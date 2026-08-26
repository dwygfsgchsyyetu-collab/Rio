"""
Universal Three.js builder
- Generates fully standalone index.html using Three.js r128+, GLTFLoader, Howler, Nipple.js
- Supports WASM Rapier if provided via CDN
- Saves to /exports/{game_id}/index.html and packages zip
"""
import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Dict

EXPORTS_DIR = Path("exports")
EXPORTS_DIR.mkdir(exist_ok=True)

THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"
GLTF_LOADER = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"
HOWLER_CDN = "https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.3/howler.min.js"
NIPPLE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.8.1/nipplejs.min.js"
RAPIER_WASM = "https://cdn.jsdelivr.net/npm/@dimforge/rapier3d@0.10.3/rapier3d.wasm"
RAPIER_JS = "https://cdn.jsdelivr.net/npm/@dimforge/rapier3d@0.10.3/rapier3d.js"


def _ensure_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def create_threejs_build(game_id: str, assets: List[Dict], title: str = "God Node Build") -> Dict[str, str]:
    """Creates a standalone Three.js HTML build and zip bundle.
    assets: list of dicts with keys: name, path, ext
    Returns dict with preview and zip paths relative to static server
    """
    build_dir = EXPORTS_DIR / game_id
    _ensure_dir(build_dir)

    # Copy assets into build_dir
    for a in assets:
        src = Path(a.get("path"))
        if src.exists():
            shutil.copy(src, build_dir / src.name)

    # Determine default model, image, audio
    model = next((a for a in assets if a.get("ext") in [".glb", ".gltf"]), None)
    audio = next((a for a in assets if a.get("ext") in [".mp3", ".wav", ".ogg"]), None)

    index_html = build_dir / "index.html"
    with open(index_html, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>{title}</title>\n<style>html,body{{height:100%;margin:0}}#overlay{{position:absolute;left:8px;top:8px;padding:8px;background:rgba(255,255,255,0.85);color:#000;z-index:10;border-radius:6px}}</style>\n</head>\n<body>\n<div id=\"overlay\">{title}</div>\n<script src=\"{THREE_CDN}\"></script>\n<script src=\"{GLTF_LOADER}\"></script>\n<script src=\"{HOWLER_CDN}\"></script>\n<script src=\"{NIPPLE_CDN}\"></script>\n<script src=\"{RAPIER_JS}\"></script>\n<script>\n// Basic scene setup\nconst scene = new THREE.Scene();\nscene.background = new THREE.Color(0xeceff1);\nconst camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);\nconst renderer = new THREE.WebGLRenderer({antialias:true});\nrenderer.shadowMap.enabled = true;\nrenderer.setSize(window.innerWidth, window.innerHeight);\ndocument.body.appendChild(renderer.domElement);\n\n// Lights\nconst ambient = new THREE.AmbientLight(0xffffff, 0.6); scene.add(ambient);\nconst dir = new THREE.DirectionalLight(0xffffff, 0.8); dir.position.set(3,10,4); dir.castShadow = true; scene.add(dir);\n\n// Floor grid\nconst grid = new THREE.GridHelper(20, 40, 0x888888, 0xcccccc); scene.add(grid);\n\n// Simple player box\nconst playerGeo = new THREE.BoxGeometry(1,1,1); const playerMat = new THREE.MeshStandardMaterial({color:0x0077ff}); const player = new THREE.Mesh(playerGeo, playerMat); player.position.y = 0.5; player.castShadow = true; scene.add(player);\n\n// Load model if available\n"")
        if model:
            f.write(f"\n// GLTF model load\nconst loader = new THREE.GLTFLoader();\nloader.load('{model['name']}', function(gltf){{ scene.add(gltf.scene); }}, undefined, function(err){{console.error('GLTF load error', err);}});\n")
        f.write("""

// Camera and controls
camera.position.set(0, 2, 5);
let move = {forward:0, right:0};
const speed = 0.06;

function handleKeys(){
  if(move.forward) player.position.z -= speed * move.forward;
  if(move.right) player.position.x += speed * move.right;
}

window.addEventListener('keydown', (e)=>{
  if(['w','W','ArrowUp'].includes(e.key)) move.forward = 1;
  if(['s','S','ArrowDown'].includes(e.key)) move.forward = -1;
  if(['a','A','ArrowLeft'].includes(e.key)) move.right = -1;
  if(['d','D','ArrowRight'].includes(e.key)) move.right = 1;
});
window.addEventListener('keyup', (e)=>{ if(['w','W','ArrowUp','s','S','ArrowDown'].includes(e.key)) move.forward=0; if(['a','A','ArrowLeft','d','D','ArrowRight'].includes(e.key)) move.right=0; });

// Mobile joystick using nipplejs
let joystick = null;
if (window.nipplejs){
  joystick = nipplejs.create({zone: document.body, mode: 'static', position: {left: '80px', bottom: '80px'}, color: 'black'});
  joystick.on('move', function(evt, data){ if(data && data.vector){ move.right = data.vector.x; move.forward = -data.vector.y; } });
  joystick.on('end', function(){ move.right = 0; move.forward = 0; });
}

// Audio
""")
        if audio:
            f.write(f"\nconst sound = new Howl({{src:['{audio['name']}'], html5:true}}); const playBtn = document.createElement('button'); playBtn.textContent='Play'; playBtn.style.position='absolute'; playBtn.style.right='12px'; playBtn.style.bottom='12px'; playBtn.onclick=()=>sound.play(); document.body.appendChild(playBtn);\n")
        f.write("""

// Basic animation loop
function animate(){ requestAnimationFrame(animate); handleKeys(); camera.position.lerp(new THREE.Vector3(player.position.x, player.position.y+2, player.position.z+5), 0.08); camera.lookAt(player.position); renderer.render(scene, camera); }
window.addEventListener('resize', ()=>{ camera.aspect = window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); });
animate();
</script>
</body>
</html>
""")

    # Create zip
    zip_path = EXPORTS_DIR / f"{game_id}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in build_dir.rglob('*'):
            zf.write(p, arcname=p.relative_to(build_dir))

    return {"preview": f"/exports/{game_id}/index.html", "zip": f"/exports/{game_id}.zip"}
