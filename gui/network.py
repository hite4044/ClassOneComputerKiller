import wx
from gui.widgets import *


class NetworkTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.StaticText(self, label="byd不想做, 感觉没用")
        self.sizer.Add(self.text)
        self.SetSizer(self.sizer)

        self.text.SetFont(ft(90))
