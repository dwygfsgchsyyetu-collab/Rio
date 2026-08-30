import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

# Wrapper around emscripten/wasm/native toolchains.
# This module uses asyncio subprocesses to avoid blocking the event loop.

EMSCRIPTEN_EMCC = os.environ.get('EMCC_PATH', 'emcc')  # override if needed

async def compile_cpp_to_wasm(cpp_source: str, game_id: str, timeout: int = 30) -> Dict[str, Any]:
    """Attempt to compile provided C++ source into WebAssembly using emscripten.

    Returns a dict with keys: success(bool), wasm_path(str|None), js_shim(str|None), stderr(str)
    If emscripten is not available or compilation fails, returns success=False and stderr.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix=f'game_build_{game_id}_'))
    src_file = tmpdir / 'game.cpp'
    out_js = tmpdir / 'game.js'
    out_wasm = tmpdir / 'game.wasm'
    src_file.write_text(cpp_source, encoding='utf-8')

    cmd = f"{EMSCRIPTEN_EMCC} {src_file} -O2 -s WASM=1 -s MODULARIZE=1 -s EXPORT_NAME=GameModule -o {out_js}"

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {'success': False, 'wasm_path': None, 'js_shim': None, 'stderr': 'Compilation timed out'}

        if proc.returncode != 0:
            return {'success': False, 'wasm_path': None, 'js_shim': None, 'stderr': stderr.decode(errors='ignore')}

        # On success, move produced artifacts into a stable path
        artifact_dir = Path('exports') / game_id / 'wasm'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        # emscripten produces .js and .wasm; copy them
        if out_js.exists():
            shutil.copy(out_js, artifact_dir / out_js.name)
        if out_wasm.exists():
            shutil.copy(out_wasm, artifact_dir / out_wasm.name)

        return {
            'success': True,
            'wasm_path': str(artifact_dir / out_wasm.name) if out_wasm.exists() else None,
            'js_shim': str(artifact_dir / out_js.name) if out_js.exists() else None,
            'stderr': stderr.decode(errors='ignore') if stderr else ''
        }
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


async def compile_cpp_native(cpp_source: str, game_id: str, timeout: int = 30) -> Dict[str, Any]:
    """Attempt a native compilation (gcc/clang) to a native binary. Used for PC exports.
    For web targets prefer compile_cpp_to_wasm.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix=f'native_build_{game_id}_'))
    src_file = tmpdir / 'game.cpp'
    bin_file = tmpdir / 'game_bin'
    src_file.write_text(cpp_source, encoding='utf-8')
    cmd = f"g++ {src_file} -O2 -o {bin_file}"
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {'success': False, 'binary_path': None, 'stderr': 'Native compilation timed out'}

    if proc.returncode != 0:
        return {'success': False, 'binary_path': None, 'stderr': stderr.decode(errors='ignore')}

    artifact_dir = Path('exports') / game_id / 'native'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(bin_file, artifact_dir / bin_file.name)
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
    return {'success': True, 'binary_path': str(artifact_dir / bin_file.name), 'stderr': ''}
