from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pathlib import Path
import zipfile

router = APIRouter()
EXPORTS_DIR = Path("exports")
EXPORTS_DIR.mkdir(exist_ok=True)

@router.get("/api/v1/games")
async def list_games():
    result = []
    if not EXPORTS_DIR.exists():
        EXPORTS_DIR.mkdir()
    for p in EXPORTS_DIR.iterdir():
        if p.is_dir():
            build_id = p.name
            idx = p / "index.html"
            zipf = EXPORTS_DIR / f"{build_id}.zip"
            result.append({
                "build_id": build_id,
                "preview_url": f"/exports/{build_id}/index.html" if idx.exists() else None,
                "zip_url": f"/exports/{build_id}.zip" if zipf.exists() else None
            })
    return JSONResponse({"games": result})

@router.post("/api/v1/games/{game_id}/publish")
async def publish_game(game_id: str, request_body: dict = None, bg: BackgroundTasks = None):
    targets = (request_body or {}).get("targets", ["web", "zip"])
    build_dir = EXPORTS_DIR / game_id
    if not build_dir.exists():
        raise HTTPException(404, "build not found")

    result = {"build_id": game_id, "published": {}}
    index = build_dir / "index.html"
    if index.exists() and "web" in targets:
        preview_url = f"/exports/{game_id}/index.html"
        iframe = f'<iframe src="{preview_url}" width="960" height="600"></iframe>'
        result["published"]["web"] = {"preview_url": preview_url, "embed_snippet": iframe}

    if "zip" in targets:
        zip_path = EXPORTS_DIR / f"{game_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in build_dir.rglob("*"):
                zf.write(p, arcname=p.relative_to(build_dir))
        result["published"]["zip"] = {"zip_url": f"/exports/{game_id}.zip"}

    if "capacitor" in targets:
        cap_zip = EXPORTS_DIR / f"{game_id}_capacitor.zip"
        with zipfile.ZipFile(cap_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", "Capacitor skeleton: copy 'www' into your Capacitor app and run capacitor commands.")
            if index.exists():
                zf.writestr("www/index.html", index.read_text(encoding="utf-8"))
        result["published"]["capacitor"] = {"zip_url": f"/exports/{game_id}_capacitor.zip"}

    if "tauri" in targets:
        tauri_zip = EXPORTS_DIR / f"{game_id}_tauri.zip"
        with zipfile.ZipFile(tauri_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", "Tauri skeleton: copy 'dist' content and configure tauri locally.")
            if index.exists():
                zf.writestr("dist/index.html", index.read_text(encoding="utf-8"))
        result["published"]["tauri"] = {"zip_url": f"/exports/{game_id}_tauri.zip"}

    return JSONResponse(result)
