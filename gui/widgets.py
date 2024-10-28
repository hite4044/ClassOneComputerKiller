import wx
from time import sleep
from libs.packets import *
from threading import Lock
from os.path import abspath
from typing import Callable
from win32gui import GetCursorPos
from win32api import GetSystemMetrics

font: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
font.SetPointSize(11)

MAX_SIZE = (GetSystemMetrics(0), GetSystemMetrics(1))

font_cache = {}


def ft(size: float, weight: int = 500) -> wx.Font:
    global font_cache
    if font_cache.get((size, weight)):
        return font_cache.get((size, weight))
    _ft: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    _ft.SetPointSize(size)
    if weight != 500:
        _ft.SetWeight(weight)
    font_cache[(size, weight)] = _ft
    return _ft


def get_window(widget: wx.Window) -> wx.Frame:
    while True:
        widget: wx.Window = widget.GetParent()
        if isinstance(widget, wx.Frame):
            return widget


def format_size(size_in_bytes) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size_in_bytes >= 1024 and index < len(units) - 1:
        size_in_bytes /= 1024
        index += 1
    return f"{size_in_bytes:.2f} {units[index]}"


class Panel(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        pos: tuple[int, int] | list[int] = (0, 0),
        size: tuple[int, int] | list[int] = (16, 16),
    ):
        pos = tuple(pos)
        size = tuple(size)
        super().__init__(parent=parent, pos=pos, size=size)
        # import random
        # self.SetBackgroundColour(wx.Colour(*(random.randint(0, 255) for _ in range(3))))


class LabelEntry(Panel):
    def __init__(self, parent, label: str):
        super().__init__(parent, size=(130, 27))
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.label_ctl = wx.StaticText(self, label=label)
        self.text = wx.TextCtrl(self, size=(100, 27))
        self.label_ctl.SetFont(font)
        sizer.Add(self.label_ctl, flag=wx.ALIGN_CENTER_VERTICAL, proportion=0)
        sizer.AddSpacer(6)
        sizer.Add(self.text, wx.EXPAND)
        self.SetSizer(sizer)


class LabelCombobox(Panel):
    def __init__(self, parent, label: str, choices: list[tuple[str, Any]] = []):
        super().__init__(parent, size=(130, 27))
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.label_ctl = wx.StaticText(self, label=label)
        self.combobox = wx.ComboBox(
            self, choices=[name for name, _ in choices], size=(100, 27), style=wx.CB_READONLY
        )
        self.label_ctl.SetFont(font)
        sizer.Add(self.label_ctl, flag=wx.ALIGN_CENTER_VERTICAL, proportion=0)
        sizer.AddSpacer(6)
        sizer.Add(self.combobox, wx.EXPAND)
        self.SetSizer(sizer)

        self.datas = choices

    def set_choices(self, choices: list[tuple[str, Any]]):
        self.combobox.Clear()
        self.combobox.AppendItems([name for name, _ in choices])
        self.datas = choices

    def add_choice(self, name: str, data: Any):
        self.combobox.Append(name)
        self.datas.append((name, data))

    def get_data(self) -> Any | None:
        select = self.combobox.GetValue()
        for name, data in self.datas:
            if name == select:
                return data
        return None


class AddableList(Panel):
    def __init__(
        self, parent, label: str, ready_data: list[tuple[str, Any]] = [], ch_title: str = "选择"
    ):
        super().__init__(parent, size=(200, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_button = wx.BitmapButton(
            self, bitmap=wx.Bitmap(abspath("assets/add.png"), wx.BITMAP_TYPE_PNG)
        )
        self.add_button.Bind(wx.EVT_BUTTON, lambda _: self.on_add())
        self.label_ctl = wx.StaticText(self, label=label)
        self.label_ctl.SetFont(ft(13))
        self.listbox = wx.ListBox(self, size=(200, 85))
        self.listbox.SetFont(font)

        top_sizer.Add(self.label_ctl, wx.EXPAND | wx.TOP, border=5)
        top_sizer.Add(self.add_button, proportion=0)
        sizer.Add(top_sizer, flag=wx.ALL | wx.EXPAND, border=3, proportion=0)
        sizer.Add(self.listbox, flag=wx.EXPAND, proportion=1)
        self.SetSizer(sizer)
        self.listbox.Bind(wx.EVT_RIGHT_DOWN, self.on_empty_menu)
        self.listbox.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.on_item_menu)

        self.ch_title = ch_title
        self.ready_data = ready_data
        self.datas: dict[int, tuple[str, Any]] = {}

    def add_item(self, name: str, data: Any, index: int = -1):
        if index == -1:
            index = self.listbox.GetCount()
        self.listbox.Insert(name, index)
        self.datas[index] = (name, data)

    def on_empty_menu(self, event: wx.MouseEvent):
        menu = wx.Menu()
        menu.Append(1, "添加")
        menu.Bind(wx.EVT_MENU, lambda _: self.on_add(), id=1)
        self.PopupMenu(menu)
        event.Skip()

    def on_item_menu(self, event: wx.ListEvent):
        menu = wx.Menu()
        menu.Append(1, "添加")
        menu.Append(2, "修改")
        menu.Append(3, "删除")
        index = event.GetIndex()
        menu.Bind(wx.EVT_MENU, lambda _: self.on_add(), id=1)
        menu.Bind(wx.EVT_MENU, lambda _: self.on_modify(index), id=2)
        menu.Bind(wx.EVT_MENU, lambda _: self.on_delete(index), id=3)
        self.PopupMenu(menu)

    def on_add(self):
        ItemChoiceDialog(self, self.ch_title, self.ready_data, self.add_item)

    def on_modify(self, index: int):
        pass

    def on_delete(self, index: int):
        self.listbox.Delete(index)

    def get_items(self) -> list[Any]:
        return [data for _, data in self.datas.values()]


class ItemChoiceDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        title: str,
        choices: list[tuple[str, Any]],
        callback: Callable[[str, Any], None],
    ):
        super().__init__(get_window(parent), title=title, size=(200, 250))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.listbox = wx.ListBox(self, size=MAX_SIZE)
        self.bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.empty = wx.Window(self)
        self.ok_btn = wx.Button(self, label="确定")
        self.cancel_btn = wx.Button(self, label="取消")

        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, lambda _: self.Close())
        self.listbox.SetFont(ft(12))
        self.ok_btn.SetFont(ft(12))
        self.cancel_btn.SetFont(ft(12))

        self.sizer.Add(self.listbox, wx.EXPAND)
        self.bottom_sizer.Add(self.empty, flag=wx.EXPAND)
        self.bottom_sizer.Add(self.ok_btn, proportion=0)
        self.bottom_sizer.AddSpacer(6)
        self.bottom_sizer.Add(self.cancel_btn, proportion=0)
        self.sizer.Add(self.bottom_sizer, flag=wx.EXPAND | wx.ALL, proportion=0, border=6)
        self.SetSizer(self.sizer)
        self.SetIcon(wx.Icon(abspath("assets/select.ico"), wx.BITMAP_TYPE_ICO))
        for name, _ in choices:
            self.listbox.Append(name)

        self.cbk = callback
        self.choices = choices
        self.ShowModal()

    def on_ok(self, _):
        select = self.listbox.GetSelection()
        if select != wx.NOT_FOUND:
            self.cbk(*self.choices[select])
        self.Close()


class InputSlider(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        _from: int = 0,
        to: int = 100,
        _min: int = 0,
        _max: int = 100,
        value: int = 50,
        cbk: Callable = lambda _: None,
    ):
        super().__init__(parent=parent, size=(1500, 31))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.slider = wx.Slider(self, value=value, minValue=_from, maxValue=to, size=(790, 31))
        self.inputter = wx.TextCtrl(self, value=str(value), size=(60, 31))
        self.sizer.AddSpacer(5)
        self.sizer.Add(self.slider, flag=wx.ALIGN_LEFT | wx.EXPAND | wx.TOP, border=4, proportion=1)
        self.sizer.AddSpacer(5)
        self.sizer.Add(self.inputter, flag=wx.ALIGN_LEFT | wx.TOP, border=3, proportion=0)

        self.slider.Bind(wx.EVT_SLIDER, self.on_slider)
        self.inputter.Bind(wx.EVT_TEXT, self.on_edit)
        self.inputter.Bind(wx.EVT_CHAR_HOOK, self.on_enter)
        self.inputter.Bind(wx.EVT_KILL_FOCUS, self.on_focus_out)

        self.value = value
        self.min = _min
        self.max = _max
        self.cbk = cbk
        self.SetSizer(self.sizer)

    def parse_value(self):
        value = self.inputter.GetValue()
        try:
            value = int(value)
        except ValueError:
            value = self.min
        if value > self.max:
            value = self.max
        elif value < self.min:
            value = self.min
        self.slider.SetValue(value)
        self.value = value + 1 - 1

    def on_slider(self, event: wx.ScrollEvent):
        value = self.slider.GetValue()
        if value > self.max:
            value = self.max
            self.slider.SetValue(value)
        elif value < self.min:
            value = self.min
            self.slider.SetValue(value)
        self.inputter.SetValue(str(value))
        self.value = value + 1 - 1
        self.cbk(self.value)
        event.Skip()

    def on_edit(self, event: wx.Event):
        self.parse_value()
        event.Skip()

    def on_enter(self, event: wx.KeyEvent):
        self.SetFocus()
        if event.GetKeyCode() == wx.WXK_RETURN or event.GetKeyCode() == wx.WXK_NUMPAD_ENTER:
            self.on_focus_out()
        event.Skip()

    def on_focus_out(self, event: wx.Event = None):
        self.parse_value()
        self.inputter.SetValue(str(self.value))
        self.cbk(self.value)
        if event:
            event.Skip()

    def get_value(self):
        return self.value


class BToolTip:
    def __init__(self, parent: wx.Window, text: str, _font=None):
        """Big & Better TipTool"""
        self.parent = parent
        self.text = text
        self.font: wx.Font = _font
        self.delay = 0.5
        self.client = get_window(parent)
        self.in_timer = True
        self.tooltip = None
        self.tooltip_lock = Lock()
        parent.Bind(wx.EVT_MOUSE_EVENTS, self.mouse_event)

    def timer_thread(self):
        sleep(self.delay)
        if self.client.connected:
            wx.CallAfter(self.show_tooltip)

    def show_tooltip(self):
        if not self.in_timer:
            return
        with self.tooltip_lock:
            if self.tooltip:
                return
            dc = wx.ScreenDC()
            if self.font:
                dc.SetFont(self.font)
            if "\n" in self.text:
                mx_len = 0
                size = (0, 0)
                for line in self.text.split("\n"):
                    size = dc.GetTextExtent(line)
                    if size[0] > mx_len:
                        mx_len = size[0]
                size = list(size)
                size[0] = mx_len
            else:
                size = dc.GetTextExtent(self.text)

            tooltip = wx.TipWindow(get_window(self.parent), self.text, size[0] + 10)
            text: wx.StaticText = tooltip.GetChildren()[0]

            tooltip.SetSize(0, 0, size[0] + 6, tooltip.GetSize()[1])
            text.SetSize(0, 0, size[0] + 6, text.GetSize()[1])
            text.SetBackgroundColour(wx.Colour((249, 249, 249)))
            text.SetForegroundColour(wx.Colour((87, 87, 87)))
            if self.font:
                text.SetFont(self.font)
            pos = list(GetCursorPos())
            pos[1] += 31
            tooltip.SetPosition(pos)
            self.tooltip = tooltip

    def mouse_event(self, event: wx.MouseEvent):
        if event.Entering():
            self.in_timer = True
            start_and_return(self.timer_thread)
        elif event.Moving() and self.tooltip:
            pos = list(GetCursorPos())
            pos[1] += 31
            self.tooltip.SetPosition(pos)
        elif event.Leaving():
            self.in_timer = False
            with self.tooltip_lock:
                try:
                    self.tooltip.Destroy()
                except AttributeError:
                    pass
                except RuntimeError:
                    pass
            self.tooltip = None
        event.Skip()
