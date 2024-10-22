import wx
from gui.widgets import *
from libs.api import get_api

MAX_HISTORY_LENGTH = 100000


class TerminalText(wx.TextCtrl):
    def __init__(self, parent):
        wx.TextCtrl.__init__(
            self,
            parent=parent,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_CHARWRAP,
            size=(1226, 700),
        )
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_menu)
        self.api = get_api(self)
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
        self.api.send_command("")
        self.Clear()
        event.Skip()

    def restore_shell(self, _):
        self.Clear()
        self.api.restore_shell()


class TerminalInput(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 32))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.TextCtrl(self, size=(1200, 28), style=wx.TE_PROCESS_ENTER)
        self.send_button = wx.Button(self, label="发送", size=(75, 31))
        self.sizer.Add(self.text, flag=wx.ALIGN_TOP | wx.EXPAND | wx.TOP, border=1, proportion=1)
        self.sizer.AddSpacer(3)
        self.sizer.Add(self.send_button, flag=wx.ALIGN_TOP, proportion=0)
        self.sizer.AddSpacer(2)
        self.SetSizer(self.sizer)

        self.tip_text = "请输入命令"
        self.on_tip = False
        self.has_focus = False
        self.normal_color = self.GetForegroundColour()
        self.gray_color = wx.Colour((76, 76, 76))
        self.api = get_api(self)
        self.text.Bind(wx.EVT_SET_FOCUS, self.on_focus)
        self.text.Bind(wx.EVT_KILL_FOCUS, self.on_focus_out)
        self.text.Bind(wx.EVT_KEY_DOWN, self.on_enter)
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
        if event.GetKeyCode() == wx.WXK_NUMPAD_ENTER or event.GetKeyCode() == wx.WXK_RETURN:
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
        self.api.send_command(self.text.GetValue())
        self.text.Clear()


class TerminalTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.cmd_text = TerminalText(self)
        self.inputter = TerminalInput(self)
        self.sizer.Add(self.cmd_text, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=1)
        self.sizer.AddSpacer(3)
        self.sizer.Add(self.inputter, flag=wx.ALIGN_TOP | wx.EXPAND, proportion=0)
        self.SetSizer(self.sizer)
