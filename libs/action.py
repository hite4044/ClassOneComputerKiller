from os import system
from libs.packets import *
from typing import Any, Dict, Literal, Type
import win32gui
import re

Packet = Dict[str, Any]


class ActionKind:
    BLUESCREEN = 0


class StartPrqKind:
    NONE = 0
    WHEN_CONNECTED = 1
    WHEN_LAUNCH_APP = 2


class EndPrqKind:
    NONE = 0


class ParamType:
    INT = 0
    STRING = 1
    FLOAT = 2
    BOOL = 3


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
        return


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

    def parse_string(self, value: str) -> int:
        return int(value)


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

    def parse_string(self, value: str) -> float:
        return float(value)


class BoolParam(ActionParam):
    def __init__(self, label: str, default: bool):
        super().__init__(label, ParamType.BOOL, default)

    def valid(self, value: bool) -> True:
        return True

    def parse_string(self, value: bool) -> bool:
        return bool(value)


class StringParam(ActionParam):
    def __init__(self, label: str, default: str):
        super().__init__(label, ParamType.STRING, default)

    def parse_string(self, value: str) -> str:
        return value


class StartPrq:
    params = {}

    def __init__(self, kind: int, datas: dict = {}, check_inv: float = 1):
        self.kind = kind
        self.datas = datas
        self.check_inv = check_inv

    def valid(self) -> bool:
        return True

    def to_tuple(self) -> tuple[int, dict, int]:
        return self.kind, self.datas, self.check_inv

    @staticmethod
    def from_tuple(_tuple: tuple[int, dict, int]) -> "StartPrq":
        kind, datas, check_inv = _tuple
        return start_prqs_map[kind](datas, check_inv)

    @staticmethod
    def ch_name() -> str:
        return "undefined"

    def name(self) -> str:
        return self.ch_name()


class EndPrq:
    params = {}

    def __init__(self, kind: int, datas: dict = {}, check_inv: float = 1):
        self.kind = kind
        self.datas = datas
        self.check_inv = check_inv

    def valid(self) -> bool:
        return True

    def to_tuple(self) -> tuple[int, dict, int]:
        return self.kind, self.datas, self.check_inv

    @staticmethod
    def from_tuple(_tuple: tuple[int, dict, int]) -> "EndPrq":
        kind, datas, check_inv = _tuple
        return end_prqs_map[kind](datas, check_inv)

    @staticmethod
    def ch_name() -> str:
        return "undefined"

    def name(self) -> str:
        return self.ch_name()


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
        return "应用启动条件"

    def name(self):
        return f"当启动 {self.app_name} 时"

    @property
    def app_name(self):
        return self.datas["app_name"]

    @app_name.setter
    def app_name(self, value: str):
        self.datas["app_name"] = value


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
        return actions_map[kind](datas)

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

    def name(self) -> str:
        return self.ch_name()

    @staticmethod
    def ch_name() -> str:
        return "蓝屏"


class TheAction:
    def __init__(
        self,
        name: str,
        actions: list[AnAction] = [],
        start_prqs: list[StartPrq] = [],
        end_prqs: list[EndPrq] = [],
    ):
        self.name = name
        self.actions = actions
        self.start_prqs = start_prqs
        self.end_prqs = end_prqs

    def build_packet(self) -> Packet:
        packet = {"name": self.name}
        packet["actions"] = [action.to_tuple() for action in self.actions]
        packet["start_prqs"] = [start_prq.to_tuple() for start_prq in self.start_prqs]
        packet["end_prqs"] = [end_prq.to_tuple() for end_prq in self.end_prqs]
        return packet

    @staticmethod
    def from_packet(packet: Packet) -> "TheAction":
        return TheAction(
            packet["name"],
            [AnAction.from_tuple(action) for action in packet["actions"]],
            [StartPrq.from_tuple(start_prq) for start_prq in packet["start_prqs"]],
            [EndPrq.from_tuple(end_prq) for end_prq in packet["end_prqs"]],
        )

    def __str__(self):
        return self.name


actions_map = {ActionKind.BLUESCREEN: BlueScreenAction}
start_prqs_map: dict[int, StartPrq] = {
    StartPrqKind.NONE: NoneStartPrq,
    StartPrqKind.WHEN_LAUNCH_APP: LaunchAppStartPrq,
}
end_prqs_map = {EndPrqKind.NONE: NoneEndPrq}
