from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid
import asyncio

from god_brain.orchestrator import generate_game_and_export

app = FastAPI()

# Simple in-memory task store for demo purposes.
TASK_STORE = {}

class GenerateRequest(BaseModel):
    prompt: str


@app.post('/api/v2/generate/game')
async def generate_game(req: GenerateRequest):
    task_id = 'task_' + uuid.uuid4().hex
    TASK_STORE[task_id] = {'status': 'WORKING', 'result': None}
    try:
        game_id = 'game_' + uuid.uuid4().hex
        # run orchestrator asynchronously without blocking the request thread
        # we run it as a background task but await it to populate result for demo simplicity
        out = await generate_game_and_export(req.prompt, game_id)
        TASK_STORE[task_id]['status'] = out.get('status', 'SUCCESS')
        TASK_STORE[task_id]['result'] = out.get('result')
        TASK_STORE[task_id]['game_id'] = game_id
        return JSONResponse({'task_id': task_id, 'status': TASK_STORE[task_id]['status']})
    except Exception as e:
        TASK_STORE[task_id]['status'] = 'FAILED'
        TASK_STORE[task_id]['result'] = {'error': str(e)}
        return JSONResponse({'task_id': task_id, 'status': 'FAILED', 'error': str(e)}, status_code=500)


@app.get('/api/v2/status/{task_id}')
async def get_status(task_id: str):
    if task_id not in TASK_STORE:
        raise HTTPException(status_code=404, detail='task not found')
    t = TASK_STORE[task_id]
    res = {'status': t.get('status', 'WORKING')}
    if t.get('result'):
        res['result'] = t['result']
    else:
        res['result'] = None
    return JSONResponse(res)


@app.post('/api/v2/execute')
async def execute_direct(req: Request):
    body = await req.json()
    prompt = body.get('prompt')
    if not prompt:
        raise HTTPException(status_code=400, detail='missing prompt')
    try:
        game_id = 'game_' + uuid.uuid4().hex
        out = await generate_game_and_export(prompt, game_id)
        return JSONResponse(out)
    except Exception as e:
        return JSONResponse({'status':'FAILED','result':{'error':str(e)}}, status_code=500)
