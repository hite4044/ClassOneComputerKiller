import wx
import ctypes
import wx.grid
from wx import grid
from PIL import Image
from io import BytesIO
from time import localtime
from ctypes import wintypes
from typing import Callable
from win32api import GetCursorPos
from wx._core import wxAssertionError
from base64 import b64decode, b64encode
from win32com.shell import shell, shellcon  # type: ignore
from win32con import FILE_ATTRIBUTE_NORMAL
from os.path import join as path_join, normpath, abspath

app = wx.App()
from libs.action import *
from libs.widgets import *

SERVER_ADDRESS = ("127.0.0.1", 10616)
MAX_HISTORY_LENGTH = 100000
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


def extension_to_bitmap(extension) -> wx.Bitmap:
    """dot is mandatory in extension"""

    flags = (
        shellcon.SHGFI_SMALLICON
        | shellcon.SHGFI_ICON
        | shellcon.SHGFI_USEFILEATTRIBUTES
    )
    retval, info = shell.SHGetFileInfo(extension, FILE_ATTRIBUTE_NORMAL, flags)
    assert retval
    hicon, _, _, _, _ = info
    icon: wx.Icon = wx.Icon()
    icon.SetHandle(hicon)
    bmp = wx.Bitmap()
    bmp.CopyFromIcon(icon)
    return bmp


def GetSystemIcon(index: int) -> wx.Icon:
    shell32dll = ctypes.create_string_buffer(
        "C:\\Windows\\System32\\shell32.dll".encode(), 260
    )
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


class DataType:
    FILE = 0
    FOLDER = 1


class FilesData:
    def __init__(self, _type: int, name: str, item_id: wx.TreeItemId):
        self.name = name
        self.type = _type
        self.item_id = item_id

        self.name_dict: dict[str, tuple[int, wx.TreeItemId, FilesData | None]] = {}
        self.id_dict: dict[wx.TreeItemId, tuple[int, str, FilesData | None]] = {}

    def add(self, _type: int, name, item_id: wx.TreeItemId):
        if self.type == DataType.FILE:
            raise RuntimeError("Cannot add children to a file")
        self.name_dict[name] = (_type, item_id, FilesData(_type, name, item_id))
        self.id_dict[item_id] = (_type, name, FilesData(_type, name, item_id))

    def name_get(self, name: str):
        return self.name_dict[name]

    def id_get(self, item_id: wx.TreeItemId):
        return self.id_dict[item_id]

    def name_tree_get(self, names: list[str]):
        ret = self
        for name in names:
            ret = ret.name_dict[name][2]
        return ret

    def clear(self):
        self.name_dict.clear()
        self.id_dict.clear()


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
        client = Client(parent, connection, address, uuid)
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
        self.state_infer.SetFont(font)
        self.network_up.SetFont(font)
        self.network_down.SetFont(font)
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
        self.main_sizer.Add(
            self.mid_sizer, flag=wx.EXPAND | wx.ALIGN_LEFT | wx.TOP | wx.LEFT, border=9
        )
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

    def send_packet(self, packet: Packet, loss_enable: bool = False):
        self.upload_counter += len(packet)
        return self.raw_send_packet(packet, loss_enable)

    def update_data(self, _):
        if self.client.connected:
            self.text.Refresh()
            time = localtime(perf_counter() - self.client.connected_start)
            time_str = f"{str(time.tm_hour - 8).zfill(2)}:{str(time.tm_min).zfill(2)}:{str(time.tm_sec).zfill(2)}"
            self.state_infer.SetLabel(f"已连接: {time_str}")
            self.network_up.SetLabel(
                f"↑ {format_size(self.upload_counter / self.data_update_inv)}/s"
            )
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


class ScreenShower(Panel):
    def __init__(self, parent, size):
        super().__init__(parent=parent, size=size)
        self.menu: wx.Menu = ...
        self.screen_raw_size = (1920, 1080)
        self.last_size = None
        self.bmp = None
        self.last_size_send = perf_counter()
        self.last_move_send = perf_counter()
        self.client = get_client(self)
        self.button_map = {
            wx.MOUSE_BTN_LEFT: "left",
            wx.MOUSE_BTN_RIGHT: "right",
            wx.MOUSE_BTN_MIDDLE: "middle",
        }

        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)
        self.Bind(wx.EVT_RIGHT_DOWN, self.on_menu)

    def set_bitmap(self, bitmap: wx.Bitmap):
        self.bmp = bitmap
        self.OnPaint(None)

    def OnPaint(self, event: wx.PaintEvent = None):
        if self.bmp:
            dc = wx.ClientDC(self)
            dc.DrawBitmap(self.bmp, 0, 0)
            self.Refresh(False, self.GetRect())
        if event:
            event.Skip()

    def on_size(self, event: wx.Event = None):
        if self.client.pre_scale and self.client.sending_screen:
            if perf_counter() - self.last_size_send > 0.1:
                new_size = self.GetSize()
                if 0 in new_size:
                    return
                if new_size != self.last_size:
                    packet = {
                        "type": SET_SCREEN_SIZE,
                        "data_max_size": 1024 * 1024,
                        "size": tuple(new_size),
                    }
                    self.client.send_packet(packet)
                    self.last_size = new_size
                    self.last_size_send = perf_counter()
        if event:
            event.Skip()

    def on_menu(self, _):
        menu = wx.Menu()
        menu.Append(1, "获取屏幕")
        item: wx.MenuItem = menu.Append(2, "视频模式", kind=wx.ITEM_CHECK)
        menu.Bind(wx.EVT_MENU, self.send_get_screen, id=1)
        menu.Bind(wx.EVT_MENU, self.send_video_mode, id=2)
        item.Check(self.client.sending_screen)
        self.PopupMenu(menu)
        self.menu = menu

    def send_get_screen(self, _):
        packet = {"type": GET_SCREEN}
        self.client.send_packet(packet)

    def send_video_mode(self, _):
        self.client.set_screen_send(not self.client.sending_screen)

    def on_mouse(self, event: wx.MouseEvent):
        if self.client.mouse_control:
            packet = None
            if event.Moving() and perf_counter() - self.last_move_send > 0.1:
                packet = {"type": SET_MOUSE_POS, "x": event.GetX(), "y": event.GetY()}
                self.last_move_send = perf_counter()
            elif event.IsButton():
                if event.ButtonDown():
                    packet = {
                        "type": SET_MOUSE_BUTTON,
                        "button": self.button_map[event.GetButton()],
                        "state": 0,
                        "x": event.GetX(),
                        "y": event.GetY(),
                    }
                elif event.ButtonUp():
                    packet = {
                        "type": SET_MOUSE_BUTTON,
                        "button": self.button_map[event.GetButton()],
                        "state": 1,
                        "x": event.GetX(),
                        "y": event.GetY(),
                    }

            if packet:
                self.client.send_packet(packet)
        if event:
            event.Skip()


class ComputerControlSetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.text = wx.StaticText(self, label="电脑控制:")
        self.mouse_ctl = wx.CheckBox(self, label="鼠标控制")
        self.mouse_ctl.Bind(
            wx.EVT_CHECKBOX,
            lambda _: self.client.set_mouse_ctl(self.mouse_ctl.GetValue()),
        )
        self.keyboard_ctl = wx.CheckBox(self, label="键盘控制")
        self.keyboard_ctl.Bind(
            wx.EVT_CHECKBOX,
            lambda _: self.client.set_keyboard_ctl(self.keyboard_ctl.GetValue()),
        )
        self.video_mode_ctl = wx.CheckBox(self, label="视频模式")
        self.video_mode_ctl.Bind(
            wx.EVT_CHECKBOX,
            lambda _: self.client.set_screen_send(self.video_mode_ctl.GetValue()),
        )
        self.get_screen_btn = wx.Button(self, label="获取屏幕")
        self.get_screen_btn.Bind(wx.EVT_BUTTON, self.send_get_screen)
        self.client = get_client(self)

        self.text.SetFont(ft(14))
        self.mouse_ctl.SetFont(ft(13))
        self.keyboard_ctl.SetFont(ft(13))
        self.video_mode_ctl.SetFont(ft(13))
        self.get_screen_btn.SetFont(ft(11))

        self.sizer.AddSpacer(10)
        self.sizer.Add(self.text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(20)
        self.sizer.Add(self.mouse_ctl, flag=wx.ALIGN_LEFT | wx.EXPAND)
        self.sizer.AddSpacer(20)
        self.sizer.Add(self.keyboard_ctl, flag=wx.ALIGN_LEFT | wx.EXPAND)
        self.sizer.AddSpacer(20)
        self.sizer.Add(self.video_mode_ctl, flag=wx.ALIGN_LEFT | wx.EXPAND)
        self.sizer.AddSpacer(20)
        self.sizer.Add(
            self.get_screen_btn,
            flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP | wx.BOTTOM,
            border=1,
        )
        self.SetSizer(self.sizer)

    def send_get_screen(self, _):
        packet = {"type": GET_SCREEN, "size": tuple(self.GetSize())}
        self.client.send_packet(packet)


class FormatRadioButton(wx.RadioButton):
    def __init__(self, parent, text: str, value, cbk):
        super().__init__(parent=parent, label=text)
        self.Bind(wx.EVT_RADIOBUTTON, lambda _: cbk(value))
        self.Bind(wx.EVT_SIZE, lambda _: self.Update())


class PreScaleCheckBox(wx.CheckBox):
    def __init__(self, parent):
        super().__init__(parent=parent, label="预缩放")
        self.Bind(wx.EVT_CHECKBOX, self.OnSwitch)
        self.SetValue(True)

    def OnSwitch(self, _):
        enable = self.GetValue()
        get_client(self).set_pre_scale(enable)


class ScreenFormatSetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.text = wx.StaticText(self, label="屏幕格式:")
        self.jpg_button = FormatRadioButton(
            self, "JPG", ScreenFormat.JPEG, self.set_format
        )
        self.png_button = FormatRadioButton(
            self, "PNG", ScreenFormat.PNG, self.set_format
        )
        self.raw_button = FormatRadioButton(
            self, "Raw", ScreenFormat.RAW, self.set_format
        )
        self.pre_scale_box = PreScaleCheckBox(self)

        self.sizer.AddSpacer(10)
        self.sizer.Add(self.text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(15)
        self.sizer.Add(self.jpg_button, flag=wx.ALIGN_LEFT | wx.EXPAND)
        self.sizer.AddSpacer(25)
        self.sizer.Add(self.png_button, flag=wx.ALIGN_LEFT | wx.EXPAND)
        self.sizer.AddSpacer(25)
        self.sizer.Add(self.raw_button, flag=wx.ALIGN_LEFT | wx.EXPAND)
        self.sizer.AddSpacer(25)
        self.sizer.Add(self.pre_scale_box, flag=wx.ALIGN_LEFT | wx.EXPAND)

        self.jpg_button.SetValue(True)
        self.sizer.Layout()
        self.SetSizer(self.sizer)
        self.text.SetFont(ft(14))
        self.jpg_button.SetFont(ft(13))
        self.png_button.SetFont(ft(13))
        self.raw_button.SetFont(ft(13))
        self.pre_scale_box.SetFont(ft(13))

        BToolTip(self.text, "在屏幕的网络传输中使用的格式", ft(10))
        BToolTip(self.pre_scale_box, "占用更少带宽", ft(10))
        BToolTip(self.jpg_button, "带宽: 小, 质量: 高, 性能: 快", ft(10))
        BToolTip(self.png_button, "带宽: 中, 质量: 无损, 性能: 慢", ft(10))
        BToolTip(self.raw_button, "带宽: 大, 质量: 无损, 性能: 快", ft(10))

        self.format_lock = Lock()
        self.Update()

    def set_format(self, value: str):
        controller = get_client(self).screen_tab.screen_panel.screen_controller
        if value != ScreenFormat.JPEG:
            controller.sizer.Hide(controller.screen_quality_setter)
        else:
            controller.sizer.Show(controller.screen_quality_setter)
        start_and_return(self._set_format, (value,))

    def _set_format(self, value: str):
        with self.format_lock:
            packet = {"type": SET_SCREEN_FORMAT, "format": value}
            client: Client = get_client(self)
            if client.connected:
                client.send_packet(packet)


class ScreenFPSSetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.StaticText(self, label="监视帧率:")
        self.input_slider = InputSlider(self, value=10, _min=1, _max=60, _from=0, to=60)

        self.sizer.AddSpacer(10)
        self.sizer.Add(self.text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(15)
        self.sizer.Add(self.input_slider, flag=wx.ALIGN_LEFT | wx.EXPAND)

        BToolTip(self.text, "屏幕传输的帧率\n帧率越高, 带宽占用越大", ft(10))

        self.text.SetFont(ft(14))
        self.input_slider.cbk = get_client(self).set_screen_fps
        self.SetSizer(self.sizer)
        self.Update()


class ScreenQualitySetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.StaticText(self, label="屏幕质量:")
        self.input_slider = InputSlider(
            self, value=80, _min=1, _max=100, _from=0, to=100
        )

        self.sizer.AddSpacer(10)
        self.sizer.Add(self.text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(15)
        self.sizer.Add(self.input_slider, flag=wx.ALIGN_LEFT | wx.EXPAND)

        BToolTip(self.text, "屏幕传输的质量\n质量越高, 带宽占用越大", ft(10))
        self.text.SetFont(ft(14))
        self.input_slider.cbk = get_client(self).set_screen_quality
        self.SetSizer(self.sizer)


class ScreenInformationShower(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 32))

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.FPS_text = wx.StaticText(self, label="FPS: 0")
        self.network_text = wx.StaticText(self, label="占用带宽: 0 KB/s")
        self.sizer.AddSpacer(10)
        self.sizer.Add(self.FPS_text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(100)
        self.sizer.Add(
            self.network_text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3
        )

        BToolTip(self.FPS_text, "反映了屏幕传输的流畅度", ft(10))
        BToolTip(self.network_text, "屏幕传输占用的带宽", ft(10))
        self.SetSizer(self.sizer)
        self.FPS_text.SetFont(ft(14))
        self.network_text.SetFont(ft(14))

        self.fps_avg = []
        self.network_avg = []
        self.collect_inv = 0.5
        self.client = get_client(self)
        self.FPS_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_data, self.FPS_timer)
        self.FPS_timer.Start(int(self.collect_inv * 1000))

    def update_data(self, event: wx.TimerEvent = None):
        self.update_fps()
        self.update_network()
        if event:
            event.Skip()

    def update_fps(self):
        self.fps_avg.append(self.client.screen_counter / self.collect_inv)
        self.client.screen_counter = 0
        if len(self.fps_avg) > 10:
            self.fps_avg.pop(0)
        self.FPS_text.SetLabel(
            "FPS: " + str(round(sum(self.fps_avg) / len(self.fps_avg), 1))
        )

    def update_network(self):
        self.network_avg.append(self.client.screen_network_counter / self.collect_inv)
        self.client.screen_network_counter = 0
        if len(self.network_avg) > 10:
            self.network_avg.pop(0)
        self.network_text.SetLabel(
            "占用带宽: "
            + format_size(sum(self.network_avg) / len(self.network_avg))
            + " /s"
        )


class ScreenController(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1270, 160))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.control_setter = ComputerControlSetter(self)
        self.screen_format_setter = ScreenFormatSetter(self)
        self.screen_fps_setter = ScreenFPSSetter(self)
        self.screen_quality_setter = ScreenQualitySetter(self)
        self.screen_information_shower = ScreenInformationShower(self)
        self.sizer.Add(self.control_setter, flag=wx.ALIGN_TOP | wx.EXPAND)
        # self.sizer.AddSpacer(2)
        self.sizer.Add(wx.StaticLine(self), flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Add(self.screen_format_setter, flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Add(self.screen_fps_setter, flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Add(
            self.screen_quality_setter,
            flag=wx.ALIGN_TOP | wx.EXPAND | wx.RESERVE_SPACE_EVEN_IF_HIDDEN,
        )
        self.sizer.AddSpacer(3)
        self.sizer.Add(wx.StaticLine(self), flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Add(self.screen_information_shower, flag=wx.ALIGN_TOP | wx.EXPAND)
        # self.sizer.Layout()
        self.SetSizer(self.sizer)


class ScreenPanel(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(960, 1112))
        self.screen_shower = ScreenShower(self, (int(1920 / 2), int(1080 / 2)))
        self.screen_controller = ScreenController(self)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.screen_shower, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=1)
        self.sizer.Add(
            self.screen_controller, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=0
        )
        self.sizer.Layout()
        self.SetSizer(self.sizer)

        self.screen_shower.SetSize((int(1920 / 1.5), int(1080 / 1.5)))


class KeyMonitorPanel(Panel):
    def __init__(self, parent: wx.Window):
        super().__init__(parent=parent, size=(220, 680))
        self.sizer = wx.StaticBoxSizer(wx.VERTICAL, self, "键盘监听")
        self.key_monitor = wx.ListBox(self, size=MAX_SIZE, style=wx.LB_HSCROLL)
        self.sizer.Add(self.key_monitor, flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Layout()
        self.SetSizer(self.sizer)
        self.index = 0

        self.key_monitor.SetFont(ft(10))
        self.key_monitor.Append("")
        self.key_monitor.Bind(wx.EVT_RIGHT_DOWN, self.on_menu)

    def add_string(self, s: str):
        try:
            s = self.key_monitor.GetString(self.index) + s
            self.key_monitor.SetString(self.index, s)
        except wxAssertionError:
            self.key_monitor.Append(s)

    def key_press(self, key: str):
        if key == "enter":
            self.add_string("↴")
            self.index += 1
            self.add_string("")
            return
        elif len(key) > 1:
            key = f"[{key}]"
        self.add_string(key)

    def on_menu(self, _):
        menu = wx.Menu()
        menu.Append(1, "清空")
        self.Bind(wx.EVT_MENU, self.clear, id=1)
        self.PopupMenu(menu)
        menu.Destroy()

    def clear(self, _):
        self.key_monitor.Clear()
        self.key_monitor.Append("")
        self.index = 0


class ScreenTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=MAX_SIZE)
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.screen_panel = ScreenPanel(self)
        self.key_panel = KeyMonitorPanel(self)

        self.sizer.Add(self.screen_panel, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=32)
        self.sizer.Add(self.key_panel, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=9)
        self.sizer.SetItemMinSize(self.key_panel, 250, 700)
        self.sizer.Layout()
        self.SetSizer(self.sizer)


class FilesTreeView(wx.TreeCtrl):
    def __init__(self, parent):
        super().__init__(
            parent=parent, size=MAX_SIZE, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT
        )
        self.SetFont(font)

        self.image_list = wx.ImageList(16, 16, True)
        self.folder_icon = self.image_list.Add(
            wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
        )
        self.default_file_icon = self.image_list.Add(
            wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
        )
        self.icons = {}
        self.AssignImageList(self.image_list)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.on_expend)

        self.client = get_client(self)
        self.load_over_flag = False

        root = self.AddRoot("命根子")
        self.files_data: FilesData = FilesData(DataType.FOLDER, "root", root)
        c_disk = self.AppendItem(root, "C:", image=self.folder_icon)
        d_disk = self.AppendItem(root, "D:", image=self.folder_icon)
        self.AppendItem(c_disk, "加载中...")
        self.AppendItem(d_disk, "加载中...")
        self.files_data.add(DataType.FOLDER, "C:", c_disk)
        self.files_data.add(DataType.FOLDER, "D:", d_disk)

        self.Bind(wx.EVT_TREE_ITEM_MENU, self.on_menu)

    def load_packet(self, packet: Packet):
        root_path = packet["path"]
        dirs = packet["dirs"]
        files = packet["files"]

        paths = normpath(root_path).split("\\")
        paths.pop(-1) if paths[-1] == "" else None
        correct_dir = self.files_data.name_tree_get(paths)
        root_id = correct_dir.item_id

        correct_dir.clear()
        self.DeleteChildren(root_id)

        for dir_name in dirs:
            item_id = self.AppendItem(root_id, dir_name, image=self.folder_icon)
            self.AppendItem(item_id, "加载中...")
            correct_dir.add(DataType.FOLDER, dir_name, item_id)
        for file_name in files:
            assert isinstance(file_name, str)
            if "." in file_name:
                extension = file_name.split(".")[-1]
                if extension not in self.icons:
                    self.icons[extension] = self.image_list.Add(
                        extension_to_bitmap("." + extension)
                    )
                icon = self.icons[extension]
            else:
                icon = self.default_file_icon
            item_id = self.AppendItem(root_id, file_name, image=icon)
            correct_dir.add(DataType.FILE, file_name, item_id)
        if len(dirs + files) != 0:
            self.load_over_flag = True
            self.Expand(root_id)

    def on_expend(self, event: wx.TreeEvent):
        if self.load_over_flag:
            self.load_over_flag = False
            return
        item = event.GetItem()
        text: wx.TreeItemId = self.GetLastChild(item)
        if text.IsOk() and self.GetItemText(text) == "加载中...":
            self.request_list_dir(item)
            event.Veto()

    def get_item_path(self, item: wx.TreeItemId):
        path = ""
        while True:
            if item == self.GetRootItem():
                break
            name = str(self.GetItemText(item))
            if ":" in name:
                name += "\\"
            path = path_join(name, path)
            item = self.GetItemParent(item)
        return path

    def request_list_dir(self, item: wx.TreeItemId):
        self._request_list_dir(self.get_item_path(item))

    def _request_list_dir(self, path: str):
        packet = {"type": REQ_LIST_DIR, "path": path}
        self.load_over_flag = False
        self.client.send_packet(packet)

    def on_menu(self, event: wx.TreeEvent):
        item_id: wx.TreeItemId = event.GetItem()
        if not item_id.IsOk():
            return
        path = normpath(self.get_item_path(item_id))
        paths = path.split("\\")
        paths.pop(-1) if paths[-1] == "" else None
        files_data: FilesData = self.files_data.name_tree_get(paths)

        menu = wx.Menu()
        if files_data.type == DataType.FILE:
            menu.Append(1, "查看内容")
            menu.Append(2, "下载")
            menu.Append(3, "删除")
            menu.Append(4, "属性")
            menu.Bind(wx.EVT_MENU, lambda _: self.view_file(path), id=1)
            menu.Bind(wx.EVT_MENU, lambda _: self.delete_path(path, item_id), id=3)
        elif files_data.type == DataType.FOLDER:
            menu.Append(1, "刷新此文件夹")
            menu.Append(2, "删除")
            menu.Append(3, "属性")
            menu.Bind(wx.EVT_MENU, lambda _: self.refresh_dir(path, item_id), id=1)
        self.PopupMenu(menu)

    def view_file(self, path: str):
        path = normpath(path)
        packet = {"type": FILE_VIEW, "path": path, "data_max_size": 1024 * 100}
        self.client.send_packet(packet)

    def refresh_dir(self, path: str, item_id: wx.TreeItemId):
        path = normpath(path)
        self.Collapse(item_id)
        self._request_list_dir(path)

    def delete_path(self, path: str, item_id: wx.TreeItemId):
        packet = {"type": FILE_DELETE, "path": path}
        self.client.send_packet(packet)
        self.Delete(item_id)


class FileTransport(wx.ScrolledWindow):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(400, 668))
        self.sizer = wx.BoxSizer(wx.VERTICAL)


class FileTransport(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(400, 668))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_bar = wx.Gauge(self, range=100)


class FilesTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.files_view_panel = FilesTreeView(self)
        self.files_transport_panel = FileTransport(self)
        self.sizer.Add(self.files_view_panel, flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Add(self.files_transport_panel, flag=wx.ALIGN_TOP | wx.EXPAND)
        self.sizer.Layout()
        self.SetSizer(self.sizer)


class FileViewer(wx.Frame):
    def __init__(self, parent: wx.Frame, path: str, data: bytes):
        wx.Frame.__init__(self, parent=parent, title=path, size=(800, 600))
        self.path = normpath(path)
        self.data = data

        self.text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        encodes = [
            "utf-8",
            "gbk",
            "utf-16",
            "gb2312",
            "gb18030",
            "big5",
            "shift_jis",
            "euc_jp",
            "cp932",
        ]
        for encode in encodes:
            try:
                self.text.AppendText(data.decode(encode))
                break
            except UnicodeDecodeError:
                pass
        else:
            self.text.AppendText(data.decode("utf-8", "ignore"))

        self.font_size = 11
        self.ctrl_down = False
        self.text.SetFont(ft(self.font_size))
        self.text.Bind(wx.EVT_MOUSEWHEEL, self.on_scroll)
        self.text.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        self.text.Bind(wx.EVT_KEY_UP, self.on_key_up)

        menu_bar = wx.MenuBar()
        menu = wx.Menu()
        menu_bar.Append(menu, "另存为")
        menu.Bind(wx.EVT_MENU_OPEN, self.save_as)
        self.SetMenuBar(menu_bar)

        self.Show()

    def save_as(self, event: wx.MenuEvent):
        try:
            extension = self.path.split(".")[-1]
        except IndexError:
            extension = "*"
        file_name = self.path.split("\\")[-1]
        with wx.FileDialog(
            self,
            "另存为",
            wildcard="*." + extension,
            defaultFile=file_name,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as file_dialog:
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return
            path = file_dialog.GetPath()
            with open(path, "wb") as f:
                f.write(self.data)
        event.Skip()

    def on_key_down(self, event: wx.KeyEvent):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            self.ctrl_down = True
        event.Skip()

    def on_key_up(self, event: wx.KeyEvent):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            self.ctrl_down = False
        event.Skip()

    def on_scroll(self, event: wx.MouseEvent):
        if self.ctrl_down:
            if event.GetWheelRotation() > 0:
                self.font_size += 1
            else:
                self.font_size -= 1
            self.text.SetFont(ft(self.font_size))
        event.Skip()


class TerminalText(wx.TextCtrl):
    def __init__(self, parent):
        wx.TextCtrl.__init__(
            self,
            parent=parent,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_CHARWRAP,
            size=(1226, 700),
        )
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_menu)
        self.client = get_client(self)
        self.SetForegroundColour(wx.Colour(204, 204, 204))
        self.SetBackgroundColour(wx.Colour(14, 14, 14))

        pixel_font = wx.Font(
            12,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
            False,
            "宋体",
        )
        self.SetFont(pixel_font)

    def load_packet(self, packet: Packet):
        output: str = packet["output"]
        if chr(12) in output:
            self.Clear()
            output = output[output.find(chr(12)) + 1 :]
        if len(self.GetValue()) > MAX_HISTORY_LENGTH:
            self.Remove(0, self.GetLastPosition() - MAX_HISTORY_LENGTH)
        self.AppendText(output)

    def on_menu(self, _: wx.MenuEvent):
        menu = wx.Menu()
        menu.Append(1, "清空")
        menu.Append(2, "重启终端")
        menu.Bind(wx.EVT_MENU, self.clear_and_send, id=1)
        menu.Bind(wx.EVT_MENU, self.restore_shell, id=2)
        self.PopupMenu(menu)

    def clear_and_send(self, event: wx.MenuEvent):
        self.client.send_command("")
        self.Clear()
        event.Skip()

    def restore_shell(self, _):
        self.Clear()
        self.client.restore_shell()


class TerminalInput(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 32))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.TextCtrl(self, size=(1200, 28), style=wx.TE_PROCESS_ENTER)
        self.send_button = wx.Button(self, label="发送", size=(75, 31))
        self.sizer.Add(
            self.text, flag=wx.ALIGN_TOP | wx.EXPAND | wx.TOP, border=1, proportion=1
        )
        self.sizer.AddSpacer(3)
        self.sizer.Add(self.send_button, flag=wx.ALIGN_TOP, proportion=0)
        self.sizer.AddSpacer(2)
        self.SetSizer(self.sizer)

        self.tip_text = "请输入命令"
        self.on_tip = False
        self.has_focus = False
        self.normal_color = self.GetForegroundColour()
        self.gray_color = wx.Colour((76, 76, 76))
        self.client = get_client(self)
        self.text.Bind(wx.EVT_SET_FOCUS, self.on_focus)
        self.text.Bind(wx.EVT_KILL_FOCUS, self.on_focus_out)
        self.text.Bind(wx.EVT_KEY_DOWN, self.on_enter)
        self.text.SetFont(font)
        self.send_button.Bind(wx.EVT_BUTTON, lambda _: self.send())
        self.on_focus_out()
        self.send_button.SetFont(ft(10))

        self.command_history = []
        self.history_index = 0

    def on_focus(self, event: wx.FocusEvent):
        self.has_focus = True
        if self.on_tip:
            self.text.SetValue("")
            self.text.SetForegroundColour(self.normal_color)
            self.on_tip = False
        event.Skip()

    def on_focus_out(self, event: wx.FocusEvent = None):
        self.has_focus = False
        wx.CallLater(100, self.check_insert_tip)
        if event:
            event.Skip()

    def check_insert_tip(self):
        if not self.has_focus:
            if self.text.GetValue() == "":
                self.text.SetValue(self.tip_text)
                self.text.SetForegroundColour(self.gray_color)
                self.on_tip = True

    def on_enter(self, event: wx.KeyEvent):
        if (
            event.GetKeyCode() == wx.WXK_NUMPAD_ENTER
            or event.GetKeyCode() == wx.WXK_RETURN
        ):
            self.send()
        elif event.GetKeyCode() == wx.WXK_UP:
            if self.history_index > 0:
                self.history_index -= 1
                self.text.SetValue(self.command_history[self.history_index])
                self.text.SetInsertionPointEnd()
        elif event.GetKeyCode() == wx.WXK_DOWN:
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.text.SetValue(self.command_history[self.history_index])
                self.text.SetInsertionPointEnd()
        else:
            event.Skip()

    def send(self):
        self.text.SetFocus()
        if self.text.GetValue() != "":
            self.command_history.append(self.text.GetValue())
        self.history_index = len(self.command_history)
        self.client.send_command(self.text.GetValue())
        self.text.Clear()


class TerminalTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.text = TerminalText(self)
        self.inputter = TerminalInput(self)
        self.sizer.Add(self.text, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=1)
        self.sizer.AddSpacer(3)
        self.sizer.Add(self.inputter, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=0)
        self.SetSizer(self.sizer)


class NetworkTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.StaticText(self, label="byd不想做, 感觉没用")
        self.sizer.Add(self.text)
        self.SetSizer(self.sizer)

        self.text.SetFont(ft(90))


class ActionGrid(grid.Grid):
    def __init__(self, parent: wx.Window):
        super().__init__(parent, size=MAX_SIZE)
        self.CreateGrid(1, 4)
        gui_data = [
            ("名称", 100),
            ("触发条件", 300),
            ("执行操作", 180),
            ("停止条件", 300),
        ]

        for i in range(len(gui_data)):
            name, width = gui_data[i]
            self.SetColLabelValue(i, name)
            self.SetColSize(i, width)
        self.datas: list[TheAction] = []
        self.first_add = True
        self.SetDefaultCellAlignment(wx.ALIGN_CENTER, wx.ALIGN_CENTER)

        self.SetRowLabelSize(1)
        self.EnableEditing(False)
        self.SetLabelFont(font)
        self.SetDefaultCellFont(font)

    def add_action(
        self,
        name: str,
        start_prqs: list[StartPrq],
        end_prqs: list[EndPrq],
        actions: list[AnAction],
    ):
        if self.first_add:
            self.AppendRows(1)
            self.first_add = False
        row = self.GetNumberRows() - 1
        
        self.SetCellValue(row, 0, name)
        self.SetCellValue(row, 1, " ".join([start.name() for start in start_prqs]))
        self.SetCellValue(row, 2, " ".join([action.name() for action in actions]))
        self.SetCellValue(row, 3, " ".join([end.name() for end in end_prqs]))
        self.datas.append(TheAction(name, actions, start_prqs, end_prqs))
        
    def build_action_packet(self, the_action: TheAction) -> Packet:
        return the_action.build_packet()


class StartPrqList(AddableList):
    def __init__(self, parent):
        super().__init__(parent, "开始条件")

    def on_add(self):
        ItemChoiceDialog(
            self, "选择开始条件", [("1", "条件1"), ("2", "条件2")], self.add_callback
        )

    def add_callback(self, name: str, data: str):
        self.add_item(name, data)


class EndPrqList(AddableList):
    def __init__(self, parent):
        super().__init__(parent, "结束条件")

    def on_add(self):
        ItemChoiceDialog(
            self, "选择结束条件", [("1", "条件1"), ("2", "条件2")], self.add_callback
        )

    def add_callback(self, name: str, data: str):
        self.add_item(name, data)


class ActionAddDialog(wx.Frame):
    def __init__(self, parent):
        assert isinstance(parent, ActionEditor)
        super().__init__(get_client(parent), title="动作编辑器", size=(420, 390))
        self.action_editor = parent
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.name_inputter = LabelEntry(self, "名称: ")
        self.prq_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_prqs = StartPrqList(self)
        self.end_prqs = EndPrqList(self)
        self.actions_chooser = LabelCombobox(
            self, "动作: ", [("动作1", "114514"), ("动作2", "54188")]
        )
        self.bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_btn = wx.Button(self, label="确定")
        self.cancel_btn = wx.Button(self, label="取消")

        for i in range(10):
            self.start_prqs.listbox.Append(f"Test:{i}")
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.ok_btn.SetFont(ft(12))
        self.cancel_btn.SetFont(ft(12))
        self.name_inputter.label_ctl.SetFont(ft(13))
        self.name_inputter.text.SetFont(ft(12))
        self.actions_chooser.label_ctl.SetFont(ft(13))
        self.actions_chooser.combobox.SetFont(ft(12))

        self.sizer.Add(self.name_inputter, proportion=0)
        self.sizer.AddSpacer(6)
        self.prq_sizer.Add(self.start_prqs, flag=wx.EXPAND, proportion=50)
        self.prq_sizer.AddSpacer(6)
        self.prq_sizer.Add(self.end_prqs, flag=wx.EXPAND, proportion=50)
        self.sizer.Add(self.prq_sizer, wx.EXPAND)
        self.sizer.AddSpacer(6)
        self.sizer.Add(self.actions_chooser, proportion=0)
        self.bottom_sizer.Add(self.ok_btn, proportion=0)
        self.bottom_sizer.AddSpacer(6)
        self.bottom_sizer.Add(self.cancel_btn, proportion=0)
        self.sizer.Add(self.bottom_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=6)
        self.SetSizer(self.sizer)
        self.SetIcon(wx.Icon(abspath(r"assets\action_editor.ico")))
        self.Show()

    def on_ok(self, _):
        name = self.name_inputter.text.GetValue()
        start_prqs = self.start_prqs.get_items()
        end_prqs = self.end_prqs.get_items()
        if start_prqs == []:
            start_prqs.append(NoneStartPrq())
        if end_prqs == []:
            end_prqs.append(NoneEndPrq())
        action = BlueScreenAction()
        actions = [action]
        self.action_editor.add_action(name, start_prqs, end_prqs, actions)
        self.Close()

    def on_cancel(self, _):
        self.Close()


class ActionEditor(Panel):
    def __init__(self, parent: wx.Window):
        super().__init__(parent, size=MAX_SIZE)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.action_grid = ActionGrid(self)

        self.control_bar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.action_add_btn = wx.Button(self, label="添加操作")
        self.action_remove_btn = wx.Button(self, label="删除操作")
        self.action_add_btn.Bind(wx.EVT_BUTTON, self.on_add_action)
        self.action_add_btn.SetFont(font)
        self.action_remove_btn.SetFont(font)
        self.action_grid.SetWindowStyle(wx.SIMPLE_BORDER)
        self.control_bar_sizer.Add(self.action_add_btn)
        self.control_bar_sizer.AddSpacer(6)
        self.control_bar_sizer.Add(self.action_remove_btn)

        self.sizer.Add(
            self.control_bar_sizer,
            flag=wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT,
            border=6,
        )
        self.sizer.Add(self.action_grid, flag=wx.EXPAND | wx.ALL, border=6)
        self.SetSizer(self.sizer)

    def on_add_action(self, _):
        ActionAddDialog(self)

    def add_action(
        self, name: str, start_prqs: list, end_prqs: list, actions: list[AnAction]
    ):
        self.action_grid.add_action(name, start_prqs, end_prqs, actions)


class ActionList(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(250, 703))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.text = wx.StaticText(self, label="操作列表", style=wx.ALIGN_LEFT)
        bmp = wx.Bitmap()
        bmp.LoadFile(abspath(r"assets\add.png"), wx.BITMAP_TYPE_PNG)
        self.add_btn = wx.BitmapButton(self, bitmap=bmp)
        self.action_listbox = wx.ListBox(self, style=wx.LB_SINGLE)
        self.text.SetFont(ft(13))
        self.action_listbox.SetFont(font)

        self.top_sizer.Add(
            self.text, flag=wx.EXPAND | wx.TOP | wx.LEFT, proportion=1, border=4
        )
        self.top_sizer.Add(self.add_btn, flag=wx.TOP | wx.RIGHT, proportion=0, border=4)
        self.sizer.Add(
            self.top_sizer,
            flag=wx.ALIGN_TOP | wx.EXPAND | wx.LEFT | wx.RIGHT,
            proportion=0,
            border=3,
        )
        self.sizer.Add(
            self.action_listbox,
            flag=wx.ALIGN_TOP | wx.EXPAND | wx.ALL,
            proportion=1,
            border=5,
        )
        self.SetSizer(self.sizer)
        self.SetWindowStyle(wx.SIMPLE_BORDER)

        for action in Actions.action_list:
            self.action_listbox.Append(action.label)


class ActionTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.action_editor = ActionEditor(self)
        self.action_list = ActionList(self)
        self.sizer.Add(self.action_editor, flag=wx.EXPAND, proportion=1)
        self.sizer.Add(
            self.action_list, flag=wx.EXPAND | wx.ALL, proportion=0, border=5
        )
        self.SetSizer(self.sizer)


class Client(wx.Frame):
    def __init__(
        self,
        parent: wx.Frame,
        sock: socket.socket,
        address: tuple[str, int],
        uuid: bytes,
    ):
        wx.Frame.__init__(
            self, parent=parent, title=DEFAULT_COMPUTER_TEXT, size=(1250, 772)
        )

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

        self.init_ui()
        self.recv_thread = start_and_return(self.packet_recv_thread, name="RecvThread")
        self.send_thread = start_and_return(self.packet_send_thread, name="SendThread")
        self.Show()
        self.SetPosition(wx.Point(15, 110))
        self.SetFont(font)

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

        self.tab.SetFont(font)

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
        start_and_return(self.state_init, name="StateInit")

    def state_init(self):
        packet = {
            "type": STATE_INFO,
            "video_mode": self.sending_screen,
            "monitor_fps": self.screen_tab.screen_panel.screen_controller.screen_fps_setter.input_slider.get_value(),
            "monitor_quality": self.screen_tab.screen_panel.screen_controller.screen_quality_setter.input_slider.get_value(),
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
            if packet["type"] != SCREEN:
                print("接收到数据包:", packet)
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
            self.files_panel.files_view_panel.load_packet(packet)

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
            self.terminal_panel.text.load_packet(packet)
        elif packet["type"] == SHELL_BROKEN:
            wx.CallAfter(self.shell_broke_tip)
        return True

    def shell_broke_tip(self):
        ret = wx.MessageBox(
            "终端已损坏\n立即重启终端?",
            "终端错误",
            wx.YES_NO | wx.ICON_ERROR,
            parent=self,
        )
        if ret == 2:
            self.terminal_panel.text.restore_shell(None)

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
        self.screen_tab.screen_panel.screen_controller.control_setter.video_mode_ctl.SetValue(
            enable
        )
        packet = {"type": SET_SCREEN_SEND, "enable": enable}
        self.send_packet(packet)

    def on_close(self, _: wx.CloseEvent):
        self.Show(False)
        return False

    # 网络底层接口
    def packet_send_thread(self):
        self.packet_manager.packet_send_thread()
        print("Send Thread Exited")

    def send_packet(self, packet: Packet, loss_enable: bool = False) -> None:
        print(f"发送数据包: {packet}")
        self.packet_manager.send_packet(packet, loss_enable)

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


def get_client(widget: wx.Window) -> Client:
    while True:
        widget: wx.Window = widget.GetParent()
        if isinstance(widget, Client):
            return widget


if __name__ == "__main__":
    font: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(11)
    # wx.SizerFlags.DisableConsistencyChecks()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("product")
    timer = perf_counter()
    client_list = ClientListWindow()
    print(f"初始化时间: {perf_counter() - timer}")
    app.MainLoop()

# https://www.youtube.com/watch?v=0ZJ2zZ3YJL4
