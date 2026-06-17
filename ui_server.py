import asyncio
import websockets
import json

CLIENTS = set()

async def handler(websocket):
    # İstemciyi kaydet
    CLIENTS.add(websocket)
    try:
        async for message in websocket:
            # Bir mesaj alındı (muhtemelen jarvis.py'den)
            # Diğer tüm istemcilere (UI arayüzü gibi) yayınla
            targets = [c for c in CLIENTS if c != websocket]
            if targets:
                websockets.broadcast(targets, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # İstemci kaydını kaldır
        CLIENTS.remove(websocket)

async def main():
    print("[UI Server] Starting WebSocket broker on ws://127.0.0.1:7474")
    async with websockets.serve(handler, "127.0.0.1", 7474):
        await asyncio.Future()  # sonsuza kadar çalıştır

if __name__ == "__main__":
    asyncio.run(main())
