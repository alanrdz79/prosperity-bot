import json, asyncio
try:
    import websockets
except ImportError:
    print("pip install websockets")
    exit()

async def test():
    async with websockets.connect('wss://demo-ws-api.binance.com/ws-api/v3') as ws:
        await ws.send(json.dumps({'id':'1','method':'account.status','params':{'apiKey':'obR4jfbaZ07jeQkALqOFjAZBgmXkfbdtthAOFu2XKKRFVofZ5pOvVuOW9uK9K9lb'}}))
        print(await ws.recv())

asyncio.run(test())
