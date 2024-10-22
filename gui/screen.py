import wx
from gui.widgets import *
from libs.api import get_api
from wx._core import wxAssertionError


class ScreenShower(Panel):
    def __init__(self, parent, size):
        super().__init__(parent=parent, size=size)
        self.menu: wx.Menu = ...
        self.screen_raw_size = (1920, 1080)
        self.last_size = None
        self.bmp = None
        self.last_size_send = perf_counter()
        self.last_move_send = perf_counter()
        self.api = get_api(self)
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
        if self.api.pre_scale and self.api.sending_screen:
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
                    self.api.send_packet(packet)
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
        item.Check(self.api.sending_screen)
        self.PopupMenu(menu)
        self.menu = menu

    def send_get_screen(self, _):
        packet = {"type": GET_SCREEN}
        self.api.send_packet(packet)

    def send_video_mode(self, _):
        self.api.set_screen_send(not self.api.sending_screen)

    def on_mouse(self, event: wx.MouseEvent):
        if self.api.mouse_control:
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
                self.api.send_packet(packet)
        if event:
            event.Skip()


class ComputerControlSetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.SetFont(ft(13))
        self.text = wx.StaticText(self, label="电脑控制:")
        self.mouse_ctl = wx.CheckBox(self, label="鼠标控制")
        self.mouse_ctl.Bind(
            wx.EVT_CHECKBOX,
            lambda _: self.api.set_mouse_ctl(self.mouse_ctl.GetValue()),
        )
        self.keyboard_ctl = wx.CheckBox(self, label="键盘控制")
        self.keyboard_ctl.Bind(
            wx.EVT_CHECKBOX,
            lambda _: self.api.set_keyboard_ctl(self.keyboard_ctl.GetValue()),
        )
        self.video_mode_ctl = wx.CheckBox(self, label="视频模式")
        self.video_mode_ctl.Bind(
            wx.EVT_CHECKBOX,
            lambda _: self.api.set_screen_send(self.video_mode_ctl.GetValue()),
        )
        self.get_screen_btn = wx.Button(self, label="获取屏幕")
        self.get_screen_btn.Bind(wx.EVT_BUTTON, self.send_get_screen)
        self.api = get_api(self)

        self.text.SetFont(ft(14))

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
        self.api.send_packet(packet)


class FormatRadioButton(wx.RadioButton):
    def __init__(self, parent, text: str, value, cbk):
        super().__init__(parent=parent, label=text)
        self.Bind(wx.EVT_RADIOBUTTON, lambda _: cbk(value))
        self.Bind(wx.EVT_SIZE, lambda _: self.Update())


class PreScaleCheckBox(wx.CheckBox):
    def __init__(self, parent):
        super().__init__(parent=parent, label="预缩放")
        self.api = get_api(self)
        self.Bind(wx.EVT_CHECKBOX, self.OnSwitch)
        self.SetValue(True)

    def OnSwitch(self, _):
        enable = self.GetValue()
        self.api.set_pre_scale(enable)


class ScreenFormatSetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.SetFont(ft(13))
        self.text = wx.StaticText(self, label="屏幕格式:")
        self.jpg_button = FormatRadioButton(self, "JPG", ScreenFormat.JPEG, self.set_format)
        self.png_button = FormatRadioButton(self, "PNG", ScreenFormat.PNG, self.set_format)
        self.raw_button = FormatRadioButton(self, "Raw", ScreenFormat.RAW, self.set_format)
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
        self.api = get_api(self)

        BToolTip(self.text, "在屏幕的网络传输中使用的格式", ft(10))
        BToolTip(self.pre_scale_box, "占用更少带宽", ft(10))
        BToolTip(self.jpg_button, "带宽: 小, 质量: 高, 性能: 快", ft(10))
        BToolTip(self.png_button, "带宽: 中, 质量: 无损, 性能: 慢", ft(10))
        BToolTip(self.raw_button, "带宽: 大, 质量: 无损, 性能: 快", ft(10))

        self.format_lock = Lock()
        self.Update()

    def set_format(self, value: str):
        controller: ScreenController = self.api.client.screen_tab.screen_panel.controller
        if value != ScreenFormat.JPEG:
            controller.sizer.Hide(controller.screen_quality_setter)
        else:
            controller.sizer.Show(controller.screen_quality_setter)
        start_and_return(self._set_format, (value,))

    def _set_format(self, value: str):
        with self.format_lock:
            packet = {"type": SET_SCREEN_FORMAT, "format": value}
            if self.api.connected:
                self.api.send_packet(packet)


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
        self.input_slider.cbk = get_api(self).set_screen_fps
        self.SetSizer(self.sizer)
        self.Update()


class ScreenQualitySetter(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 31))

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.StaticText(self, label="屏幕质量:")
        self.input_slider = InputSlider(self, value=80, _min=1, _max=100, _from=0, to=100)

        self.sizer.AddSpacer(10)
        self.sizer.Add(self.text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(15)
        self.sizer.Add(self.input_slider, flag=wx.ALIGN_LEFT | wx.EXPAND)

        BToolTip(self.text, "屏幕传输的质量\n质量越高, 带宽占用越大", ft(10))
        self.text.SetFont(ft(14))
        self.input_slider.cbk = get_api(self).set_screen_quality
        self.SetSizer(self.sizer)


class ScreenInformationShower(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1500, 32))

        self.SetFont(ft(14))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.FPS_text = wx.StaticText(self, label="FPS: 0")
        self.network_text = wx.StaticText(self, label="占用带宽: 0 KB/s")
        self.delay_text = wx.StaticText(self, label="延迟: 0 ms")
        self.sizer.AddSpacer(10)
        self.sizer.Add(self.FPS_text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(100)
        self.sizer.Add(self.network_text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)
        self.sizer.AddSpacer(100)
        self.sizer.Add(self.delay_text, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=3)

        BToolTip(self.FPS_text, "反映了屏幕传输的流畅度", ft(10))
        BToolTip(self.network_text, "屏幕传输占用的带宽", ft(10))
        BToolTip(self.delay_text, "客户端到服务器的延迟", ft(10))
        self.SetSizer(self.sizer)

        self.fps_avg = []
        self.network_avg = []
        self.collect_inv = 0.5
        self.api = get_api(self)
        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_data, self.update_timer)
        self.update_timer.Start(int(self.collect_inv * 1000))
        self.delay_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.req_update_data, self.delay_timer)
        self.delay_timer.Start(1000)

    def update_data(self, event: wx.TimerEvent = None):
        self.update_fps()
        self.update_network()
        if event:
            event.Skip()

    def req_update_data(self, event: wx.TimerEvent = None):
        self.api.send_packet({"type": PING, "timer": perf_counter()}, priority=Priority.HIGHEST)
        event.Skip()

    def update_fps(self):
        self.fps_avg.append(self.api.screen_counter / self.collect_inv)
        self.api.screen_counter = 0
        if len(self.fps_avg) > 10:
            self.fps_avg.pop(0)
        self.FPS_text.SetLabel("FPS: " + str(round(sum(self.fps_avg) / len(self.fps_avg), 1)))

    def update_network(self):
        self.network_avg.append(self.api.screen_network_counter / self.collect_inv)
        self.api.screen_network_counter = 0
        if len(self.network_avg) > 10:
            self.network_avg.pop(0)
        self.network_text.SetLabel(
            "占用带宽: " + format_size(sum(self.network_avg) / len(self.network_avg)) + " /s"
        )

    def update_delay(self, delay: int):
        self.delay_text.SetLabel(f"延迟: {round(delay*1000, 2)} ms")


class ScreenController(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1270, 160))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.control_setter = ComputerControlSetter(self)
        self.screen_format_setter = ScreenFormatSetter(self)
        self.screen_fps_setter = ScreenFPSSetter(self)
        self.screen_quality_setter = ScreenQualitySetter(self)
        self.info_shower = ScreenInformationShower(self)
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
        self.sizer.Add(self.info_shower, flag=wx.ALIGN_TOP | wx.EXPAND)
        # self.sizer.Layout()
        self.SetSizer(self.sizer)


class ScreenPanel(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(960, 1112))
        self.screen_shower = ScreenShower(self, (int(1920 / 2), int(1080 / 2)))
        self.controller = ScreenController(self)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.screen_shower, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=1)
        self.sizer.Add(self.controller, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=0)
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
