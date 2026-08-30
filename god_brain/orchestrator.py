import os
import re
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from .api_nexus import GeminiAdapter
from game_compilers.universal_builder import create_threejs_build

# Export path base
EXPORTS_ROOT = Path(os.environ.get('EXPORTS_ROOT', 'exports'))
EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)

THREE_R128 = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'

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


def _strip_markdown_and_quotes(text: str) -> str:
    """Aggressively strip markdown fences and outer quoting from assistant outputs."""
    if not text:
        return ''
    text = re.sub(r"```(?:html|javascript|js)?\s*", '', text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", '', text)
    text = re.sub(r'^\s*["\']+', '', text)
    text = re.sub(r'["\']+\s*$', '', text)
    text = re.sub(r'^(assistant:|output:|answer:)\s*', '', text, flags=re.IGNORECASE)
    return text.strip()


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
    wrapped = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8"/>\n<meta name="viewport" content="width=device-width,initial-scale=1"/>\n' + THREE_R128 + '\n</head>\n<body>\n' + html + '\n</body>\n</html>'
    return wrapped


class Orchestrator:
    def __init__(self):
        self.adapter = GeminiAdapter()

    async def orchestrate_generation(self, prompt: str, game_id: str, timeout_seconds: int = 15) -> Dict[str, Any]:
        start = time.time()
        # Run adapter.generate in threadpool to avoid blocking
        try:
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, self.adapter.generate, prompt, timeout_seconds)
        except Exception:
            raw = ''

        candidate = _extract_html_candidate(raw)
        candidate = _strip_markdown_and_quotes(candidate)
        candidate = ensure_threejs_and_doctype(candidate)

        valid = False
        if candidate and re.search(r'(?i)<!doctype\s+html>', candidate):
            if 'three.min.js' in candidate.lower() or 'three.js' in candidate.lower():
                valid = True

        # Detect embedded C++ block markers to compile
        cpp_source = None
        # If the raw output contains ```cpp or .cpp content, extract
        m_cpp = re.search(r'```(?:cpp|c\+\+|c\+\+11)?\s*(.*?)```', raw, flags=re.DOTALL|re.IGNORECASE)
        if m_cpp:
            cpp_source = m_cpp.group(1).strip()
        # Also accept <code class="language-cpp"> blocks
        if not cpp_source:
            m2 = re.search(r'(?is)<pre><code[^>]*>(.*?)</code></pre>', raw)
            if m2 and ('#include' in m2.group(1) or 'int main' in m2.group(1)):
                cpp_source = re.sub(r'<[^>]+>', '', m2.group(1)).strip()

        if not valid:
            candidate = FALLBACK_ARENA % THREE_R128

        final_html = ensure_threejs_and_doctype(candidate)

        # Pass to universal builder which will optionally compile C++ to Wasm
        try:
            build_info = await create_threejs_build(final_html, game_id, cpp_source=cpp_source, compile_target='web')
        except Exception as e:
            # On builder failure, fallback to writing simple arena
            final_html = FALLBACK_ARENA % THREE_R128
            build_info = await create_threejs_build(final_html, game_id, cpp_source=None)

        result = {
            'status': 'SUCCESS',
            'result': {
                'final_build': final_html,
                'download_url': build_info.get('download_url')
            }
        }
        # include compile_info for debugging
        if build_info.get('compile_info'):
            result['result']['compile_info'] = build_info['compile_info']

        return result


_default_orchestrator = Orchestrator()


async def generate_game_and_export(prompt: str, game_id: str) -> Dict[str, Any]:
    return await _default_orchestrator.orchestrate_generation(prompt, game_id)
