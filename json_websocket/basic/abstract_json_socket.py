import asyncio
import inspect
import json
import os
import random
import string
import sys
import threading
from time import time, sleep
from typing import Dict

WITH_NUMPY = True
try:
    import numpy as np
except:
    WITH_NUMPY = False


class DefaultEncoder(json.JSONEncoder):
    def default(self, obj):
        if WITH_NUMPY:
            if isinstance(obj, np.ndarray):
                return obj.tolist()

            try:
                if hasattr(obj, 'dtype'):
                    return obj.item()
            except:
                pass

            if isinstance(obj, (np.uint64, np.int64)):
                return str(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)

        return super().default(obj)


def assure_coro(call):
    if not inspect.iscoroutinefunction(call):
        async def _f(*args, **kwargs):
            return call(*args, **kwargs)

        return _f
    else:
        return call


class Promise():
    def __init__(self):
        self.isPending = True
        self.isFulfilled = False
        self.isRejected = False
        self.reject_func = None
        self.fulfill_func = None
        self.child = None

    def then(self, fulfill_func, reject_func):
        self.fulfill_func = fulfill_func
        self.reject_func = reject_func
        self.child = Promise()
        return self.child

    async def async_reject(self, *args, **kwargs):
        if self.reject_func:
            await self.reject_func(*args, **kwargs)
        else:
            print("REJECT:", args, kwargs)
        self._post_reject()

    def reject(self, *args, **kwargs):
        if self.reject_func:
            self.reject_func(*args, **kwargs)
        else:
            print("REJECT:", args, kwargs)
        self._post_reject()

    def _post_reject(self):
        self.isPending = False
        self.isRejected = True
        self.isFulfilled = False

    async def async_fulfill(self, *args, **kwargs):
        if self.fulfill_func:
            try:
                await self.child.async_fulfill(await self.fulfill_func(*args, **kwargs))
            except Exception as e:
                await self.child.reject(e)
        self._post_fulfill()

    def fulfill(self, *args, **kwargs):
        if self.fulfill_func:
            try:
                self.child.fulfill(self.fulfill_func(*args, **kwargs))
            except Exception as e:
                self.child.reject(e)
        self._post_fulfill()

    def _post_fulfill(self):
        self.isPending = False
        self.isRejected = False
        self.isFulfilled = True


class OutMessage(Promise):
    def __init__(self, message_str, resends, timeout):
        super().__init__()
        self.resends = resends
        self.timeout = timeout
        self.message_str = message_str
        self.reject_func = lambda error: print("REJECT:", self.message_str, "because of", error)

    async def async_try_send_out(self, send_function):
        send_function = assure_coro(send_function)

        async def _send_out():
            await send_function(self.message_str)
            st = time()
            while time() - st < self.timeout and self.isPending:
                await asyncio.sleep(0.1)
            if self.resends > 0 and self.isPending:
                self.resends -= 1
                await _send_out()
            else:
                if self.isPending:
                    await self.async_reject("timeout")

        await _send_out()

    def try_send_out(self, send_function):
        def _send_out():
            send_function(self.message_str)
            st = time()
            while time() - st < self.timeout and self.isPending:
                sleep(0.1)
            if self.resends > 0 and self.isPending:
                self.resends -= 1
                _send_out()
            else:
                if self.isPending:
                    self.reject("timeout")

        threading.Thread(target=_send_out, daemon=True).start()


class AbstractJsonWebsocket:

    def __init__(self, default_cls=DefaultEncoder, use_asyncio=False,*args,**kwargs):
        super(AbstractJsonWebsocket, self).__init__(*args,**kwargs)
        self.use_asyncio = use_asyncio
        self._default_cls = default_cls
        self.message_types = {}
        self.open = False
        self.answers_pending = {}
        self.ANSWER_TIMEOUT = 5000
        self.send_function = None
        if use_asyncio:
            self.add_type_function("error", self.async_receive_error_message)
            self.add_type_function("ans", self.async_receive_ans)
            self.send_type_message = self.async_send_type_message
            if not hasattr(self,"on_message"):
                self.on_message = self.async_on_message

        else:
            self.add_type_function("error", self.receive_error_message)
            self.add_type_function("ans", self.receive_ans)

            self.send_type_message = self.sync_send_type_message
            if not hasattr(self,"on_message"):
                self.on_message = self.sync_on_message

    async def async_receive_error_message(self, data):
        print(self, data["data"])

    def receive_error_message(self, data):
        print(self, data["data"])

    async def async_receive_ans(self, data):
        ans = data["data"]
        if ans['id'] in self.answers_pending:
            out_message = self.answers_pending[ans['id']]
            if ans["success"]:
                await out_message.fulfill(ans["data"])
            else:
                await out_message.reject(ans["data"])
            del self.answers_pending[ans['id']]

    def receive_ans(self, data):
        ans = data["data"]
        if ans['id'] in self.answers_pending:
            out_message = self.answers_pending[ans['id']]
            if ans["success"]:
                out_message.fulfill(ans["data"])
            else:
                out_message.reject(ans["data"])
            del self.answers_pending[ans['id']]

    def _generate_out_message(self, type, data=None, expect_response=False,
                              timeout=-1, resends=0, target=None, cls=None, source=None):
        if source is None:
            source = []
        if data is None:
            data = {}
        if cls is None:
            cls = self._default_cls

        if self.send_function is None:
            raise ValueError("please set send_function before you send something")
        message = self.get_type_message(type=type, data=data)
        if expect_response:
            message['id'] = ''.join([random.choice(string.ascii_letters) for i in range(5)]) + str(int(time() * 1000))
        if target is not None:
            message["target"] = target
            message['source'] = source
        message_str = json.dumps(message, cls=cls)
        out_message = OutMessage(message_str, resends=resends,
                                 timeout=(timeout if timeout > 0 else self.ANSWER_TIMEOUT) / 1000)
        if expect_response:
            self.answers_pending[message['id']] = out_message

        return out_message, expect_response

    async def async_send_type_message(self, *args, **kwargs):
        out_message, expect_response = self._generate_out_message(*args, **kwargs)
        if not expect_response:
            await out_message.async_fulfill()
        await out_message.async_try_send_out(self.send_function)
        return out_message

    def sync_send_type_message(self, *args, **kwargs):
        out_message, expect_response = self._generate_out_message(*args, **kwargs)
        if not expect_response:
            out_message.fulfill()
        out_message.try_send_out(self.send_function)
        return out_message

    async def async_on_message(self, data):
        if isinstance(data, str):
            data = json.loads(data)
        succ = False
        if "type" in data:
            if data["type"] in self.message_types:
                try:
                    ans = await self.message_types[data["type"]](data)
                    succ = True
                except Exception as e:
                    ans = str(e)
            else:
                ans = "message type '{}' not defined!".format(data["type"])
        else:
            ans = "no 'type' in data!"
        if "id" in data:
            return await self.async_send_answer_message(ans, id=data["id"], success=succ,
                                                        target=(data['source'][0] if 'source' in data else None))

    def sync_on_message(self, data):
        if isinstance(data, str):
            data = json.loads(data)
        try:
            ans = self.message_types[data["type"]](data)
            succ = True
        except Exception as e:
            ans = str(e)
            succ = False
        if "id" in data:
            return self.sync_send_answer_message(ans, id=data["id"], success=succ,
                                                 target=(data['source'][0] if 'source' in data else None))

    async def async_send_answer_message(self, ans, id, success=True, **kwargs):
        return await self.async_send_type_message("ans", data={'id': id, 'success': success, "data": ans}, **kwargs)

    def sync_send_answer_message(self, ans, id, success=True, **kwargs):
        return self.sync_send_type_message("ans", data={'id': id, 'success': success, "data": ans}, **kwargs)

    def add_type_function(self, name, message_type_call):
        if self.use_asyncio:
            message_type_call = assure_coro(message_type_call)
        self.message_types[name] = message_type_call

    def get_type_message(self, type, data):
        message = {'type': type, 'data': data}
        return message

    def error_message(self, message):
        return self.message_types["error"].encode(message=message)

    def on_open(self):
        self.open = True
        print(f"open {self}")

    def on_close(self, code=None, reason=None):
        self.open = False
        if reason is not None or code is not None:
            print("Close socket", code, reason)

    def on_error(self, e):
        self.open = False
        print("Socket error:", e)

    @classmethod
    def generate_static_files(cls, direction):
        cls.generate_javascript(os.path.join(direction, "websocket.js"))
        cls.generate_stylesheet(os.path.join(direction, "websocket.css"))

    @classmethod
    def generate_javascript(cls, result):
        with open(result, "w+") as f:
            f.write(cls._generate_js())

    @classmethod
    def generate_stylesheet(cls, result):
        with open(result, "w+") as f:
            f.write(cls._generate_css())

    @classmethod
    def _generate_js(cls, s=""):
        for base in cls.__bases__:
            if hasattr(base, "_generate_js"):
                s = base._generate_js(s) + "\n"

        jsfile = os.path.join(
            os.path.dirname(os.path.abspath(sys.modules[cls.__module__].__file__)),
            "websocket_data.js",
        )
        if os.path.exists(jsfile):
            with open(jsfile, "r", ) as f:
                s = s + f.read()
        return s

    @classmethod
    def _generate_css(cls, s=""):
        for base in cls.__bases__:
            if hasattr(base, "_generate_css"):
                s = base._generate_css(s) + "\n"
        stylefile = os.path.join(
            os.path.dirname(os.path.abspath(sys.modules[cls.__module__].__file__)),
            "websocket_styles.css",
        )
        if os.path.exists(stylefile):
            with open(stylefile, "r", ) as f:
                s = s + f.read()
        return s
