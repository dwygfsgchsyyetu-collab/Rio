from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path

router = APIRouter()

@router.post('/api/v2/assistant/trigger')
async def trigger_assistant_audio(file: UploadFile = File(...)):
    """Accepts an audio upload and forwards to the nexus for STT/assistant response. Lightweight wrapper."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail='Empty file')

    tmp_path = Path('uploads')
    tmp_path.mkdir(exist_ok=True)
    dest = tmp_path / file.filename
    with open(dest, 'wb') as f:
        f.write(data)

    return JSONResponse({'status': 'received', 'path': str(dest)})
