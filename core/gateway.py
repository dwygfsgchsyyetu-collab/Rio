"""
Gateway endpoints for game listing and publishing
- Lists builds in /exports
- Publishes web zip, capacitor skeleton, and tauri skeleton
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pathlib import Path
import zipfile
import json

router = APIRouter()
EXPORTS_DIR = Path('exports')
EXPORTS_DIR.mkdir(exist_ok=True)

@router.get('/api/v1/games')
async def list_games():
    builds = []
    for p in sorted(EXPORTS_DIR.iterdir()):
        if p.is_dir():
            idx = p / 'index.html'
            z = EXPORTS_DIR / f"{p.name}.zip"
            builds.append({
                'game_id': p.name,
                'preview_url': f"/exports/{p.name}/index.html" if idx.exists() else None,
                'zip_url': f"/exports/{p.name}.zip" if z.exists() else None
            })
    return JSONResponse({'games': builds})

@router.post('/api/v1/games/{game_id}/publish')
async def publish_game(game_id: str, request: Request):
    body = await request.json() if request.headers.get('content-type','').startswith('application/json') else {}
    targets = body.get('targets', ['web', 'zip'])
    build_dir = EXPORTS_DIR / game_id
    if not build_dir.exists():
        raise HTTPException(404, 'build not found')

    result = { 'game_id': game_id, 'published': {} }

    # Web preview and zip
    if 'web' in targets or 'zip' in targets:
        zip_path = EXPORTS_DIR / f"{game_id}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for p in build_dir.rglob('*'):
                zf.write(p, arcname=p.relative_to(build_dir))
        result['published']['zip'] = { 'zip_url': f"/exports/{game_id}.zip" }
        if (build_dir / 'index.html').exists():
            result['published']['preview'] = { 'preview_url': f"/exports/{game_id}/index.html", 'embed': f'<iframe src="/exports/{game_id}/index.html" width="960" height="600"></iframe>' }

    # Capacitor skeleton
    if 'capacitor' in targets:
        cap_zip = EXPORTS_DIR / f"{game_id}_capacitor.zip"
        with zipfile.ZipFile(cap_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add a basic capacitor.config.json
            cap_conf = {
                "appId": f"com.godnode.{game_id}",
                "appName": f"GodNode-{game_id}",
                "webDir": "www",
                "bundledWebRuntime": False
            }
            zf.writestr('capacitor.config.json', json.dumps(cap_conf, indent=2))
            # add www/index.html
            if (build_dir / 'index.html').exists():
                zf.writestr('www/index.html', (build_dir / 'index.html').read_text(encoding='utf-8'))
            zf.writestr('README.txt', 'Copy this www folder into a Capacitor project, then run "npx cap add android" etc.')
        result['published']['capacitor'] = { 'zip_url': f"/exports/{game_id}_capacitor.zip" }

    # Tauri skeleton
    if 'tauri' in targets:
        tauri_zip = EXPORTS_DIR / f"{game_id}_tauri.zip"
        with zipfile.ZipFile(tauri_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # minimal tauri.conf.json and src files
            tauri_conf = {
                "package": {"productName": f"GodNode {game_id}", "version": "0.1.0"},
                "build": {"distDir": "dist", "devPath": "http://localhost:4000"}
            }
            zf.writestr('src-tauri/tauri.conf.json', json.dumps(tauri_conf, indent=2))
            if (build_dir / 'index.html').exists():
                zf.writestr('dist/index.html', (build_dir / 'index.html').read_text(encoding='utf-8'))
            zf.writestr('README.txt', 'Copy dist into your Tauri project and run `cargo tauri build`.')
        result['published']['tauri'] = { 'zip_url': f"/exports/{game_id}_tauri.zip" }

    return JSONResponse(result)
