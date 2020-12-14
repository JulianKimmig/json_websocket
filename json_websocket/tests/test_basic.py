import asyncio
import threading
import unittest

from time import sleep
from websocket import WebSocketConnectionClosedException

from json_websocket.basic.websocket import websocket_JsonWebsocket
from json_websocket.server.async_server import WebsocketServer


class WebsocketTest(unittest.TestCase):

    def test_start_websocket(self):
        jws = websocket_JsonWebsocket("invalidurl")
        #jws.start()
        def _f():
            jws.send("ws://helllo")
        self.assertRaises(WebSocketConnectionClosedException, _f)

    def test_start_webserver(self):
        wss = WebsocketServer(port=2342,auto_connect=False)
        async def _r():
            await asyncio.sleep(0.3)
            wss.close()
        asyncio.get_event_loop().create_task(_r())
        wss.open_websocket()


    def test_websocket_to_server(self):
        wss = WebsocketServer()
        jws = websocket_JsonWebsocket(f"ws://{wss.host}:{wss.port}")

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            asyncio.get_event_loop().create_task(wss.open_websocket(return_awaitable=True))
            sleep(0.3)
            wss.close()

        threading.Thread(target=_run).start()
        sleep(0.1)
        jws.start_forever()
        sleep(0.1)
        jws.send("huhu")
        jws.stop()

    def test_ping_pong(self):
        wss = WebsocketServer()
        jws = websocket_JsonWebsocket(f"ws://{wss.host}:{wss.port}")

        async def _on_message(data, source):
            await source.send("pong")
        wss.on_message=_on_message
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            asyncio.get_event_loop().create_task(wss.open_websocket(return_awaitable=True))
            sleep(0.5)
            wss.close()

        t = threading.Thread(target=_run)
        t.start()
        sleep(0.1)
        jws.start_forever()
        sleep(0.1)
        jws.send("ping")
        sleep(0.1)
        jws.stop()
        wss.close()
        assert t.is_alive()


