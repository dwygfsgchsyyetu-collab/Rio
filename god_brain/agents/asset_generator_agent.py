import base64

# Simple asset generator that writes a 1x1 transparent PNG if missing
PLACEHOLDER_PNG_BASE64 = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='


def ensure_placeholder_assets(uploaded_assets_store: dict):
    # If no image asset exists, insert a placeholder image
    has_image = any(v.get('name','').lower().endswith(('.png','.jpg','.jpeg')) for v in uploaded_assets_store.values())
    if not has_image:
        aid = 'asset_placeholder_img'
        uploaded_assets_store[aid] = {
            'name': 'placeholder.png',
            'size': len(PLACEHOLDER_PNG_BASE64),
            'data': base64.b64decode(PLACEHOLDER_PNG_BASE64),
            'path': 'placeholder.png'
        }
    # If no model, do nothing — builder will create default cube in HTML
    has_audio = any(v.get('name','').lower().endswith(('.mp3','.wav','.ogg')) for v in uploaded_assets_store.values())
    if not has_audio:
        # no-op; audio optional
        pass
