from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# very simple in-memory pub/sub for editor clients
SUBSCRIBERS = {}

@router.websocket('/ws/editor/{game_id}')
async def ws_editor(ws: WebSocket, game_id: str):
    await ws.accept()
    SUBSCRIBERS.setdefault(game_id, set()).add(ws)
    try:
        while True:
            data = await ws.receive_text()
            # broadcast to other clients
            for s in list(SUBSCRIBERS.get(game_id, [])):
                if s is not ws:
                    try:
                        await s.send_text(data)
                    except Exception:
                        try:
                            await s.close()
                        except Exception:
                            pass
    except WebSocketDisconnect:
        SUBSCRIBERS.get(game_id, set()).discard(ws)
    except Exception:
        SUBSCRIBERS.get(game_id, set()).discard(ws)
