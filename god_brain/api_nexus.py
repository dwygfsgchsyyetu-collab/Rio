import asyncio
import io
import logging
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from security_vault.encryption import GodVault
from god_brain.circuit_breaker import CircuitBreaker

logger = logging.getLogger("god_brain.api_nexus")
router = APIRouter()
circuit = CircuitBreaker()

# --- Provider adapters (Gemini / OpenAI) ---
class ProviderAdapter:
    def __init__(self, name: str, vault: Optional[GodVault]):
        self.name = name
        self.vault = vault

    async def generate_text(self, prompt: str, language: str = "hi") -> str:
        # Safe fallback: return a simple Hindi-first message
        if language.startswith("hi"):
            return "नमस्ते! मैंने आपकी बात समझ ली — यह एक डिफ़ॉल्ट उत्तर है।"
        return "Hello! I understood your request — this is a fallback response."

    async def tts(self, text: str, language: str = "hi") -> bytes:
        # Fallback: return raw UTF-8 bytes (client may treat as speech fallback)
        return text.encode("utf-8")

    async def stt(self, audio_bytes: bytes) -> str:
        # fallback transcription
        return "(transcription not available on this server)"

class GeminiAdapter(ProviderAdapter):
    async def generate_text(self, prompt: str, language: str = "hi") -> str:
        # If vault has gemini key, you would call Gemini API here.
        try:
            key = self.vault.get_secret("gemini") if self.vault else None
        except Exception:
            key = None
        if not key:
            return await super().generate_text(prompt, language)
        # TODO: implement actual Gemini REST call
        return await super().generate_text(prompt, language)

class OpenAIAdapter(ProviderAdapter):
    async def generate_text(self, prompt: str, language: str = "hi") -> str:
        try:
            key = self.vault.get_secret("openai") if self.vault else None
        except Exception:
            key = None
        if not key:
            return await super().generate_text(prompt, language)
        # TODO: implement actual OpenAI call
        return await super().generate_text(prompt, language)

# Initialize vault (uses security_vault.GodVault implemented earlier)
try:
    VAULT = GodVault()
except Exception:
    VAULT = None

GEMINI = GeminiAdapter("gemini", VAULT)
OPENAI = OpenAIAdapter("openai", VAULT)

# --- Vault endpoints (simple secure UI hooks) ---
@router.post("/api/v2/vault/store")
async def store_key(request: Request):
    """
    Store an API key securely in the vault.
    Body: { "service": "gemini|openai|elevenlabs", "key": "..." }
    Requires NEXUS_MASTER_KEY present in environment for persistence.
    """
    body = await request.json()
    service = body.get("service")
    key = body.get("key")
    if not service or not key:
        raise HTTPException(status_code=400, detail="service and key are required")
    try:
        vault = GodVault()
        vault.store_secret(service, key)
        return JSONResponse({"status": "OK", "service": service})
    except Exception as e:
        logger.exception("vault store failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/v2/vault/get/{service}")
async def get_key(service: str):
    try:
        vault = GodVault()
        val = vault.get_secret(service)
        return JSONResponse({"service": service, "key_present": bool(val)})
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Assistant endpoints ---
@router.post("/api/v2/nexus/respond")
async def nexus_respond(request: Request):
    """
    Simple text assistant endpoint.
    body: { "text": "...", "language": "hi", "model": "gemini|openai" }
    """
    body = await request.json()
    text = body.get("text", "")
    language = body.get("language", "hi")
    model = body.get("model", "gemini")
    adapter = GEMINI if model == "gemini" else OPENAI

    try:
        reply = await circuit(adapter.generate_text)(text, language=language)
    except Exception:
        logger.exception("adapter call failed - using fallback")
        reply = await adapter.generate_text(text, language=language)

    return JSONResponse({"reply": reply, "language": language})

@router.post("/api/v2/nexus/tts")
async def nexus_tts(request: Request):
    """
    TTS endpoint: returns audio/mpeg stream.
    body: { "text": "...", "language": "hi", "model": "gemini|openai" }
    """
    body = await request.json()
    text = body.get("text", "")
    language = body.get("language", "hi")
    model = body.get("model", "gemini")
    adapter = GEMINI if model == "gemini" else OPENAI
    try:
        audio = await circuit(adapter.tts)(text, language=language)
    except Exception:
        logger.exception("tts failed; using fallback bytes")
        audio = await adapter.tts(text, language=language)
    return StreamingResponse(io.BytesIO(audio), media_type="audio/mpeg")

# --- WebSocket streaming assistant (simple) ---
@router.websocket("/ws/nexus")
async def ws_nexus(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            obj = await ws.receive_json()
            typ = obj.get("type")
            if typ == "text":
                prompt = obj.get("content", "")
                model = obj.get("model", "gemini")
                adapter = GEMINI if model == "gemini" else OPENAI
                try:
                    reply = await circuit(adapter.generate_text)(prompt, language=obj.get("language", "hi"))
                except Exception:
                    reply = await adapter.generate_text(prompt, language=obj.get("language", "hi"))
                await ws.send_json({"type": "final", "content": reply})
            elif typ == "stt_chunk":
                # expected base64 chunk - server STT not enabled by default
                await ws.send_json({"type": "ack", "message": "chunk received"})
            else:
                await ws.send_json({"type": "error", "message": "unknown type"})
    except Exception as e:
        logger.info("ws_nexus closed: %s", e)
        try:
            await ws.close()
        except Exception:
            pass
