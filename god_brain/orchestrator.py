"""
Production Orchestrator for God Node V2
- Calls GeminiAdapter to generate HTML or structured game code
- Sanitizes output and writes final build to /exports/{game_id}/index.html
- Zips the build into /exports/{game_id}.zip
- Returns a status dict suitable for frontend polling
"""
import re
import os
import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from god_brain.api_nexus import GeminiAdapter
from game_compilers.universal_builder import create_threejs_build, EXPORTS_DIR

logger = logging.getLogger("god_brain.orchestrator")

# Utility: sanitize model output (strip markdown fences and leading/trailing whitespace)
_FENCE_RE = re.compile(r"```(?:[\w+-]+)?\n(?P<code>.*)```", re.S)


def _strip_code_fences(text: str) -> str:
    if not text:
        return text
    # Replace all fenced code blocks with their inner code
    def _repl(m):
        return m.group('code')
    cleaned = _FENCE_RE.sub(_repl, text)
    # Also strip any remaining leading/trailing backticks/newlines
    cleaned = cleaned.strip()
    # If the agent returned JSON wrapped in markdown, attempt to extract the JSON payload
    # but prefer raw HTML if present
    return cleaned


async def orchestrate_game(prompt: str, game_id: Optional[str] = None, language: str = 'hi', model: str = 'gemini') -> Dict[str, Any]:
    """Orchestrate end-to-end generation of a Three.js game from a user prompt.

    Steps:
      1. Call GeminiAdapter to obtain generation output
      2. Sanitize output (strip markdown fences)
      3. Ensure /exports/{game_id}/ exists and write index.html
      4. Create/refresh /exports/{game_id}.zip
      5. Return status with preview and download URLs and raw_html to allow immediate iframe rendering
    """
    task_id = f"GAME_{game_id or 'local'}"
    game_id = game_id or task_id

    adapter = GeminiAdapter(None)

    try:
        result = await adapter.generate(prompt, language=language, model=model)
    except Exception as e:
        logger.exception("Orchestrator: generation failed: %s", e)
        return {"task_id": task_id, "status": "FAILED", "error": str(e)}

    raw_text = result.get('text', '') if isinstance(result, dict) else str(result)
    cleaned = _strip_code_fences(raw_text)

    # Prepare exports directory
    build_dir = EXPORTS_DIR / game_id
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    # If cleaned text already looks like a complete HTML document, write it directly
    html_to_write = cleaned
    if not cleaned.lower().strip().startswith("<!doctype html") and not cleaned.lower().strip().startswith("<html"):
        # If it's not a full HTML document, we will embed it into the universal template
        # Use create_threejs_build to scaffold a default build, then inject the generated JS/HTML into index.html
        try:
            # create default build (no assets)
            create_threejs_build(game_id, assets=[], title=f"God Node - {game_id}")
            index_path = build_dir / 'index.html'
            if index_path.exists():
                # Read scaffold and attempt to inject the cleaned content into a placeholder
                scaffold = index_path.read_text(encoding='utf-8')
                # Attempt to replace default scene comment block with the cleaned code; fallback to prepend
                if '<!-- GENERATED_GAME_CONTENT -->' in scaffold:
                    scaffold = scaffold.replace('<!-- GENERATED_GAME_CONTENT -->', cleaned)
                    html_to_write = scaffold
                else:
                    # Prepend cleaned content inside body before existing script
                    html_to_write = re.sub(r"(<body[^>]*>)", r"\1\n<!-- GENERATED -->\n"+cleaned, scaffold, count=1, flags=re.I)
            else:
                # Fallback: wrap cleaned content in minimal HTML
                html_to_write = f"<!doctype html>\n<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{game_id}</title></head><body>\n{cleaned}\n</body></html>"
        except Exception as e:
            logger.exception("Orchestrator: create_threejs_build scaffold failed: %s", e)
            # fallback to writing minimal HTML
            html_to_write = f"<!doctype html>\n<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{game_id}</title></head><body>\n{cleaned}\n</body></html>"

    # Ensure index.html is written
    index_file = build_dir / 'index.html'
    index_file.write_text(html_to_write, encoding='utf-8')

    # Recreate zip bundle
    zip_path = EXPORTS_DIR / f"{game_id}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in build_dir.rglob('*'):
            zf.write(p, arcname=p.relative_to(build_dir))

    preview_url = f"/exports/{game_id}/index.html"
    zip_url = f"/exports/{game_id}.zip"

    logger.info("Orchestrator: generated game %s, preview=%s, zip=%s", game_id, preview_url, zip_url)

    return {
        "task_id": task_id,
        "status": "SUCCESS",
        "preview_url": preview_url,
        "download_url": zip_url,
        "raw_html": html_to_write,
        "provider_raw": result.get('raw') if isinstance(result, dict) else None
    }


# Convenience synchronous wrapper for compatibility
def orchestrate_game_sync(prompt: str, game_id: Optional[str] = None, language: str = 'hi', model: str = 'gemini') -> Dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(orchestrate_game(prompt, game_id=game_id, language=language, model=model))
