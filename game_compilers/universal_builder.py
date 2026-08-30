import asyncio
import os
import shutil
import zipfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .cpp_bridge import compile_cpp_native, compile_cpp_to_wasm
except ImportError:
    try:
        from game_compilers.cpp_bridge import compile_cpp_native, compile_cpp_to_wasm
    except ImportError:
        from cpp_bridge import compile_cpp_native, compile_cpp_to_wasm

EXPORTS_ROOT = Path(os.environ.get('EXPORTS_ROOT', 'exports'))
EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)

# Mobile-friendly CSS & Three.js Fallback
MOBILE_VIEWPORT_HEAD = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
  html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #000; touch-action: none; }
  canvas { display: block; width: 100vw; height: 100vh; }
</style>
"""

THREEJS_CDN = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'


async def create_threejs_build(
    html_source: str,
    game_id: str,
    cpp_source: Optional[str] = None,
    compile_target: str = "web",
) -> Dict[str, Any]:
    """
    Advanced Enterprise Build System for God Node V2:
    - Auto-sanitizes HTML & ensures Three.js + Mobile Viewport
    - Integrates C++ WebAssembly shims seamlessly
    - Assembles standalone distributable ZIP and index.html
    """
    start_time = time.time()
    export_dir = EXPORTS_ROOT / game_id
    export_dir.mkdir(parents=True, exist_ok=True)
    index_path = export_dir / 'index.html'

    injected_html = html_source.strip()
    compile_info = None

    # 1. Ensure Mobile & WebGL Core Headers
    if "<head>" in injected_html.lower():
        idx = injected_html.lower().find("<head>") + 6
        injected_html = injected_html[:idx] + "\n" + MOBILE_VIEWPORT_HEAD + injected_html[idx:]
    else:
        injected_html = f"<!DOCTYPE html><html><head>{MOBILE_VIEWPORT_HEAD}</head><body>{injected_html}</body></html>"

    if "three.min.js" not in injected_html and "three.js" not in injected_html:
        if "<head>" in injected_html.lower():
            idx = injected_html.lower().find("<head>") + 6
            injected_html = injected_html[:idx] + "\n" + THREEJS_CDN + injected_html[idx:]

    # 2. C++ & WebAssembly Compilation Pipeline
    if cpp_source:
        try:
            if compile_target == 'web':
                compile_info = await compile_cpp_to_wasm(cpp_source, game_id)
            else:
                compile_info = await compile_cpp_native(cpp_source, game_id)
        except Exception as e:
            compile_info = {'success': False, 'stderr': str(e)}

        if compile_info and compile_info.get('success') and compile_info.get('js_shim'):
            shim_name = Path(compile_info['js_shim']).name
            shim_src = EXPORTS_ROOT / game_id / 'wasm' / shim_name
            
            if shim_src.exists():
                try:
                    shutil.copy(shim_src, export_dir / shim_name)
                    wasm_loader = f"""
<script src="{shim_name}"></script>
<script>
  if (typeof GameModule !== 'undefined') {{
      GameModule().then(function(mod) {{
          console.log("[GodNode] Wasm Module Initialized Successfully:", mod);
          window.WasmModule = mod;
      }}).catch(function(err) {{
          console.warn("[GodNode] Wasm Module Init Warning:", err);
      }});
  }}
</script>
"""
                    if '</body>' in injected_html.lower():
                        idx = injected_html.lower().rfind('</body>')
                        injected_html = injected_html[:idx] + wasm_loader + '\n' + injected_html[idx:]
                    else:
                        injected_html += wasm_loader
                except Exception as e:
                    compile_info['inject_error'] = str(e)

    # 3. Write Master index.html
    index_path.write_text(injected_html, encoding='utf-8')

    # 4. Packaging Standalone Distributable ZIP
    zip_path = EXPORTS_ROOT / f"{game_id}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(index_path, arcname='index.html')
        wasm_dir = EXPORTS_ROOT / game_id / 'wasm'
        if wasm_dir.exists():
            for file_path in wasm_dir.iterdir():
                zf.write(file_path, arcname=f"wasm/{file_path.name}")
        for file_path in export_dir.iterdir():
            if file_path.name not in ['index.html', 'wasm']:
                zf.write(file_path, arcname=file_path.name)

    build_duration = round(time.time() - start_time, 3)

    return {
        'status': 'SUCCESS',
        'game_id': game_id,
        'index_path': str(index_path),
        'zip_path': str(zip_path),
        'download_url': f'/exports/{game_id}.zip',
        'compile_info': compile_info,
        'build_time_sec': build_duration,
        'file_size_kb': round(index_path.stat().st_size / 1024, 2)
        }
                                                         
