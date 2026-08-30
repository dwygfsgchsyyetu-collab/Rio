import os
import sys
import logging
import uuid
import asyncio
import json
from typing import Optional, AsyncGenerator

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ENSURE REQUIRED DIRECTORIES EXIST
# ============================================================================

def ensure_directories():
    """Create required directories at startup."""
    directories = ['static', 'exports']
    for dir_name in directories:
        try:
            os.makedirs(dir_name, exist_ok=True)
            logger.info(f"Directory ensured: {dir_name}")
        except Exception as e:
            logger.warning(f"Could not create directory {dir_name}: {e}")


# ============================================================================
# CORE FASTAPI IMPORTS (REQUIRED)
# ============================================================================

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError as e:
    logger.error(f"Critical import failed: {e}. Please install fastapi, pydantic, and uvicorn.")
    sys.exit(1)

# Local module imports with safe fallback
try:
    from god_brain.orchestrator import generate_game_and_export
    ORCHESTRATOR_AVAILABLE = True
except Exception as e:
    logger.warning(f"Orchestrator import failed (non-critical): {e}")
    ORCHESTRATOR_AVAILABLE = False
    generate_game_and_export = None

# Optional: Try to mount static files
try:
    from fastapi.staticfiles import StaticFiles
    STATIC_MOUNT_AVAILABLE = True
except ImportError:
    logger.warning("StaticFiles not available, static serving disabled")
    STATIC_MOUNT_AVAILABLE = False

# ============================================================================
# ENSURE DIRECTORIES BEFORE APP INITIALIZATION
# ============================================================================

ensure_directories()

# Initialize FastAPI app at module level
app = FastAPI(
    title="Rio Ultra-Fast Pipeline",
    description="Event-driven game generation with real-time SSE streaming",
    version="2.0.0"
)

# Task store: map task_id -> {status, result, game_id, stream_queue, progress}
TASK_STORE = {}
TASK_LOCKS = {}


class GenerateRequest(BaseModel):
    prompt: str


class StreamProgress:
    """Helper to track progress events for streaming."""
    def __init__(self):
        self.events = []
        self.lock = asyncio.Lock()
    
    async def add_event(self, percentage: int, message: str):
        async with self.lock:
            self.events.append({'percentage': percentage, 'message': message})


async def progress_callback_factory(task_id: str, stream_queue: asyncio.Queue):
    """Factory to create a progress callback that emits to SSE queue."""
    async def callback(percentage: int, message: str):
        try:
            await stream_queue.put({
                'type': 'progress',
                'percentage': percentage,
                'message': message,
                'timestamp': asyncio.get_event_loop().time()
            })
        except Exception as e:
            logger.error(f"Failed to queue progress event: {e}")
    return callback


async def run_generation_background(prompt: str, game_id: str, task_id: str, stream_queue: asyncio.Queue):
    """Run generation in background and emit progress + final result to stream queue."""
    if not ORCHESTRATOR_AVAILABLE or generate_game_and_export is None:
        await stream_queue.put({
            'type': 'error',
            'error': 'Orchestrator not available. Check imports and dependencies.'
        })
        TASK_STORE[task_id]['status'] = 'FAILED'
        TASK_STORE[task_id]['result'] = {'error': 'Orchestrator not available'}
        return
    
    try:
        progress_cb = await progress_callback_factory(task_id, stream_queue)
        result = await generate_game_and_export(prompt, game_id, progress_callback=progress_cb)
        
        # Emit final result
        await stream_queue.put({
            'type': 'complete',
            'status': result.get('status'),
            'result': result.get('result'),
            'game_id': game_id
        })
        
        # Update task store
        TASK_STORE[task_id]['status'] = result.get('status', 'SUCCESS')
        TASK_STORE[task_id]['result'] = result.get('result')
    except Exception as e:
        logger.exception(f"Background generation failed for {task_id}")
        await stream_queue.put({
            'type': 'error',
            'error': str(e)
        })
        TASK_STORE[task_id]['status'] = 'FAILED'
        TASK_STORE[task_id]['result'] = {'error': str(e)}


# ============================================================================
# ROOT & HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Serve the main Web UI (index.html)."""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    elif os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return JSONResponse({
        "status": "online",
        "engine": "God Node V2",
        "version": "2.0.0",
        "orchestrator_available": ORCHESTRATOR_AVAILABLE,
        "message": "index.html not found in root or static directory"
    })


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return JSONResponse({
        'status': 'healthy',
        'service': 'Rio Ultra-Fast Pipeline',
        'orchestrator': 'available' if ORCHESTRATOR_AVAILABLE else 'unavailable'
    })


@app.get('/api/v2/health')
async def health_check_v2():
    """Legacy health check endpoint (v2 API)."""
    return JSONResponse({'status': 'healthy', 'service': 'Rio Ultra-Fast Pipeline'})


# ============================================================================
# GAME GENERATION ENDPOINTS
# ============================================================================

@app.post('/api/v2/generate/game')
async def generate_game(req: GenerateRequest):
    """
    Initiate game generation and return task_id for polling/streaming.
    """
    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not available. Check server logs."
        )
    
    task_id = 'task_' + uuid.uuid4().hex
    game_id = 'game_' + uuid.uuid4().hex
    
    # Initialize task state
    TASK_STORE[task_id] = {
        'status': 'QUEUED',
        'result': None,
        'game_id': game_id,
        'stream_queue': asyncio.Queue(maxsize=100),
        'progress': StreamProgress()
    }
    
    # Launch background generation task
    asyncio.create_task(
        run_generation_background(
            req.prompt,
            game_id,
            task_id,
            TASK_STORE[task_id]['stream_queue']
        )
    )
    
    return JSONResponse({
        'task_id': task_id,
        'game_id': game_id,
        'status': 'QUEUED',
        'stream_url': f'/api/v2/stream/pipeline/{task_id}',
        'status_url': f'/api/v2/status/{task_id}'
    })


@app.get('/api/v2/status/{task_id}')
async def get_status(task_id: str):
    """Poll current task status."""
    if task_id not in TASK_STORE:
        raise HTTPException(status_code=404, detail='task not found')
    
    t = TASK_STORE[task_id]
    res = {'status': t.get('status', 'WORKING')}
    if t.get('result'):
        res['result'] = t['result']
    return JSONResponse(res)


# ============================================================================
# SERVER-SENT EVENTS (SSE) STREAMING
# ============================================================================

async def sse_event_generator(task_id: str) -> AsyncGenerator[str, None]:
    """Server-Sent Events generator for real-time progress streaming."""
    if task_id not in TASK_STORE:
        raise HTTPException(status_code=404, detail='task not found')
    
    stream_queue = TASK_STORE[task_id]['stream_queue']
    sent_complete = False
    start_time = asyncio.get_event_loop().time()
    timeout = 120
    
    try:
        while not sent_complete:
            try:
                event = await asyncio.wait_for(stream_queue.get(), timeout=2.0)
                
                if event['type'] == 'progress':
                    yield f"data: {json.dumps(event)}\n\n"
                elif event['type'] == 'complete':
                    yield f"data: {json.dumps(event)}\n\n"
                    sent_complete = True
                elif event['type'] == 'error':
                    yield f"data: {json.dumps(event)}\n\n"
                    sent_complete = True
            except asyncio.TimeoutError:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    logger.warning(f"Stream timeout for {task_id}")
                    yield f"data: {json.dumps({'type': 'timeout', 'message': 'Stream timeout'})}\n\n"
                    sent_complete = True
                else:
                    yield ": keepalive\n\n"
    except GeneratorExit:
        logger.info(f"Client disconnected from stream {task_id}")
    except Exception as e:
        logger.exception(f"SSE generator error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@app.get('/api/v2/stream/pipeline/{task_id}')
async def stream_pipeline(task_id: str):
    """High-throughput Server-Sent Events endpoint."""
    if task_id not in TASK_STORE:
        raise HTTPException(status_code=404, detail='task not found')
    
    return StreamingResponse(
        sse_event_generator(task_id),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.post('/api/v2/execute')
async def execute_direct(req: Request):
    """Direct synchronous execution."""
    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not available. Check server logs."
        )
    
    body = await req.json()
    prompt = body.get('prompt')
    if not prompt:
        raise HTTPException(status_code=400, detail='missing prompt')
    
    try:
        game_id = 'game_' + uuid.uuid4().hex
        out = await generate_game_and_export(prompt, game_id)
        return JSONResponse(out)
    except Exception as e:
        logger.exception(f"Direct execution failed: {e}")
        return JSONResponse({'status':'FAILED','result':{'error':str(e)}}, status_code=500)


# ============================================================================
# STATIC FILES MOUNTING
# ============================================================================

if STATIC_MOUNT_AVAILABLE:
    try:
        app.mount('/static', StaticFiles(directory='static'), name='static')
        app.mount('/exports', StaticFiles(directory='exports'), name='exports')
        logger.info("Static and Exports mounted")
    except Exception as e:
        logger.warning(f"Could not mount static files: {e}")


# ============================================================================
# ENTRYPOINT
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    logger.info(f"Starting Rio Ultra-Fast Pipeline on {host}:{port}")
    logger.info(f"Orchestrator available: {ORCHESTRATOR_AVAILABLE}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level='info'
)
            
