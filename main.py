import wx
import ctypes
import wx.grid
from PIL import Image
from io import BytesIO
from time import localtime
from ctypes import wintypes
from os.path import join as abspath
from wx._core import wxAssertionError
from base64 import b64decode, b64encode

app = wx.App()
from gui.widgets import *
from gui.screen import ScreenTab
from gui.files import FilesTab, FileViewer
from gui.terminal import TerminalTab
from gui.network import NetworkTab
from gui.action import ActionTab
from libs.api import ClientAPI

SERVER_ADDRESS = ("127.0.0.1", 10616)
DEFAULT_COMPUTER_TEXT = "已连接的电脑"

ExtractIconExA = ctypes.windll.shell32.ExtractIconExA
ExtractIconExA.argtypes = [
    wintypes.LPCSTR,
    ctypes.c_int,
    ctypes.POINTER(wintypes.HICON),
    ctypes.POINTER(wintypes.HICON),
    wintypes.UINT,
]
ExtractIconExA.restype = wintypes.UINT


def format_size(size_in_bytes) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size_in_bytes >= 1024 and index < len(units) - 1:
        size_in_bytes /= 1024
        index += 1
    return f"{size_in_bytes:.2f} {units[index]}"


def GetSystemIcon(index: int) -> wx.Icon:
    shell32dll = ctypes.create_string_buffer("C:\\Windows\\System32\\shell32.dll".encode(), 260)
    small_icon = wintypes.HICON()
    ExtractIconExA(
        ctypes.cast(shell32dll, ctypes.c_char_p),
        index,
        ctypes.byref(small_icon),
        None,
        1,
    )
    icon = wx.Icon()
    if small_icon.value:
        icon.SetHandle(small_icon.value)
    else:
        icon = wx.NullIcon
    return icon


def load_icon_file(file_path: str) -> wx.Icon:
    return wx.Icon(name=abspath(file_path))


class ClientsContainer(wx.ScrolledWindow):
    def __init__(self, parent: wx.Window):
        super().__init__(parent=parent, size=(500, 515))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.AddSpacer(1)
        self.SetSizer(self.sizer)

    def add_card(self, client_card):
        assert isinstance(client_card, ClientCard)
        self.sizer.Add(client_card, flag=wx.RIGHT, border=3)


class ClientListWindow(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, parent=None, title="客户端列表", size=(450, 515))

        self.clients = {}
        self.run_server()
        self.SetIcon(load_icon_file("assets/client_list.ico"))

        self.servers_container = ClientsContainer(self)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.servers_container, wx.EXPAND)
        self.SetSizer(self.sizer)

        self.Show()

    def add_card(self, client):
        assert isinstance(client, Client)
        card = ClientCard(self.servers_container, client)
        self.servers_container.add_card(card)
        return card

    def run_server(self):
        Thread(target=self.server_thread, daemon=True).start()

    def server_thread(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(SERVER_ADDRESS)
        sock.listen(10)
        print(f"已在 {SERVER_ADDRESS[0]}:{SERVER_ADDRESS[1]} 上启动监听")
        while True:
            conn, addr = sock.accept()
            uuid = conn.recv(8)
            print("客户端UUID:", hex(int.from_bytes(uuid, "big")))
            for addr, client in self.clients.items():
                assert isinstance(client, Client)
                if client.uuid == uuid:
                    print("客户端已存在, 替换连接")
                    client.reconnected(conn, addr, uuid)
                    break
            else:
                wx.CallAfter(self.add_client, self, conn, addr, uuid)
                continue
            self.clients.pop(addr)
            self.clients[addr] = client

    def add_client(self, parent, connection: socket.socket, address, uuid: bytes):
        timer = perf_counter()
        client = Client(parent, connection, address, uuid)
        print(f"客户端初始化耗时 {ms(timer)} ms")
        self.clients[address] = client


class ClientCard(Panel):
    def __init__(self, parent, client):
        assert isinstance(client, Client)
        super().__init__(parent=parent, size=(650, 88))
        self.client = client

        self.raw_set_bitmap = client.screen_tab.screen_panel.screen_shower.set_bitmap
        client.screen_tab.screen_panel.screen_shower.set_bitmap = self.set_bitmap
        self.raw_parse_packet = client.parse_packet
        client.parse_packet = self.parse_packet
        self.raw_send_packet = client.send_packet
        client.send_packet = self.send_packet
        self.video_update_inv = 2
        self.last_video_update = 0
        self.data_update_inv = 1
        self.upload_counter = 0
        self.download_counter = 0

        self.cover = wx.StaticBitmap(self, size=(128, 72))
        self.text = wx.StaticText(self, label=DEFAULT_COMPUTER_TEXT)
        self.state_infer = wx.StaticText(self)
        self.network_up = wx.StaticText(self, label="↑ 3.75 MB/s")
        self.network_down = wx.StaticText(self, label="↓ 2.67 KB/s")

        self.text.SetFont(ft(15))
        self.cover.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.state_infer.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.network_up.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.network_down.Bind(wx.EVT_LEFT_DCLICK, self.on_open)

        self.mid_sizer = wx.BoxSizer(wx.VERTICAL)
        self.mid_sizer.Add(self.text)
        self.mid_sizer.AddSpacer(10)
        self.mid_sizer.Add(self.state_infer)
        self.mid_sizer.Layout()

        self.right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.right_sizer.AddSpacer(10)
        self.right_sizer.Add(self.network_up)
        self.right_sizer.AddSpacer(4)
        self.right_sizer.Add(self.network_down)
        self.right_sizer.Layout()

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

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_data, self.timer)
        self.timer.Start(int(self.data_update_inv * 1000))
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_open)
        self.SetWindowStyle(wx.SIMPLE_BORDER)

        self.SetSizer(self.main_sizer)

    def set_bitmap(self, bitmap: wx.Bitmap):
        self.raw_set_bitmap(bitmap)
        if perf_counter() - self.last_video_update > self.video_update_inv:
            wx.CallAfter(self.parse_bitmap, bitmap)
            self.last_video_update = perf_counter()

    def parse_bitmap(self, bitmap: wx.Bitmap):
        image: wx.Image = bitmap.ConvertToImage()
        try:
            image = image.Rescale(*self.cover.GetSize())
        except wxAssertionError:
            image = image.Rescale(128, 72)
        self.cover.SetBitmap(image.ConvertToBitmap())
        self.main_sizer.Fit(self)

    def parse_packet(self, packet: Packet, length: int):
        if packet["type"] == HOST_NAME:
            self.text.SetLabel(packet["name"])
        self.download_counter += length
        return self.raw_parse_packet(packet, length)

    def send_packet(self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER):
        self.upload_counter += len(packet)
        return self.raw_send_packet(packet, loss_enable, priority)

    def update_data(self, _):
        if self.client.connected:
            self.text.Refresh()
            time = localtime(perf_counter() - self.client.connected_start)
            time_str = f"{str(time.tm_hour - 8).zfill(2)}:{str(time.tm_min).zfill(2)}:{str(time.tm_sec).zfill(2)}"
            self.state_infer.SetLabel(f"已连接: {time_str}")
            self.network_up.SetLabel(f"↑ {format_size(self.upload_counter / self.data_update_inv)}/s")
            self.network_down.SetLabel(
                f"↓ {format_size(self.download_counter / self.data_update_inv)}/s"
            )
            self.upload_counter = 0
            self.download_counter = 0
        else:
            self.state_infer.SetLabel("未连接")
            self.network_up.SetLabel("↑ 0B/s")
            self.network_down.SetLabel("↓ 0B/s")

    def on_open(self, _):
        if not self.client.IsShown():
            self.client.Show(True)
        self.client.Restore()
        self.client.SetFocus()


class Client(wx.Frame):
    def __init__(
        self,
        parent: wx.Frame,
        sock: socket.socket,
        address: tuple[str, int],
        uuid: bytes,
    ):
        wx.Frame.__init__(self, parent=parent, title=DEFAULT_COMPUTER_TEXT, size=(1250, 772))

        self.sock = sock
        self.address = address
        self.uuid = uuid
        self.mouse_control = False
        self.keyboard_control = False
        self.__connected = True
        self.pre_scale = True
        self.raw_title = DEFAULT_COMPUTER_TEXT
        self.sending_screen = False
        self.screen_counter = 0
        self.screen_network_counter = 0
        self.connected_start = perf_counter()
        self.packet_manager = PacketManager(self.connected, sock)
        self.files_list: dict[str, tuple[str, bytes]] = {}

        self.SetFont(font)
        self.api = ClientAPI(self)
        self.init_ui()
        self.recv_thread = start_and_return(self.packet_recv_thread, name="RecvThread")
        self.send_thread = start_and_return(self.packet_send_thread, name="SendThread")
        start_and_return(self.state_init, name="StateInit")
        self.Show()
        self.SetPosition(wx.Point(15, 110))

    # noinspection PyAttributeOutsideInit
    def init_ui(self):
        self.tab = wx.Notebook(self)

        self.screen_tab = ScreenTab(self.tab)
        self.files_panel = FilesTab(self.tab)
        self.terminal_panel = TerminalTab(self.tab)
        self.network_panel = NetworkTab(self.tab)
        self.action_panel = ActionTab(self.tab)

        self.tab.AddPage(self.screen_tab, "屏幕")
        self.tab.AddPage(self.files_panel, "文件")
        self.tab.AddPage(self.terminal_panel, "终端")
        self.tab.AddPage(self.network_panel, "网络")
        self.tab.AddPage(self.action_panel, "操作")

        self.SetIcon(GetSystemIcon(15))
        self.Bind(wx.EVT_CLOSE, self.on_close)
        parent: ClientListWindow = self.GetParent()
        self.client_card = parent.add_card(self)

    def reconnected(self, conn: socket.socket, addr: tuple[str, int], uuid: bytes):
        self.sock = conn
        self.address = addr
        self.uuid = uuid
        self.screen_counter = 0
        self.screen_network_counter = 0
        self.packet_manager = PacketManager(self.connected, conn)
        self.connected = True
        self.recv_thread = start_and_return(self.packet_recv_thread, name="RecvThread")
        self.send_thread = start_and_return(self.packet_send_thread, name="SendThread")
        self.terminal_panel.cmd_text.Clear()
        start_and_return(self.state_init, name="StateInit")

    def state_init(self):
        packet = {
            "type": STATE_INFO,
            "video_mode": self.sending_screen,
            "monitor_fps": self.screen_tab.screen_panel.controller.screen_fps_setter.input_slider.get_value(),
            "video_quality": self.screen_tab.screen_panel.controller.screen_quality_setter.input_slider.get_value(),
        }
        self.send_packet(packet)

    def packet_recv_thread(self) -> None:
        while self.connected:
            try:
                length, packet = self.recv_packet()
            except ConnectionError:
                self.connected = False
                break
            if packet is None:
                print("没有接收到数据包")
                sleep(0.001)
                continue
            if packet["type"] != SCREEN and packet["type"] != PONG:
                print("接收到数据包:", packet_str(packet))
            if not self.parse_packet(packet, length):
                return
        print("Recv Thread Exit")
        # self.Close()

    def parse_packet(self, packet: Packet, length: int) -> bool:
        """处理数据包，当需要退出时返回False"""
        if packet["type"] == KEY_EVENT:
            wx.CallAfter(self.screen_tab.key_panel.key_press, packet["key"])
        elif packet["type"] == MOUSE_EVENT:
            pass
        elif packet["type"] == SCREEN:
            start_and_return(self.parse_screen, (packet, length))
        elif packet["type"] == HOST_NAME:
            self.raw_title = packet["name"]
            self.SetTitle(self.raw_title)
        elif packet["type"] == DIR_LIST_RESULT:
            wx.CallAfter(self.files_panel.viewer.load_packet, packet)

        # 文件传输
        elif packet["type"] == FILE_VIEW_CREATE:
            self.files_list[packet["cookie"]] = (packet["path"], b"")
        elif packet["type"] == FILE_VIEW_DATA:
            path, data = self.files_list[packet["cookie"]]
            data += b64decode(packet["data"])
            self.files_list[packet["cookie"]] = (path, data)
        elif packet["type"] == FILE_VIEW_OVER:
            path, data = self.files_list[packet["cookie"]]
            wx.CallAfter(FileViewer, self, path, data)
        elif packet["type"] == FILE_VIEW_ERROR:
            wx.CallAfter(
                wx.MessageBox,
                f"无法打开文件: {packet['path']}\n{packet['error']}",
                "文件查看错误",
                wx.OK | wx.ICON_ERROR,
                parent=self,
            )

        elif packet["type"] == SHELL_OUTPUT:
            self.terminal_panel.cmd_text.load_packet(packet)
        elif packet["type"] == SHELL_BROKEN:
            wx.CallAfter(self.shell_broke_tip)
        elif packet["type"] == PONG:
            wx.CallAfter(
                self.screen_tab.screen_panel.controller.info_shower.update_delay,
                perf_counter() - packet["timer"],
            )

        return True

    def shell_broke_tip(self):
        ret = wx.MessageBox(
            "终端已损坏\n立即重启终端?",
            "终端错误",
            wx.YES_NO | wx.ICON_ERROR,
            parent=self,
        )
        if ret == 2:
            self.terminal_panel.cmd_text.restore_shell(None)

    def parse_screen(self, packet: Packet, length: int):
        data = b64decode(packet["data"])
        if packet["format"] == ScreenFormat.RAW:
            image = Image.frombuffer("RGB", packet["size"], data)
        elif packet["format"] == ScreenFormat.JPEG:
            image_io = BytesIO(data)
            image = Image.open(image_io, formats=["JPEG"]).convert("RGB")
        elif packet["format"] == ScreenFormat.PNG:
            image_io = BytesIO(data)
            image = Image.open(image_io, formats=["PNG"])
        else:
            raise RuntimeError("Error screen format")

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
        bitmap = wx.Bitmap.FromBuffer(*packet["size"], image.tobytes())
        self.set_screen(bitmap)
        self.screen_counter += 1
        self.screen_network_counter += length

    def set_screen(self, bitmap: wx.Bitmap):
        try:
            self.screen_tab.screen_panel.screen_shower.set_bitmap(bitmap)
        except RuntimeError:
            pass

    def set_pre_scale(self, enable: bool):
        self.pre_scale = enable
        packet = {"type": SET_PRE_SCALE, "enable": enable}
        self.send_packet(packet)
        self.screen_tab.screen_panel.screen_shower.on_size()

    def set_screen_fps(self, fps: int):
        packet = {"type": SET_SCREEN_FPS, "fps": fps}
        self.send_packet(packet)

    def set_screen_quality(self, quality: int):
        packet = {"type": SET_SCREEN_QUALITY, "quality": quality}
        self.send_packet(packet)

    def send_command(self, command: str):
        self.shell_send_data((command + "\r\n").encode("gbk"))

    def shell_send_data(self, data: bytes):
        packet = {"type": SHELL_INPUT, "text": b64encode(data)}
        self.send_packet(packet)

    def restore_shell(self):
        packet = {"type": SHELL_INIT}
        self.send_packet(packet)

    def set_mouse_ctl(self, enable: bool):
        self.mouse_control = enable

    def set_keyboard_ctl(self, enable: bool):
        self.keyboard_control = enable

    def set_screen_send(self, enable: bool):
        self.sending_screen = enable
        self.screen_tab.screen_panel.controller.control_setter.video_mode_ctl.SetValue(enable)
        packet = {"type": SET_SCREEN_SEND, "enable": enable}
        self.send_packet(packet)

    def on_close(self, _: wx.CloseEvent):
        self.Show(False)
        return False

    # 网络底层接口
    def packet_send_thread(self):
        self.packet_manager.packet_send_thread()
        print("Send Thread Exited")

    def send_packet(
        self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER
    ) -> None:
        if packet["type"] != PING:
            print(f"发送数据包: {packet_str(packet)}")
        self.packet_manager.send_packet(packet, loss_enable, priority)

    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]:
        return self.packet_manager.recv_packet()

    @property
    def connected(self):
        return self.__connected

    @connected.setter
    def connected(self, value: bool):
        if value:
            self.connected_start = perf_counter()
            self.SetTitle(self.raw_title)
        else:
            self.SetTitle(self.raw_title + " (未连接)")
        self.__connected = value
        self.packet_manager.connected = value


if __name__ == "__main__":
    font: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(11)
    # wx.SizerFlags.DisableConsistencyChecks()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("product")
    timer = perf_counter()
    client_list = ClientListWindow()
    print(f"初始化时间: {ms(timer)} ms")
    app.MainLoop()

# https://www.youtube.com/watch?v=0ZJ2zZ3YJL4
