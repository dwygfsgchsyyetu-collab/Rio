import asyncio
import os
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional

from .cpp_bridge import compile_cpp_to_wasm, compile_cpp_native

EXPORTS_ROOT = Path(os.environ.get('EXPORTS_ROOT', 'exports'))
EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)

async def create_threejs_build(html_source: str, game_id: str, cpp_source: Optional[str] = None, compile_target: str = 'web') -> Dict[str, Any]:
    """Create the build for a Three.js project. If cpp_source is provided, attempt to compile it
    to Wasm (for web) or native binary (for PC) and inject loader/shim into the HTML.

    Returns {'index_path':..., 'zip_path':..., 'download_url':...}
    """
    export_dir = EXPORTS_ROOT / game_id
    export_dir.mkdir(parents=True, exist_ok=True)
    index_path = export_dir / 'index.html'

    injected_html = html_source

    compile_info = None
    if cpp_source:
        try:
            if compile_target == 'web':
                compile_info = await compile_cpp_to_wasm(cpp_source, game_id)
            else:
                compile_info = await compile_cpp_native(cpp_source, game_id)
        except Exception as e:
            compile_info = {'success': False, 'stderr': str(e)}

        # If wasm produced, inject loader script to load the generated js shim
        if compile_info and compile_info.get('success') and compile_info.get('js_shim'):
            shim_name = Path(compile_info['js_shim']).name
            # copy shim into export_dir
            shim_src = Path('exports') / game_id / 'wasm' / shim_name
            if shim_src.exists():
                try:
                    import shutil
                    shutil.copy(shim_src, export_dir / shim_name)
                    # inject simple loader to initialize module
                    loader = (
                        f"\n<script src=\"{shim_name}\"></script>\n"
                        f"<script>/* Emscripten module loads as GameModule() */\n"
                        f"if(typeof GameModule !== 'undefined'){{{\n"
                        f"  GameModule().then(function(mod){{{\n"
                        f"    console.log('Wasm module loaded:', mod);\n"
                        f"    window.WasmModule = mod;\n"
                        f"  }});\n"
                        f"}}\n"
                        f"</script>"
                    )
                    # Place loader before closing body
                    if '</body>' in injected_html.lower():
                        injected_html = injected_html.replace('</body>', loader + '\n</body>')
                    else:
                        injected_html += loader
                except Exception as e:
                    compile_info['inject_error'] = str(e)
        else:
            # compilation failed; leave HTML unmodified and record error
            pass

    # write index
    index_path.write_text(injected_html, encoding='utf-8')

    # copy any other runtime assets if present (wasm binary, shims exist in exports/game_id/wasm)
    # collect files to zip
    zip_path = EXPORTS_ROOT / f"{game_id}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(index_path, arcname='index.html')
        wasm_dir = EXPORTS_ROOT / game_id / 'wasm'
        if wasm_dir.exists():
            for p in wasm_dir.iterdir():
                zf.write(p, arcname=p.name)
        # include shims copied into export_dir
        for p in export_dir.iterdir():
            if p.name != 'index.html':
                zf.write(p, arcname=p.name)

    return {
        'index_path': str(index_path),
        'zip_path': str(zip_path),
        'download_url': f'/exports/{game_id}.zip',
        'compile_info': compile_info
    }
