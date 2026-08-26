import zipfile
import shutil
import os
from typing import List, Dict
from pathlib import Path

THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.154.0/build/three.min.js"
GLTF_LOADER = "https://cdn.jsdelivr.net/npm/three@0.154.0/examples/js/loaders/GLTFLoader.js"
HOWLER_CDN = "https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.3/howler.min.js"
NIPPLE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.8.1/nipplejs.min.js"

EXPORTS_DIR = Path('exports')
EXPORTS_DIR.mkdir(exist_ok=True)


def create_threejs_build(build_id: str, assets: List[Dict], title: str = "God Node Build") -> Dict:
    build_dir = EXPORTS_DIR / build_id
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    # copy asset files into build_dir
    for a in assets:
        src = Path(a['path'])
        if src.exists():
            shutil.copy(src, build_dir / src.name)

    # Generate HTML
    model = next((a for a in assets if a['ext'] in ['.glb', '.gltf']), None)
    image = next((a for a in assets if a['ext'] in ['.png', '.jpg', '.jpeg']), None)
    audio = next((a for a in assets if a['ext'] in ['.mp3', '.wav', '.ogg']), None)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>{title}</title>
  <style>body{{margin:0;overflow:hidden;background:#eef6ff}}</style>
</head>
<body>
  <div id='overlay' style='position:absolute;left:8px;top:8px;padding:8px;background:rgba(255,255,255,0.8);z-index:10'>{title}</div>
  <script src='{THREE_CDN}'></script>
  <script src='{GLTF_LOADER}'></script>
  <script src='{HOWLER_CDN}'></script>
  <script src='{NIPPLE_CDN}'></script>
  <script>
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({antialias:true});
    renderer.setSize(window.innerWidth, window.innerHeight);
    document.body.appendChild(renderer.domElement);

    const light = new THREE.HemisphereLight(0xffffff, 0x444444, 1.2);
    scene.add(light);
    camera.position.set(0,1.6,3);

    function animate(){ requestAnimationFrame(animate); renderer.render(scene, camera); }

"""
    if model:
        html += f"\n    const loader = new THREE.GLTFLoader();\n    loader.load('{Path(model['path']).name}', function(gltf){{ scene.add(gltf.scene); }}, undefined, function(e){{console.error(e);}});\n"
    else:
        html += "\n    const geom = new THREE.BoxGeometry(1.4,1.4,1.4); const mat = new THREE.MeshStandardMaterial({color:0x0077ff}); const mesh = new THREE.Mesh(geom, mat); scene.add(mesh); mesh.rotation.y=0.5;\n"

    if audio:
        html += f"\n    const sound = new Howl({{src:['{Path(audio['path']).name}'], autoplay:false, loop:true}});\n    const btn = document.createElement('button'); btn.textContent='Play Music'; btn.style.position='absolute'; btn.style.right='12px'; btn.style.bottom='12px'; btn.onclick=()=>sound.play(); document.body.appendChild(btn);\n"

    html += "\n    window.addEventListener('resize', ()=>{camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight);}); animate();\n  </script>\n</body>\n</html>"

    index_path = build_dir / 'index.html'
    index_path.write_text(html, encoding='utf-8')

    # create zip
    zip_path = EXPORTS_DIR / f"{build_id}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in build_dir.rglob('*'):
            zf.write(p, arcname=p.relative_to(build_dir))

    # return URLs (served by StaticFiles mount)
    return { 'build_dir': str(build_dir), 'preview': f'/exports/{build_id}/index.html', 'zip': f'/exports/{build_id}.zip' }
