"""
Production-ready God Node V2 - Nexus API (Gemini + OpenAI adapters)
- Uses httpx for async HTTP calls to Google Generative API
- Extracts API keys from headers, security vault, or environment
- CircuitBreaker protects remote calls
- WebSocket streaming implemented by chunking provider responses
"""
from typing import Optional, Dict, Any
import os
import json
import asyncio
import logging
import httpx

from fastapi import APIRouter, Request, WebSocket, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from god_brain.circuit_breaker import CircuitBreaker

logger = logging.getLogger("god_brain.api_nexus")
router = APIRouter()

# Import GodVault if available. If missing, raise explicit errors when used.
try:
    from security_vault.encryption import GodVault
except Exception:
    GodVault = None

circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

# Configuration
GOOGLE_GENERATIVE_BASE = os.getenv("GOOGLE_GENERATIVE_BASE", "https://generative.googleapis.com/v1")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-09-2025")
HTTPX_TIMEOUT = float(os.getenv("NEXUS_HTTP_TIMEOUT", "30"))

async def resolve_key(service: str, request: Optional[Request] = None) -> Optional[str]:
    """Resolve API key or bearer token for a named service.
    Resolution order:
      1. Incoming headers (X-Gemini-Key, X-Openai-Key, X-Elevenlabs-Key)
      2. Security Vault (if present)
      3. Environment variables (GEMINI_API_KEY, OPENAI_API_KEY)
    Returns raw key/token string or None
    """
    header_map = {
        "gemini": "X-Gemini-Key",
        "openai": "X-Openai-Key",
        "elevenlabs": "X-Elevenlabs-Key",
    }
    env_map = {
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
        "openai": ["OPENAI_API_KEY"],
        "elevenlabs": ["ELEVENLABS_API_KEY"]
    }

    # 1. from headers
    if request is not None:
        header_key = header_map.get(service)
        if header_key:
            val = request.headers.get(header_key)
            if val:
                return val.strip()

    # 2. from vault
    if GodVault is not None:
        try:
            vault = GodVault()
            secret = vault.get_secret(service)
            if secret:
                return secret
        except Exception as e:
            logger.warning("Vault lookup failed: %s", e)

    # 3. env vars
    for k in env_map.get(service, []):
        v = os.getenv(k)
        if v:
            return v.strip()

    return None

# ---------------------------------------------------------------------------
# Gemini / Google Generative API adapter
# ---------------------------------------------------------------------------
class GeminiAdapter:
    def __init__(self, request: Optional[Request] = None):
        self.request = request

    async def generate(self, prompt: str, language: str = "hi", model: Optional[str] = None) -> Dict[str, Any]:
        """Call Google Generative API: models/{model}:generate
        Returns parsed JSON result with 'output' -> text/html
        """
        model_name = model or DEFAULT_GEMINI_MODEL
        key = await resolve_key("gemini", request=self.request)
        if not key:
            raise HTTPException(status_code=401, detail="Gemini API key not found. Provide via X-Gemini-Key header, Security Vault, or GEMINI_API_KEY env var.")

        url = f"{GOOGLE_GENERATIVE_BASE}/models/{model_name}:generate"

        # Accept both API key formats and OAuth bearer tokens
        headers = {"Content-Type": "application/json"}
        params = {}
        if key.startswith("AIza") or key.startswith("AIza"):
            params["key"] = key
        elif key.startswith("ya29.") or key.startswith("AQ") or key.startswith("AQA"):
            headers["Authorization"] = f"Bearer {key}"
        else:
            # Best-effort: if looks like a long json credentials path, treat as env variable
            if os.path.exists(key):
                # If a path to service account JSON, set GOOGLE_APPLICATION_CREDENTIALS accordingly
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key
            else:
                # fallback to API key query param
                params["key"] = key

        # Prompt engineering: request either structured JSON or standalone HTML if user asks for code
        system_instruction = (
            "You are a production-grade engine. If the user asks for a runnable web game or Three.js code, "
            "respond ONLY with a single valid HTML5 document (<!doctype html>...)</> that is self-contained or references assets by filename. "
            "If the user asks for data or structured output, respond with JSON only. "
            "Prioritize Hindi output when language starts with 'hi', but always keep code and JSON output valid ASCII/UTF-8."
        )

        # Construct request body compatible with Generative API
        body = {
            "prompt": {
                "context": system_instruction,
                "text": prompt
            },
            "temperature": 0.2,
            "max_output_tokens": 1024
        }

        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            try:
                resp = await client.post(url, headers=headers, params=params, json=body)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.exception("Gemini API error: %s", e)
                raise HTTPException(status_code=502, detail=f"Gemini API error: {e.response.text}")
            except Exception as e:
                logger.exception("Gemini request failed: %s", e)
                raise HTTPException(status_code=502, detail=str(e))

        # Parse probable fields. Generative API returns candidates or output.
        # We will look for 'candidates' or 'output' fields with text.
        text = None
        if isinstance(data, dict):
            # common v1beta structures
            if "candidates" in data:
                candidates = data.get("candidates")
                if candidates and isinstance(candidates, list):
                    text = candidates[0].get("content") if isinstance(candidates[0], dict) else str(candidates[0])
            elif "output" in data:
                out = data.get("output")
                if isinstance(out, list) and out:
                    # output[0].content perhaps
                    first = out[0]
                    if isinstance(first, dict) and "content" in first:
                        content_field = first["content"]
                        if isinstance(content_field, list):
                            # join text parts
                            text = "".join([p.get("text", "") for p in content_field if isinstance(p, dict)])
                        elif isinstance(content_field, str):
                            text = content_field
        if text is None:
            # Try generic fallback extraction
            text = json.dumps(data)

        return {"raw": data, "text": text}

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@router.post("/api/v2/nexus/respond")
async def nexus_respond(request: Request):
    """Receive JSON { text: str, language: 'hi'|'en', model: 'gemini' }
    Calls Gemini and returns structured result. Raises 4xx/5xx for missing keys or provider errors.
    """
    payload = await request.json()
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    language = payload.get("language", "hi")
    model = payload.get("model", "gemini")

    if model != "gemini":
        raise HTTPException(status_code=400, detail="unsupported model; only 'gemini' supported in this endpoint")

    adapter = GeminiAdapter(request)

    # wrap remote call in circuit breaker
    try:
        result = await circuit(adapter.generate)(text, language=language, model=model)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Nexus respond failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # If the response text looks like JSON or HTML, return it raw
    return JSONResponse({"reply": result.get("text", ""), "raw": result.get("raw")})

@router.post("/api/v2/nexus/tts")
async def nexus_tts(request: Request):
    """TTS proxy that uses ElevenLabs or Google TTS if available.
    Body: { text: ..., language: 'hi' }
    Returns audio/mpeg
    """
    body = await request.json()
    text = body.get("text")
    lang = body.get("language", "hi")
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    # Prefer ElevenLabs if key present, otherwise attempt Google Cloud TTS via RPC
    eleven_key = await resolve_key("elevenlabs", request)
    gemini_key = await resolve_key("gemini", request)

    # Use ElevenLabs REST API if key present
    if eleven_key:
        # ElevenLabs expects a voice and returns audio content
        url = "https://api.elevenlabs.io/v1/text-to-speech/alloy"
        headers = {"xi-api-key": eleven_key, "Content-Type": "application/json"}
        payload = {"text": text, "voice": "alloy", "model": "eleven_multilingual_v1"}
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            return StreamingResponse(r.aiter_bytes(), media_type="audio/mpeg")

    # If ElevenLabs not available, try Google TTS via REST using service account ADC (requires google-auth)
    if gemini_key:  # if user has google creds, attempt REST call to text:synthesize
        tts_url = "https://texttospeech.googleapis.com/v1/text:synthesize"
        # If gemini_key is API key (AIza) use ?key=, otherwise Authorization header must be set via ADC
        params = {}
        headers = {"Content-Type": "application/json"}
        if gemini_key.startswith("AIza"):
            params["key"] = gemini_key
        elif gemini_key.startswith("ya29.") or gemini_key.startswith("AQ"):
            headers["Authorization"] = f"Bearer {gemini_key}"
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": "hi-IN" if lang.startswith("hi") else "en-US", "ssmlGender": "FEMALE"},
            "audioConfig": {"audioEncoding": "MP3"}
        }
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            r = await client.post(tts_url, headers=headers, params=params, json=payload)
            r.raise_for_status()
            data = r.json()
            audio_b64 = data.get("audioContent")
            if not audio_b64:
                raise HTTPException(status_code=502, detail="No audio content returned from TTS")
            import base64, io
            audio_bytes = base64.b64decode(audio_b64)
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")

    raise HTTPException(status_code=501, detail="No TTS provider configured (ElevenLabs or Google TTS required)")

# ---------------------------------------------------------------------------
# WebSocket streaming assistant
# ---------------------------------------------------------------------------
@router.websocket("/ws/nexus")
async def ws_nexus(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            typ = msg.get("type", "text")
            if typ != "text":
                await ws.send_json({"type": "error", "message": "unsupported message type"})
                continue
            content = msg.get("content", "")
            language = msg.get("language", "hi")
            model = msg.get("model", "gemini")

            if model != "gemini":
                await ws.send_json({"type": "error", "message": "unsupported model"})
                continue

            adapter = GeminiAdapter(ws._request if hasattr(ws, "_request") else None)

            # Run generation in executor and stream chunks back to client
            loop = asyncio.get_event_loop()
            try:
                result = await circuit(adapter.generate)(content, language=language, model=model)
            except HTTPException as e:
                await ws.send_json({"type": "error", "message": str(e.detail)})
                continue
            except Exception as e:
                logger.exception("Streaming generation failed: %s", e)
                await ws.send_json({"type": "error", "message": "generation failed"})
                continue

            full_text = result.get("text", "")
            # Stream by slicing full_text into 200-char chunks
            chunk_size = 200
            for i in range(0, len(full_text), chunk_size):
                await ws.send_json({"type": "partial", "content": full_text[i:i+chunk_size]})
                await asyncio.sleep(0.05)
            await ws.send_json({"type": "final", "content": full_text})

    except Exception as e:
        logger.info("ws_nexus connection closed: %s", e)
        try:
            await ws.close()
        except Exception:
            pass
