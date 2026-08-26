"""
Main application wiring for God Node V2
- Mounts StaticFiles for /exports
- Includes routers for gateway, api_nexus, live editor, mobile assistant
- Ensures background tasks run non-blocking
"""
import os
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import routers
from core.gateway import router as gateway_router
from god_brain.api_nexus import router as nexus_router
from live_editor.hot_reloader import router as editor_router
from mobile_services.assistant_trigger import router as mobile_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [GOD NODE CORE] - %(levelname)s - %(message)s')
logger = logging.getLogger('GodNode')

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Starting God Node V2')
    # Start background tick loops etc. If present, they should be awaited non-blocking
    yield
    logger.info('Shutting down God Node V2')

app = FastAPI(title='God Node V2', lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'], allow_credentials=True)

# Mount static exports
if not os.path.exists('exports'):
    os.makedirs('exports', exist_ok=True)
app.mount('/exports', StaticFiles(directory='exports'), name='exports')

# Include routers
app.include_router(gateway_router)
app.include_router(nexus_router)
app.include_router(editor_router)
app.include_router(mobile_router)

# Root serves index.html if present
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import Request

@app.get('/', response_class=HTMLResponse)
async def root(request: Request):
    if os.path.exists('index.html'):
        return HTMLResponse(open('index.html','r',encoding='utf-8').read())
    return HTMLResponse('<h1>God Node V2 Running</h1>')

# Run using uvicorn externally
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=int(os.getenv('PORT',8000)), reload=True)
