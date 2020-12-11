import inspect

from ..basic.abstract_json_socket import AbstractJsonWebsocket


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
    return nd


class WebsocketCommand():
    def __init__(self, name, func, raw=False,callback=None):
        self.raw = raw
        self.func = func
        self.name = name
        args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations = inspect.getfullargspec(self.func)
        len_defaults = 0
        if defaults is not None:
            len_defaults = len(defaults)
        self.func_args = args[:len(args) - len_defaults]
        if len_defaults:
            self.func_kwargs = dict(zip(args[-len_defaults:], defaults))
        else:
            self.func_kwargs = {}

        self.callback=callback

        if kwonlydefaults is not None:
            self.func_kwargs.update(kwonlydefaults)

        self.func_with_kwargs = varkw is not None
        self.typing = annotations

    def __call__(self, consumer, data):
        kwargs = {'consumer': consumer}
        kwargs.update(self.func_kwargs)
        if self.raw:
            data = data
        else:
            data = data['data']['data']
        kwargs.update(data)
        if not self.func_with_kwargs:
            kwargs = {k: v for k, v in kwargs.items() if k in self.func_args + list(self.func_kwargs.keys())}

        res = self.func(**kwargs)
        if self.callback is not None:
            res = self.callback(res)

        return res

    def info(self):
        return {'args': self.func_args,
                'kwargs': self.func_kwargs,
                'typing': {k: (v.__name__ if inspect.isclass(v) else str(v)) for k, v in self.typing.items()},
                'doc':self.func.__doc__.strip() if self.func.__doc__ else None,
                }


class AbstractCmdJsonWebsocket(AbstractJsonWebsocket):
    def __init__(self):
        super().__init__()
        self._available_cmds = {}
        self.add_type_function("cmd", self.run_cmd)

    def run_cmd(self, base_data):
        data = base_data["data"]
        f = self.get_cmd(data['cmd'])
        if f is None:
            raise AttributeError("cmd '"+str(data['cmd']) + "' not found")

        return f(self, base_data)

    def get_cmd(self, cmd):
        return self._available_cmds.get(cmd)

    def set_cmd(self, cmd, func):
        if not isinstance(func, WebsocketCommand):
            func = WebsocketCommand(cmd, func)
        self._available_cmds[cmd] = func

    def get_cmd_message(self, cmd, data=None):
        if data is None:
            data = {}
        return self.get_type_message("cmd", {'cmd': cmd, 'data': data})

    def send_cmd_message(self, cmd, data=None, expect_response=True, **kwargs):
        if data is None:
            data = {}
        send_data = {'cmd': cmd, 'data': data}
        return self.send_type_message(type="cmd", data=send_data, expect_response=expect_response, **kwargs)

    def get_available_cmds(self):
        return {cmd: callfunc.info() for cmd, callfunc in self._available_cmds.items()}
