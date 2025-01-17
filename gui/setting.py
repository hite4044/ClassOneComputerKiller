import wx
from gui.widgets import *
from libs.config import *
from libs.api import get_api


class ServerConfigurator(Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.api = get_api(self)
        
        self.sizer = wx.StaticBoxSizer(wx.VERTICAL, self, label="服务端配置")
        self.SetSizer(self.sizer)
        self.SetMaxSize(MAX_SIZE)


class ClientConfigurator(Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.api = get_api(self)

        self.sizer = wx.StaticBoxSizer(wx.VERTICAL, self, label="客户端配置")
        self.config_grid = wx.ListCtrl(self, style=wx.LC_REPORT)
        self.config_grid.InsertColumn(0, "名称")
        self.config_grid.InsertColumn(1, "值")
        self.config_grid.InsertColumn(2, "描述")
        self.config_grid.SetColumnWidth(0, 100)
        self.config_grid.SetColumnWidth(1, 100)
        self.config_grid.SetColumnWidth(2, 300)
        self.sizer.Add(self.config_grid, flag=wx.EXPAND)
        self.SetSizer(self.sizer)
        self.SetMaxSize(MAX_SIZE)
    
    def parse_result(self, packet: Packet):
        self.config_grid.DeleteAllItems()
        


class SettingTab(Panel):
    def __init__(self, parent):
        super().__init__(parent, size=MAX_SIZE)
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE, size=MAX_SIZE)
        self.server_config = ServerConfigurator(self.splitter)
        self.client_config = ClientConfigurator(self.splitter)
        self.splitter.SplitVertically(self.server_config, self.client_config)
        self.splitter.SetSashGravity(0.5)
        self.sizer.Add(self.splitter, flag=wx.EXPAND)
        self.SetSizer(self.sizer)
