import asyncio
import threading
import time

import websocket

from .abstract_json_socket import AbstractJsonWebsocket

SLEEP_TIME = 0.1


def realize_abstract_websocket(abstract_json_websocket, url, header=None,
                               reconnect_time=5,
                               *args, **kwargs
                               ):
    asbws = abstract_json_websocket(*args, **kwargs)

    class _WS(websocket.WebSocketApp):
        def __init__(self, url, **kwargs):
            super().__init__(url, header=header,
                             on_error=self.on_error,
                             on_open=self.on_open,
                             on_message=self.on_message,
                             on_close=self.on_close)

        def on_message(self, data):
            return asbws.on_message(data)

        def on_open(self):
            return asbws.on_open()

        def on_error(self, e):
            return asbws.on_error(e)

        def on_close(self, code=None, reason=None):
            return asbws.on_close(code=code, reason=reason)

    def send(data):
        asbws.ws.send(data)

    asbws.send_function = send

    def start(in_background=True):
        if in_background:
            threading.Thread(target=asbws.ws.run_forever, daemon=True).start()
        else:
            asbws.ws.run_forever()

    asbws.start = start

    def stop():
        asbws.ws.close()
        asbws.running = False

    asbws.stop = stop

    def start_forever(in_background=True):
        if asbws.use_asyncio:
            async def _async_forever():
                asbws.running = True
                while asbws.running:
                    asbws.start(in_background=False)
                    st = time.time()
                    while time.time() - st < asbws.reconnect_time and asbws.running:
                        await asyncio.sleep(SLEEP_TIME)

            asbws.asycio_loop = asyncio.get_event_loop()
            t = asbws.asycio_loop.create_task(_async_forever())
            if in_background:
                asbws.asycio_loop.run_until_complete(t)
            else:
                return t
        else:
            def _forever():
                asbws.running = True
                while asbws.running:
                    asbws.start(in_background=False)
                    st = time.time()
                    while time.time() - st < asbws.reconnect_time and asbws.running:
                        time.sleep(SLEEP_TIME)

            t = threading.Thread(target=_forever, daemon=True)
            if in_background:
                t.start()
            else:
                t.run()

    asbws.start_forever = start_forever

    asbws.ws = _WS(url=url)

    asbws.reconnect_time = reconnect_time
    asbws.asycio_loop = None
    asbws.running = False
    return asbws


websocket_JsonWebsocket = lambda *args, **kwargs: realize_abstract_websocket(AbstractJsonWebsocket,*args, **kwargs)