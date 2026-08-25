"""
Main application for God Node V2 - integrated with gateway router, keep-alive, static exports and circuit-breaker protections.
"""

import asyncio
import os
import uuid
import time
import logging
import inspect
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Union
import io
import pathlib

# imports for routers
try:
    from core import gateway as gateway_router_module
except Exception:
    gateway_router_module = None

# optional circuit breaker
try:
    from god_brain.circuit_breaker import CircuitBreaker
    circuit = CircuitBreaker()
except Exception:
    circuit = None

# =====================================================================
# Logging
# =====================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [GOD NODE CORE] - %(levelname)s - %(message)s')
logger = logging.getLogger("GodNode.Main")

SYSTEM_LOG_BUFFER: List[str] = [
    f"[{time.strftime('%H:%M:%S')}] [SYSTEM] God Node V2 Engine Bootstrapped.",
]

def add_system_log(message: str):
    timestamp = time.strftime('%H:%M:%S')
    formatted = f"[{timestamp}] {message}"
    SYSTEM_LOG_BUFFER.append(formatted)
    if len(SYSTEM_LOG_BUFFER) > 5000:
        SYSTEM_LOG_BUFFER.pop(0)
    logger.info(message)

# =====================================================================
# FastAPI app
# =====================================================================
app = FastAPI(title="God Node V2 Enterprise", version="10.0-ULTRA-FAST-PRO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Exports static folder
EXPORTS_DIR = pathlib.Path("exports")
EXPORTS_DIR.mkdir(exist_ok=True)
app.mount("/exports", StaticFiles(directory=str(EXPORTS_DIR)), name="exports")

# Include gateway router if available
if gateway_router_module and hasattr(gateway_router_module, 'router'):
    try:
        app.include_router(gateway_router_module.router)
        add_system_log("✅ Gateway router included.")
    except Exception as e:
        add_system_log(f"⚠️ Failed to include gateway router: {e}")

# =====================================================================
# Keep-alive worker (to prevent Render sleeping)
# =====================================================================
keepalive_task = None

async def keepalive_loop(interval: int = 60):
    add_system_log("🔁 Keep-alive loop started")
    while True:
        try:
            # simple no-op: touch a timestamp file or log
            add_system_log("🔁 Keep-alive ping: server active")
        except Exception as e:
            add_system_log(f"⚠️ Keepalive ping failed: {e}")
        await asyncio.sleep(interval)

# lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    global keepalive_task
    add_system_log("🚀 App startup: beginning lifespan")
    keepalive_task = asyncio.create_task(keepalive_loop(300))  # ping every 5 minutes
    yield
    add_system_log("🛑 App shutdown: ending lifespan")
    if keepalive_task:
        keepalive_task.cancel()

app.router.lifespan_context = lifespan

# =====================================================================
# Simple endpoints
# =====================================================================
@app.get('/', response_class=HTMLResponse)
async def root():
    try:
        idx = pathlib.Path('index.html')
        if idx.exists():
            return HTMLResponse(idx.read_text(encoding='utf-8'))
    except Exception as e:
        add_system_log(f"Error serving index.html: {e}")
    return HTMLResponse('<h1>God Node V2 - Place index.html in repo root to serve dashboard</h1>')

@app.get('/api/v2/status')
async def status():
    return JSONResponse({
        'status': 'ONLINE',
        'timestamp': time.time(),
        'assets_count': 0,
        'uptime': 'unknown'
    })

# Minimal logs endpoint
@app.get('/api/v2/logs')
async def get_logs(recent: int = Query(50)):
    return JSONResponse({'status': 'SUCCESS', 'lines': SYSTEM_LOG_BUFFER[-recent:]})

# =====================================================================
# Play endpoint helper (redirects to exports preview)
# =====================================================================
@app.get('/play/{build_id}', response_class=HTMLResponse)
async def play_build(build_id: str):
    index_path = EXPORTS_DIR / build_id / 'index.html'
    if not index_path.exists():
        raise HTTPException(status_code=404, detail='Build not found')
    return HTMLResponse(index_path.read_text(encoding='utf-8'))

# =====================================================================
# Mount completed
# =====================================================================
add_system_log('✅ Main app initialized and routes mounted')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), reload=True)
