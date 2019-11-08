import json
from typing import Dict, Any


def merge(new_values, default_values):
    nd = {}
    for key, value in default_values.items():
        nv = new_values.get(key, None)
        if isinstance(value, dict) and isinstance(nv, dict):
            nd[key] = merge(value, nv)
        else:
            if nv is None:
                nd[key] = value
            else:
                nd[key] = nv
    for key, value in new_values.items():
        if key not in default_values:
            nd[key] = value
    return nd


class MessageType:
    def __init__(self, type, data_dict=None, decode_function=None):
        self.decode_function = decode_function
        if data_dict is None:
            data_dict = {}
        self.data_dict = data_dict
        self.type = type

    def encode(self, **kwargs):
        return json.dumps(
            {"type": self.type, "data": merge({**kwargs}, self.data_dict)}
        )

    def decode(self, consumer, data=None):
        if data is None:
            data = {}
        # try:
        self.decode_function(consumer=consumer, **data)
        # except:
        #    raise NotImplementedError(f"no decoder for {type}")


def error_message(consumer, message=None):
    print(consumer, message)


MESSAGETYPES = {"error": MessageType(type="error", decode_function=error_message)}


class AbstractJsonWebsocket:
    message_types: Dict[str, MessageType]

    def __init__(self):
        self.message_types = {}
        self.available_cmds = {}

        for n, t in MESSAGETYPES.items():
            self.set_message_type(n, t)

    def set_message_type(self, name, message_type: MessageType):
        self.message_types[name] = message_type

    def on_open(self):
        print("open")

    def on_close(self, code=None, reason=None):
        if reason is not None or code is not None:
            print("Close socket", code, reason)

    def on_error(self, e):
        print("Socket error:", e)

    def on_message(self, data):
        text_data = json.loads(data)
        self.message_types[text_data["type"]].decode(
            consumer=self, data=text_data["data"]
        )

    def error_message(self, message):
        return self.message_types["error"].encode(message=message)

    @classmethod
    def generate_javascript(cls, result):
        with open(result, "w+") as f:
            f.write(cls._generate_js())

    @classmethod
    def _generate_js(cls, s=""):
        import os
        import sys

        for base in cls.__bases__:
            if hasattr(base, "_generate_js"):
                s = base._generate_js(s) + "\n"
        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(sys.modules[cls.__module__].__file__)),
                "websocket_data.js",
            ),
            "r+",
        ) as f:
            s = s + f.read()
        return s
