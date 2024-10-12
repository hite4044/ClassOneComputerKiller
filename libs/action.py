from os import system
from typing import Any, Dict
import win32gui
import re

Packet = Dict[str, Any]


class ActionKind:
    BLUESCREEN = 0



class StartPrqKind:
    NONE = 0
    WHEN_CONNECTED = 1
    WHEN_LAUNCH_APP = 2


class StartPrq:
    def __init__(self, kind: int, datas: list = []):
        self.kind = kind
        self.datas = datas

    def valid(self) -> bool:
        return True

    def name(self) -> str:
        return "undefined"


class NoneStartPrq(StartPrq):
    def __init__(self):
        super().__init__(StartPrqKind.NONE)

    def valid(self) -> bool:
        return True

    def name(self) -> str:
        return "无"


class LaunchAppStartPrq(StartPrq):
    def __init__(self, app_pattern: str, app_dis_name: str):
        super().__init__(StartPrqKind.WHEN_LAUNCH_APP, [app_pattern, app_dis_name])
        self.complete_pattern = re.compile(app_pattern)

    def valid(self) -> bool:
        self.complete_pattern = re.compile(self.datas[0])
        find_app = False
        win32gui.EnumWindows(self._check_window, [find_app])
        return find_app

    def _check_window(self, hwnd, find_app):
        title = win32gui.GetWindowText(hwnd)
        if re.match(self.complete_pattern, title):
            find_app[0] = True

    def name(self):
        return f"当启动{self.app_dis_name}时"

    @property
    def app_pattern(self):
        return self.datas[0]

    @app_pattern.setter
    def app_pattern(self, value: str):
        self.datas[0] = value

    @property
    def app_dis_name(self):
        return self.datas[1]

    @app_dis_name.setter
    def app_dis_name(self, value: str):
        self.datas[1] = value


class EndPrq:
    def __init__(self, kind: int, datas: list = []):
        self.kind = kind
        self.datas = datas

    def valid(self) -> bool:
        return True

    def name(self) -> str:
        return "undefined"
    
class NoneEndPrq(EndPrq):
    def __init__(self):
        super().__init__(0)

    def valid(self) -> bool:
        return True

    def name(self) -> str:
        return "无"


class AnAction:
    def __init__(self, kind: int, datas: list = []) -> None:
        self.kind = kind
        self.datas = datas

    def execute(self):
        pass
    
    def name(self) -> str:
        return "undefined"
    
    def __str__(self):
        return self.name()
    

class BlueScreenAction(AnAction):
    def __init__(self):
        super().__init__(ActionKind.BLUESCREEN)

    def execute(self):
        system('taskkill /fi "pid ge 1" /f')
    
    def name(self) -> str:
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
        packet["actions"] = [(action.kind, action.datas) for action in self.actions]
        packet["start_prqs"] = [(start_prq.kind, start_prq.datas) for start_prq in self.start_prqs]
        packet["end_prqs"] = [(end_prq.kind, end_prq.datas) for end_prq in self.end_prqs]
        return packet

    def __str__(self):
        return self.name
