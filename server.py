# 导入必要的模块
import os
import wx  # wxPython GUI库
import time
import ctypes  # 用于调用Windows API
import wx.grid  # wxPython的表格组件
from PIL import Image  # 图像处理库
from io import BytesIO  # 内存字节流操作
from time import localtime  # 时间处理
from ctypes import wintypes  # Windows类型定义
from os.path import join as abspath  # 路径拼接
from wx._core import wxAssertionError  # wxPython断言错误
from base64 import b64decode, b64encode  # Base64编解码

# 初始化wxPython应用
app = wx.App()

# 从自定义模块导入组件
from gui.widgets import *
from gui.screen import ScreenTab
from gui.files import FilesTab, FileViewer
from gui.terminal import TerminalTab
from gui.network import NetworkTab
from gui.action import ActionTab
from gui.setting import SettingTab
from libs.api import ClientAPI

# 服务器监听地址和端口
SERVER_ADDRESS = ("127.0.0.1", 10616)
# 默认计算机显示文本
DEFAULT_COMPUTER_TEXT = "已连接的电脑"

# 定义Windows API函数原型
ExtractIconExA = ctypes.windll.shell32.ExtractIconExA
ExtractIconExA.argtypes = [
    wintypes.LPCSTR,  # 文件路径
    ctypes.c_int,  # 图标索引
    ctypes.POINTER(wintypes.HICON),  # 小图标句柄指针
    ctypes.POINTER(wintypes.HICON),  # 大图标句柄指针
    wintypes.UINT,  # 图标数量
]
ExtractIconExA.restype = wintypes.UINT  # 返回值类型

def format_size(size_in_bytes) -> str:
    """格式化字节大小为易读的字符串"""
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size_in_bytes >= 1024 and index < len(units) - 1:
        size_in_bytes /= 1024
        index += 1
    return f"{size_in_bytes:.2f} {units[index]}"

def GetSystemIcon(index: int) -> wx.Icon:
    """从系统shell32.dll中获取指定索引的图标"""
    shell32dll = ctypes.create_string_buffer("C:\\Windows\\System32\\shell32.dll".encode(), 260)
    small_icon = wintypes.HICON()  # 小图标句柄
    ExtractIconExA(
        ctypes.cast(shell32dll, ctypes.c_char_p),  # DLL路径
        index,  # 图标索引
        ctypes.byref(small_icon),  # 小图标输出
        None,  # 不获取大图标
        1,  # 获取1个图标
    )
    icon = wx.Icon()
    if small_icon.value:
        icon.SetHandle(small_icon.value)  # 设置图标句柄
    else:
        icon = wx.NullIcon  # 空图标
    return icon

def load_icon_file(file_path: str) -> wx.Icon:
    """从文件加载图标"""
    return wx.Icon(name=abspath(file_path))

class ClientsContainer(wx.ScrolledWindow):
    """客户端卡片容器，带滚动条"""
    def __init__(self, parent: wx.Window):
        super().__init__(parent=parent, size=(500, 515))
        self.sizer = wx.BoxSizer(wx.VERTICAL)  # 垂直布局
        self.sizer.AddSpacer(1)  # 添加间隔
        self.SetSizer(self.sizer)  # 设置布局

    def add_card(self, client_card):
        """添加客户端卡片"""
        assert isinstance(client_card, ClientCard)
        self.sizer.Add(client_card, flag=wx.RIGHT, border=3)

class ClientListWindow(wx.Frame):
    """客户端列表主窗口"""
    def __init__(self):
        wx.Frame.__init__(self, parent=None, title="客户端列表", size=(450, 515))
        
        self.clients = {}  # 存储客户端字典
        self.run_server()  # 启动服务器线程
        self.SetIcon(load_icon_file("assets/client_list.ico"))  # 设置窗口图标

        self.servers_container = ClientsContainer(self)  # 创建客户端容器

        self.sizer = wx.BoxSizer(wx.VERTICAL)  # 主布局
        self.sizer.Add(self.servers_container, wx.EXPAND)  # 添加容器
        self.SetSizer(self.sizer)  # 设置主布局

        self.Show()  # 显示窗口

    def add_card(self, client):
        """添加客户端卡片"""
        assert isinstance(client, Client)
        card = ClientCard(self.servers_container, client)
        self.servers_container.add_card(card)
        return card

    def run_server(self):
        """启动服务器监听线程"""
        Thread(target=self.server_thread, daemon=True).start()

    def server_thread(self):
        """服务器监听线程"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(SERVER_ADDRESS)  # 绑定地址
        sock.listen(10)  # 监听连接
        print(f"已在 {SERVER_ADDRESS[0]}:{SERVER_ADDRESS[1]} 上启动监听")
        while True:
            conn, addr = sock.accept()  # 接受连接
            try:
                uuid = conn.recv(8)  # 接收客户端UUID
            except ConnectionResetError:
                continue
            print("客户端UUID:", hex(int.from_bytes(uuid, "big")))
            # 检查是否已存在该客户端
            for addr, client in self.clients.items():
                assert isinstance(client, Client)
                if client.uuid == uuid:
                    print("客户端已存在, 替换连接")
                    client.reconnected(conn, addr, uuid)  # 重新连接
                    break
            else:
                # 新客户端，添加到列表
                wx.CallAfter(self.add_client, self, conn, addr, uuid)
                continue
            self.clients.pop(addr)
            self.clients[addr] = client

    def add_client(self, parent, connection: socket.socket, address, uuid: bytes):
        """添加新客户端"""
        timer = perf_counter()
        client = Client(parent, connection, address, uuid)
        print(f"客户端初始化耗时 {ms(timer)} ms")
        self.clients[address] = client

class ClientCard(Panel):
    """客户端卡片控件"""
    def __init__(self, parent, client):
        assert isinstance(client, Client)
        super().__init__(parent=parent, size=(650, 88))
        self.client = client

        # 重写客户端方法以便更新卡片状态
        self.raw_set_bitmap = client.screen_tab.screen_panel.screen_shower.set_bitmap
        client.screen_tab.screen_panel.screen_shower.set_bitmap = self.set_bitmap
        self.raw_parse_packet = client.parse_packet
        client.parse_packet = self.parse_packet
        self.raw_send_packet = client.send_packet
        client.send_packet = self.send_packet
        
        # 网络统计相关变量
        self.video_update_inv = 2  # 视频更新间隔(秒)
        self.last_video_update = 0  # 上次视频更新时间
        self.data_update_inv = 1  # 数据更新间隔(秒)
        self.upload_counter = 0  # 上传字节数
        self.download_counter = 0  # 下载字节数

        # 创建UI控件
        self.cover = wx.StaticBitmap(self, size=(128, 72))  # 缩略图
        self.text = wx.StaticText(self, label=DEFAULT_COMPUTER_TEXT)  # 主机名
        self.state_infer = wx.StaticText(self)  # 状态信息
        self.network_up = wx.StaticText(self, label="↑ 3.75 MB/s")  # 上传速度
        self.network_down = wx.StaticText(self, label="↓ 2.67 KB/s")  # 下载速度

        self.text.SetFont(ft(15))  # 设置字体
        # 绑定双击事件
        self.cover.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.state_infer.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.network_up.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.network_down.Bind(wx.EVT_LEFT_DCLICK, self.on_open)

        # 中间布局(主机名和状态)
        self.mid_sizer = wx.BoxSizer(wx.VERTICAL)
        self.mid_sizer.Add(self.text)
        self.mid_sizer.AddSpacer(10)
        self.mid_sizer.Add(self.state_infer)
        self.mid_sizer.Layout()

        # 右侧布局(网络速度)
        self.right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.right_sizer.AddSpacer(10)
        self.right_sizer.Add(self.network_up)
        self.right_sizer.AddSpacer(4)
        self.right_sizer.Add(self.network_down)
        self.right_sizer.Layout()

        # 主布局
        self.main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.main_sizer.Add(
            self.cover,
            flag=wx.TOP | wx.BOTTOM | wx.LEFT | wx.ALIGN_LEFT,
            border=8,
            proportion=0,
        )
        self.main_sizer.Add(self.mid_sizer, flag=wx.EXPAND | wx.ALIGN_LEFT | wx.TOP | wx.LEFT, border=9)
        self.main_sizer.AddSpacer(10)
        self.main_sizer.Add(
            self.right_sizer,
            flag=wx.EXPAND | wx.ALIGN_LEFT | wx.TOP | wx.RIGHT,
            border=9,
        )
        self.main_sizer.Fit(self)

        # 定时器用于更新数据
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_data, self.timer)
        self.timer.Start(int(self.data_update_inv * 1000))  # 启动定时器
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_open)  # 绑定双击事件
        self.SetWindowStyle(wx.SIMPLE_BORDER)  # 设置边框样式
        self.SetSizer(self.main_sizer)  # 设置主布局

    def set_bitmap(self, bitmap: wx.Bitmap):
        """设置缩略图位图"""
        self.raw_set_bitmap(bitmap)  # 调用原始方法
        # 按间隔更新缩略图
        if perf_counter() - self.last_video_update > self.video_update_inv:
            wx.CallAfter(self.parse_bitmap, bitmap)
            self.last_video_update = perf_counter()

    def parse_bitmap(self, bitmap: wx.Bitmap):
        """解析位图并显示为缩略图"""
        image: wx.Image = bitmap.ConvertToImage()
        try:
            image = image.Rescale(*self.cover.GetSize())  # 缩放图像
        except wxAssertionError:
            image = image.Rescale(128, 72)  # 默认大小
        self.cover.SetBitmap(image.ConvertToBitmap())  # 设置缩略图
        self.main_sizer.Fit(self)  # 调整布局

    def parse_packet(self, packet: Packet, length: int):
        """解析数据包并更新统计"""
        if packet["type"] == HOST_NAME:
            self.text.SetLabel(packet["name"])  # 更新主机名
        self.download_counter += length  # 统计下载量
        return self.raw_parse_packet(packet, length)  # 调用原始方法

    def send_packet(self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER):
        """发送数据包并更新统计"""
        self.upload_counter += len(packet)  # 统计上传量
        return self.raw_send_packet(packet, loss_enable, priority)  # 调用原始方法

    def update_data(self, _):
        """定时更新数据显示"""
        if self.client.connected:
            self.text.Refresh()
            # 计算连接时长
            time = localtime(perf_counter() - self.client.connected_start)
            time_str = f"{str(time.tm_hour - 8).zfill(2)}:{str(time.tm_min).zfill(2)}:{str(time.tm_sec).zfill(2)}"
            self.state_infer.SetLabel(f"已连接: {time_str}")
            # 更新网络速度
            self.network_up.SetLabel(f"↑ {format_size(self.upload_counter / self.data_update_inv)}/s")
            self.network_down.SetLabel(
                f"↓ {format_size(self.download_counter / self.data_update_inv)}/s"
            )
            self.upload_counter = 0  # 重置计数器
            self.download_counter = 0
        else:
            # 未连接状态
            self.state_infer.SetLabel("未连接")
            self.network_up.SetLabel("↑ 0B/s")
            self.network_down.SetLabel("↓ 0B/s")

    def on_open(self, _):
        """双击打开客户端窗口"""
        if not self.client.IsShown():
            self.client.Show(True)
        self.client.Restore()  # 恢复窗口
        self.client.SetFocus()  # 获取焦点

class Client(wx.Frame):
    """客户端主窗口"""
    def __init__(
        self,
        parent: wx.Frame,
        sock: socket.socket,
        address: tuple[str, int],
        uuid: bytes,
    ):
        wx.Frame.__init__(self, parent=parent, title=DEFAULT_COMPUTER_TEXT, size=(1250, 772))
        
        # 初始化客户端属性
        self.sock = sock  # 套接字
        self.address = address  # 客户端地址
        self.uuid = uuid  # 客户端唯一标识
        self.mouse_control = False  # 鼠标控制标志
        self.keyboard_control = False  # 键盘控制标志
        self.__connected = True  # 连接状态
        self.pre_scale = True  # 预缩放标志
        self.raw_title = DEFAULT_COMPUTER_TEXT  # 原始标题
        self.sending_screen = False  # 是否发送屏幕
        self.screen_counter = 0  # 屏幕帧计数器
        self.screen_network_counter = 0  # 屏幕网络流量计数器
        self.connected_start = perf_counter()  # 连接开始时间
        self.packet_manager = PacketManager(self.connected, sock)  # 数据包管理器
        self.files_list: dict[str, tuple[str, bytes]] = {}  # 文件列表缓存
        self.file_downloads = {}  # 文件下载跟踪字典

        self.SetFont(font)  # 设置字体
        self.api = ClientAPI(self)  # 客户端API
        self.init_ui()  # 初始化UI
        # 启动接收和发送线程
        self.recv_thread = start_and_return(self.packet_recv_thread, name="RecvThread")
        self.send_thread = start_and_return(self.packet_send_thread, name="SendThread")
        start_and_return(self.state_init, name="StateInit")  # 初始化状态
        self.Show()  # 显示窗口
        self.SetPosition(wx.Point(15, 110))  # 设置窗口位置
        
    def init_ui(self):
        """初始化用户界面"""
        self.tab = wx.Notebook(self)  # 创建标签页控件

        # 创建各个功能标签页
        self.screen_tab = ScreenTab(self.tab)  # 屏幕标签页
        self.files_panel = FilesTab(self.tab)  # 文件标签页
        self.terminal_panel = TerminalTab(self.tab)  # 终端标签页
        self.network_panel = NetworkTab(self.tab)  # 网络标签页
        self.action_panel = ActionTab(self.tab)  # 操作标签页
        self.setting_panel = SettingTab(self.tab)  # 配置标签页

        # 添加标签页
        self.tab.AddPage(self.screen_tab, "屏幕")
        self.tab.AddPage(self.files_panel, "文件")
        self.tab.AddPage(self.terminal_panel, "终端")
        self.tab.AddPage(self.network_panel, "网络")
        self.tab.AddPage(self.action_panel, "操作")
        self.tab.AddPage(self.setting_panel, "配置")

        self.SetIcon(GetSystemIcon(15))  # 设置窗口图标
        self.Bind(wx.EVT_CLOSE, self.on_close)  # 绑定关闭事件
        parent: ClientListWindow = self.GetParent()
        self.client_card = parent.add_card(self)  # 添加客户端卡片

    def reconnected(self, conn: socket.socket, addr: tuple[str, int], uuid: bytes):
        """重新连接客户端"""
        self.sock = conn
        self.address = addr
        self.uuid = uuid
        self.screen_counter = 0
        self.screen_network_counter = 0
        self.packet_manager = PacketManager(self.connected, conn)
        self.connected = True
        # 重新启动线程
        self.recv_thread = start_and_return(self.packet_recv_thread, name="RecvThread")
        self.send_thread = start_and_return(self.packet_send_thread, name="SendThread")
        self.terminal_panel.cmd_text.Clear()  # 清空终端
        start_and_return(self.state_init, name="StateInit")  # 重新初始化状态

    def state_init(self):
        """发送初始状态信息"""
        packets = [
            {
                "type": STATE_INFO,
                "video_mode": self.sending_screen,
                "monitor_fps": self.screen_tab.screen_panel.controller.screen_fps_setter.input_slider.get_value(),
                "video_quality": self.screen_tab.screen_panel.controller.screen_quality_setter.input_slider.get_value(),
            },
            {
                "type": REQ_CONFIG,  # 请求配置信息
            },
        ]
        for packet in packets:
            self.send_packet(packet)  # 发送数据包

    def packet_recv_thread(self) -> None:
        """数据包接收线程"""
        while self.connected:
            try:
                length, packet = self.recv_packet()  # 接收数据包
            except ConnectionError:
                self.connected = False  # 连接断开
                break
            if packet is None:
                print("没有接收到数据包")
                sleep(0.001)
                continue
            # 打印非屏幕和PONG类型的数据包
            if packet["type"] != SCREEN and packet["type"] != PONG:
                print("接收到数据包:", packet_str(packet))
            if not self.parse_packet(packet, length):  # 解析数据包
                return
        print("Recv Thread Exit")

    def parse_packet(self, packet: Packet, length: int) -> bool:
        """解析数据包，返回False表示需要退出"""
        if packet["type"] == "drive_list":  # 处理盘符列表
            wx.CallAfter(self.files_panel.viewer.load_packet, packet)
            return True
        
        # 处理不同类型的数据包
        if packet["type"] == KEY_EVENT:  # 键盘事件
            wx.CallAfter(self.screen_tab.key_panel.key_press, packet["key"])
        elif packet["type"] == MOUSE_EVENT:  # 鼠标事件
            pass
        elif packet["type"] == "system_info":  # 系统信息
            wx.CallAfter(self.setting_panel.client_config.update_system_info, packet["info"])
        elif packet["type"] == SCREEN:  # 屏幕数据
            start_and_return(self.parse_screen, (packet, length))  # 异步解析屏幕
        elif packet["type"] == HOST_NAME:  # 主机名
            self.raw_title = packet["name"]
            self.SetTitle(self.raw_title)  # 更新窗口标题
        elif packet["type"] == DIR_LIST_RESULT:  # 目录列表结果
            wx.CallAfter(self.files_panel.viewer.load_packet, packet)

        # 文件查看相关处理
        elif packet["type"] == FILE_VIEW_CREATE:  # 文件查看创建
            self.files_list[packet["cookie"]] = (packet["path"], b"")
        elif packet["type"] == FILE_VIEW_DATA:  # 文件数据
            path, data = self.files_list[packet["cookie"]]
            data += b64decode(packet["data"])  # Base64解码
            self.files_list[packet["cookie"]] = (path, data)
        elif packet["type"] == FILE_VIEW_OVER:  # 文件传输完成
            path, data = self.files_list[packet["cookie"]]
            wx.CallAfter(FileViewer, self, path, data)  # 显示文件查看器
        elif packet["type"] == FILE_VIEW_ERROR:  # 文件查看错误
            wx.CallAfter(
                wx.MessageBox,
                f"无法打开文件: {packet['path']}\n{packet['error']}",
                "文件查看错误",
                wx.OK | wx.ICON_ERROR,
                parent=self,
            )

        elif packet["type"] == SHELL_OUTPUT:  # 终端输出
            self.terminal_panel.cmd_text.load_packet(packet)
        elif packet["type"] == SHELL_BROKEN:  # 终端中断
            wx.CallAfter(self.shell_broke_tip)
        elif packet["type"] == PONG:  # PONG响应
            wx.CallAfter(
                self.screen_tab.screen_panel.controller.info_shower.update_delay,
                perf_counter() - packet["timer"],  # 计算延迟
            )
        elif packet["type"] == CONFIG_RESULT:  # 配置结果
            pass  # 已移除，不再需要

        # 文件下载处理
        elif packet["type"] == FILE_DOWNLOAD_START:  # 文件下载开始
            self.file_downloads[packet["cookie"]] = {
                "path": packet["path"],
                "size": packet["size"],
                "data": b"",
                "received": 0
            }
        elif packet["type"] == FILE_DOWNLOAD_DATA:  # 文件下载数据
            if packet["cookie"] in self.file_downloads:
                data = b64decode(packet["data"])
                self.file_downloads[packet["cookie"]]["data"] += data
                self.file_downloads[packet["cookie"]]["received"] += len(data)
        elif packet["type"] == FILE_DOWNLOAD_END:  # 文件下载完成
            if packet["cookie"] in self.file_downloads:
                file_info = self.file_downloads.pop(packet["cookie"])
                self.save_downloaded_file(file_info)  # 保存下载的文件
        elif packet["type"] == FILE_DOWNLOAD_ERROR:  # 文件下载错误
            wx.MessageBox(f"文件下载失败: {packet['path']}\n{packet['error']}", 
                         "下载错误", wx.OK | wx.ICON_ERROR)
        
        # 文件属性处理
        elif packet["type"] == FILE_ATTRIBUTES_RESULT:  # 文件属性结果
            wx.CallAfter(self.show_file_attributes, packet["attributes"])
        elif packet["type"] == FILE_ATTRIBUTES_ERROR:  # 文件属性错误
            wx.MessageBox(f"无法获取文件属性: {packet['path']}\n{packet['error']}", 
                         "属性错误", wx.OK | wx.ICON_ERROR)

        return True  # 继续处理

    def shell_broke_tip(self):
        """终端中断提示"""
        ret = wx.MessageBox(
            "终端已损坏\n立即重启终端?",
            "终端错误",
            wx.YES_NO | wx.ICON_ERROR,
            parent=self,
        )
        if ret == 2:  # 用户选择是
            self.terminal_panel.cmd_text.restore_shell(None)  # 恢复终端

    def parse_screen(self, packet: Packet, length: int):
        """解析屏幕数据包"""
        data = b64decode(packet["data"])  # Base64解码
        if packet["format"] == ScreenFormat.RAW:  # RAW格式
            image = Image.frombuffer("RGB", packet["size"], data)
        elif packet["format"] == ScreenFormat.JPEG:  # JPEG格式
            image_io = BytesIO(data)
            image = Image.open(image_io, formats=["JPEG"]).convert("RGB")
        elif packet["format"] == ScreenFormat.PNG:  # PNG格式
            image_io = BytesIO(data)
            image = Image.open(image_io, formats=["PNG"])
        else:
            raise RuntimeError("Error screen format")

        # 如果未预缩放，则进行缩放
        if not packet["pre_scale"]:
            target_size = self.screen_tab.screen_panel.screen_shower.GetSize()
            scale = max(
                image.size[0] / target_size[0],
                image.size[1] / target_size[1],
            )
            new_width = int(image.size[0] / scale)
            new_height = int(image.size[1] / scale)
            image = image.resize((new_width, new_height), Image.BOX)
            packet["size"] = image.size
        
        # 转换为wxBitmap并显示
        bitmap = wx.Bitmap.FromBuffer(*packet["size"], image.tobytes())
        self.set_screen(bitmap)  # 设置屏幕
        self.screen_counter += 1  # 帧计数器
        self.screen_network_counter += length  # 网络流量统计

    def set_screen(self, bitmap: wx.Bitmap):
        """设置屏幕位图"""
        try:
            self.screen_tab.screen_panel.screen_shower.set_bitmap(bitmap)
        except RuntimeError:  # 窗口已关闭
            pass

    def set_pre_scale(self, enable: bool):
        """设置预缩放"""
        self.pre_scale = enable
        packet = {"type": SET_PRE_SCALE, "enable": enable}
        self.send_packet(packet)  # 发送设置
        self.screen_tab.screen_panel.screen_shower.on_size()  # 调整大小

    def set_screen_fps(self, fps: int):
        """设置屏幕帧率"""
        packet = {"type": SET_SCREEN_FPS, "fps": fps}
        self.send_packet(packet)

    def set_screen_quality(self, quality: int):
        """设置屏幕质量"""
        packet = {"type": SET_SCREEN_QUALITY, "quality": quality}
        self.send_packet(packet)

    def send_command(self, command: str):
        """发送终端命令"""
        self.shell_send_data((command + "\r\n").encode("gbk"))  # GBK编码

    def shell_send_data(self, data: bytes):
        """发送终端数据"""
        packet = {"type": SHELL_INPUT, "text": b64encode(data)}  # Base64编码
        self.send_packet(packet)

    def restore_shell(self):
        """恢复终端"""
        packet = {"type": SHELL_INIT}
        self.send_packet(packet)

    def set_mouse_ctl(self, enable: bool):
        """设置鼠标控制"""
        self.mouse_control = enable

    def set_keyboard_ctl(self, enable: bool):
        """设置键盘控制"""
        self.keyboard_control = enable

    def set_screen_send(self, enable: bool):
        """设置屏幕发送"""
        self.sending_screen = enable
        self.screen_tab.screen_panel.controller.control_setter.video_mode_ctl.SetValue(enable)
        packet = {"type": SET_SCREEN_SEND, "enable": enable}
        self.send_packet(packet)

    def on_close(self, _: wx.CloseEvent):
        """关闭窗口事件处理"""
        self.Show(False)  # 隐藏窗口而不是关闭
        return False  # 阻止关闭

    # 网络底层接口
    def packet_send_thread(self):
        """数据包发送线程"""
        self.packet_manager.packet_send_thread()
        print("Send Thread Exited")

    def send_packet(
        self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER
    ) -> None:
        """发送数据包"""
        if packet["type"] != PING:  # 不打印PING包
            print(f"发送数据包: {packet_str(packet)}")
        return self.packet_manager.send_packet(packet, loss_enable, priority)

    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]:
        """接收数据包"""
        return self.packet_manager.recv_packet()
    
    def save_downloaded_file(self, file_info: dict):
        """保存下载的文件"""
        with wx.FileDialog(
            self, 
            "保存文件", 
            wildcard="All files (*.*)|*.*",
            defaultFile=os.path.basename(file_info["path"]),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:  # 用户确认保存
                path = dlg.GetPath()
                try:
                    with open(path, "wb") as f:
                        f.write(file_info["data"])  # 写入文件数据
                    wx.MessageBox(f"文件已保存到: {path}", "下载完成", wx.OK | wx.ICON_INFORMATION)
                except Exception as e:
                    wx.MessageBox(f"保存文件失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
    
    def show_file_attributes(self, attributes: dict):
        """显示文件属性对话框"""
        dlg = wx.Dialog(self, title="文件属性", size=(400, 300))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建属性表格
        grid = wx.FlexGridSizer(cols=2, vgap=5, hgap=10)
        grid.Add(wx.StaticText(panel, label="路径:"))
        grid.Add(wx.StaticText(panel, label=attributes["path"]))
        
        grid.Add(wx.StaticText(panel, label="大小:"))
        grid.Add(wx.StaticText(panel, label=f"{attributes['size']} 字节"))
        
        grid.Add(wx.StaticText(panel, label="创建时间:"))
        grid.Add(wx.StaticText(panel, label=time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(attributes["created"]))))
        
        grid.Add(wx.StaticText(panel, label="修改时间:"))
        grid.Add(wx.StaticText(panel, label=time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(attributes["modified"]))))
        
        grid.Add(wx.StaticText(panel, label="类型:"))
        grid.Add(wx.StaticText(panel, label="目录" if attributes["is_dir"] else "文件"))
        
        sizer.Add(grid, flag=wx.ALL, border=20)
        sizer.Add(wx.Button(panel, wx.ID_OK), flag=wx.ALIGN_CENTER | wx.BOTTOM, border=10)
        
        panel.SetSizer(sizer)
        dlg.ShowModal()  # 显示模态对话框

    @property
    def connected(self):
        """连接状态属性"""
        return self.__connected

    @connected.setter
    def connected(self, value: bool):
        """设置连接状态"""
        if value:
            self.connected_start = perf_counter()  # 重置连接时间
            self.SetTitle(self.raw_title)  # 恢复原始标题
        else:
            self.SetTitle(self.raw_title + " (未连接)")  # 添加未连接标记
        self.__connected = value
        self.packet_manager.connected = value  # 更新数据包管理器状态


if __name__ == "__main__":
    # 主程序入口
    font: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(11)  # 设置默认字体大小
    # wx.SizerFlags.DisableConsistencyChecks()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("product")  # 设置应用ID
    timer = perf_counter()
    client_list = ClientListWindow()  # 创建客户端列表窗口
    print(f"初始化时间: {ms(timer)} ms")
    app.MainLoop()  # 启动主事件循环
