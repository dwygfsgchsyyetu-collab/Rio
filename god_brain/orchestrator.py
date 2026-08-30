import os
import re
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib

from .api_nexus import GeminiAdapter
from game_compilers.universal_builder import create_threejs_build

logger = logging.getLogger("god_brain.orchestrator")

# Export path base
EXPORTS_ROOT = Path(os.environ.get('EXPORTS_ROOT', 'exports'))
EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)

THREE_R128 = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'

# In-Memory LRU Cache for boilerplate & common WASM modules
_boilerplate_cache = {}
_wasm_module_cache = {}

FALLBACK_ARENA = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Fallback Arena</title>
%s
<style>body{margin:0;overflow:hidden}canvas{display:block}</style>
</head><body>
<div id="root"></div>
<script>
// Minimal Three.js r128 fallback arena: rotating cube, basic WASD movement
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setSize(window.innerWidth, window.innerHeight); document.body.appendChild(renderer.domElement);
const geometry = new THREE.BoxGeometry();
const material = new THREE.MeshStandardMaterial({color:0x0077ff});
const cube = new THREE.Mesh(geometry, material); scene.add(cube);
const light = new THREE.DirectionalLight(0xffffff, 1); light.position.set(5,10,7.5); scene.add(light);
const ambient = new THREE.AmbientLight(0x404040); scene.add(ambient);
camera.position.z = 5;
let vel = {x:0,z:0}; const speed = 0.06;
const keys = {};
window.addEventListener('keydown', e=> keys[e.key.toLowerCase()] = true);
window.addEventListener('keyup', e=> keys[e.key.toLowerCase()] = false);
function animate(){ requestAnimationFrame(animate); if(keys['w']) cube.position.z -= speed; if(keys['s']) cube.position.z += speed; if(keys['a']) cube.position.x -= speed; if(keys['d']) cube.position.x += speed; cube.rotation.x += 0.01; cube.rotation.y += 0.013; renderer.render(scene, camera);} animate();
window.addEventListener('resize', ()=>{ camera.aspect = window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); });
</script>
</body></html>'''


# Progress event callbacks
_progress_callbacks: Dict[str, list] = {}


def register_progress_callback(task_id: str, callback: Callable[[int, str], Coroutine[Any, Any, None]]):
    """Register a callback function to receive progress events (percentage, message)."""
    if task_id not in _progress_callbacks:
        _progress_callbacks[task_id] = []
    _progress_callbacks[task_id].append(callback)


async def emit_progress(task_id: str, percentage: int, message: str):
    """Emit progress event to all registered callbacks for this task."""
    if task_id in _progress_callbacks:
        tasks = [cb(percentage, message) for cb in _progress_callbacks[task_id]]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _get_boilerplate_hash(html: str) -> str:
    """Generate a hash for boilerplate caching."""
    return hashlib.md5(html.encode()).hexdigest()


@lru_cache(maxsize=128)
def _cached_strip_markdown_and_quotes(text: str) -> str:
    """Aggressively strip markdown fences and outer quoting from assistant outputs."""
    if not text:
        return ''
    text = re.sub(r"```(?:html|javascript|js)?\s*", '', text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", '', text)
    text = re.sub(r'^\s*["\']+'  , '', text)
    text = re.sub(r'["\']+'  r'\s*$', '', text)
    text = re.sub(r'^(assistant:|output:|answer:)\s*', '', text, flags=re.IGNORECASE)
    return text.strip()


def _strip_markdown_and_quotes(text: str) -> str:
    """Wrapper for cached stripping."""
    return _cached_strip_markdown_and_quotes(text)


def _extract_html_candidate(text: str) -> str:
    if not text:
        return ''
    clean = _strip_markdown_and_quotes(text)
    m = re.search(r"(?is)(<!doctype\s+html.*?</html>)", clean)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?is)(<html.*?</html>)", clean)
    if m:
        return m.group(1).strip()
    if '<script' in clean or '<canvas' in clean:
        return clean
    return ''


@lru_cache(maxsize=64)
def ensure_threejs_and_doctype(html: str) -> str:
    if not html:
        return ''
    if re.search(r'(?i)<!doctype\s+html>', html):
        if 'three.min.js' in html.lower() or 'three.js' in html.lower():
            return html
        if '</head>' in html.lower():
            return re.sub(r'(?i)</head>', f"{THREE_R128}\n</head>", html, count=1)
        else:
            return THREE_R128 + '\n' + html
    wrapped = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
{THREE_R128}
</head>
<body>
{html}
</body>
</html>'''
    return wrapped


class Orchestrator:
    def __init__(self, thread_pool_size: int = 4):
        self.adapter = GeminiAdapter()
        self.thread_pool = ThreadPoolExecutor(max_workers=thread_pool_size)
        self.task_timings: Dict[str, float] = {}

    async def orchestrate_generation(self, prompt: str, game_id: str, timeout_seconds: int = 15,
                                     progress_callback: Optional[Callable[[int, str], Coroutine[Any, Any, None]]] = None) -> Dict[str, Any]:
        """
        Orchestrate entire game generation pipeline with concurrent execution and progress streaming.
        
        Flow:
        1. Parse & validate prompt (0% -> 10%)
        2. Generate AI content (10% -> 40%)
        3. Extract HTML candidate (40% -> 50%)
        4. Compile C++ if present (50% -> 70%)
        5. Build Three.js bundle (70% -> 100%)
        
        Target: 5-8 seconds end-to-end
        """
        start_time = time.time()
        task_start = start_time
        
        # Register progress callback if provided
        if progress_callback:
            register_progress_callback(game_id, progress_callback)
        
        try:
            # PHASE 1: Parse & validation (0-10%)
            await emit_progress(game_id, 0, "Initializing pipeline...")
            await asyncio.sleep(0.01)  # Yield control
            
            if not prompt or len(prompt.strip()) < 2:
                raise ValueError("Invalid prompt provided")
            
            await emit_progress(game_id, 10, "Prompt validated, generating content...")
            
            # PHASE 2: AI generation in thread pool (10-40%)
            loop = asyncio.get_event_loop()
            try:
                raw = await asyncio.wait_for(
                    loop.run_in_executor(self.thread_pool, self.adapter.generate, prompt, timeout_seconds),
                    timeout=timeout_seconds + 2
                )
            except asyncio.TimeoutError:
                logger.warning(f"Generation timeout for {game_id}")
                raw = ''
            except Exception as e:
                logger.error(f"Generation error: {e}")
                raw = ''
            
            await emit_progress(game_id, 40, "Content generated, extracting HTML...")
            
            # PHASE 3: Extract & validate HTML (40-50%)
            candidate = _extract_html_candidate(raw)
            candidate = _strip_markdown_and_quotes(candidate)
            candidate = ensure_threejs_and_doctype(candidate)
            
            valid = False
            if candidate and re.search(r'(?i)<!doctype\s+html>', candidate):
                if 'three.min.js' in candidate.lower() or 'three.js' in candidate.lower():
                    valid = True
            
            await emit_progress(game_id, 50, "HTML validated, checking for C++ blocks...")
            
            # PHASE 4: Extract C++ and prepare for compilation (50-70%)
            cpp_source = None
            m_cpp = re.search(r'```(?:cpp|c\+\+|c\+\+11)?\s*(.*?)```', raw, flags=re.DOTALL|re.IGNORECASE)
            if m_cpp:
                cpp_source = m_cpp.group(1).strip()
                logger.info(f"C++ code detected for {game_id}, queueing compilation")
            
            if not cpp_source:
                m2 = re.search(r'(?is)<pre><code[^>]*>(.*?)</code></pre>', raw)
                if m2 and ('#include' in m2.group(1) or 'int main' in m2.group(1)):
                    cpp_source = re.sub(r'<[^>]+>', '', m2.group(1)).strip()
            
            if not valid:
                candidate = FALLBACK_ARENA % THREE_R128
            
            final_html = ensure_threejs_and_doctype(candidate)
            await emit_progress(game_id, 70, "Building Three.js bundle...")
            
            # PHASE 5: Concurrent build tasks (70-100%)
            # Run build and optional WASM compilation in parallel
            build_tasks = []
            
            # Primary build task
            build_task = asyncio.create_task(
                create_threejs_build(final_html, game_id, cpp_source=cpp_source, compile_target='web')
            )
            build_tasks.append(build_task)
            
            # Wait for all build tasks with progress
            try:
                results = await asyncio.gather(*build_tasks, return_exceptions=True)
                build_info = results[0] if not isinstance(results[0], Exception) else None
                if build_info is None or isinstance(build_info, Exception):
                    logger.error(f"Build failed: {build_info}")
                    final_html = FALLBACK_ARENA % THREE_R128
                    build_info = await create_threejs_build(final_html, game_id, cpp_source=None)
            except Exception as e:
                logger.error(f"Build error: {e}")
                final_html = FALLBACK_ARENA % THREE_R128
                build_info = await create_threejs_build(final_html, game_id, cpp_source=None)
            
            await emit_progress(game_id, 100, "Pipeline complete!")
            
            elapsed = time.time() - task_start
            logger.info(f"Generation complete for {game_id} in {elapsed:.2f}s")
            
            result = {
                'status': 'SUCCESS',
                'result': {
                    'final_build': final_html,
                    'download_url': build_info.get('download_url') if build_info else None,
                    'elapsed_seconds': elapsed
                }
            }
            
            if build_info and build_info.get('compile_info'):
                result['result']['compile_info'] = build_info['compile_info']
            
            return result
        
        except Exception as e:
            logger.exception(f"Orchestration failed for {game_id}: {e}")
            elapsed = time.time() - task_start
            await emit_progress(game_id, 0, f"Error: {str(e)[:50]}")
            return {
                'status': 'FAILED',
                'result': {'error': str(e), 'elapsed_seconds': elapsed}
            }


_default_orchestrator = Orchestrator()


async def generate_game_and_export(prompt: str, game_id: str,
                                   progress_callback: Optional[Callable[[int, str], Coroutine[Any, Any, None]]] = None) -> Dict[str, Any]:
    """Public interface for game generation with optional progress streaming."""
    return await _default_orchestrator.orchestrate_generation(prompt, game_id, progress_callback=progress_callback)
