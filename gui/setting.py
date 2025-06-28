import wx
import platform
from gui.widgets import *
from libs.config import *
from libs.api import get_api

class ClientConfigurator(Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.api = get_api(self)
        
        self.sizer = wx.StaticBoxSizer(wx.VERTICAL, self, label="客户端配置")
        
        # 使用FlexGridSizer显示系统信息
        grid = wx.FlexGridSizer(cols=2, vgap=5, hgap=15)
        grid.AddGrowableCol(1, 1)
        
        # 添加系统信息标签
        labels = [
            ("操作系统:", "os"),
            ("系统架构:", "arch"),
            ("处理器:", "cpu"),
            ("物理核心:", "cores"),
            ("逻辑核心:", "threads"),
            ("内存:", "ram")
        ]
        
        self.info_labels = {}
        for label, key in labels:
            grid.Add(wx.StaticText(self, label=label), 
                    flag=wx.ALIGN_CENTER_VERTICAL)
            value_label = wx.StaticText(self, label="加载中...")
            self.info_labels[key] = value_label
            grid.Add(value_label, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        
        self.sizer.Add(grid, flag=wx.EXPAND | wx.ALL, border=15)
        self.SetSizer(self.sizer)
        self.SetMaxSize(MAX_SIZE)
    
    def update_system_info(self, system_info: dict):
        """更新系统信息显示"""
        for key, label in self.info_labels.items():
            if key in system_info:
                label.SetLabel(str(system_info[key]))


class SettingTab(Panel):
    def __init__(self, parent):
        super().__init__(parent, size=MAX_SIZE)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 只显示客户端配置（删除服务端配置）
        self.client_config = ClientConfigurator(self)
        self.sizer.Add(self.client_config, flag=wx.EXPAND | wx.ALL, border=10)
        
        self.SetSizer(self.sizer)
