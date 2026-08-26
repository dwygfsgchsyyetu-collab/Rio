from typing import Dict, List

def select_assets(uploaded_assets_store: Dict[str, Dict]) -> List[Dict]:
    """Selects best assets (model -> image -> audio) from the uploaded store.
    Returns list of assets with keys: id, name, path, ext
    """
    assets = []
    for aid, meta in uploaded_assets_store.items():
        name = meta.get('name', aid)
        size = meta.get('size', 0)
        # assume data saved on disk earlier by upload logic
        path = meta.get('path') or meta.get('tmp_path') or None
        ext = '.' + name.split('.')[-1].lower() if '.' in name else ''
        assets.append({'id': aid, 'name': name, 'size': size, 'path': path or name, 'ext': ext})

    # priority: .glb/.gltf, then images, then audio
    model = next((a for a in assets if a['ext'] in ['.glb', '.gltf']), None)
    image = next((a for a in assets if a['ext'] in ['.png', '.jpg', '.jpeg']), None)
    audio = next((a for a in assets if a['ext'] in ['.mp3', '.wav', '.ogg']), None)

    chosen = []
    if model: chosen.append(model)
    if image: chosen.append(image)
    if audio: chosen.append(audio)

    # fallback: include top 3 assets
    if not chosen:
        assets_sorted = sorted(assets, key=lambda x: x['size'], reverse=True)
        chosen = assets_sorted[:3]

    return chosen
