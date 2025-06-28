import wx
from wx import grid
from gui.widgets import *
from libs.action import *
from libs.api import get_api, get_window_name
from libs.packets import Any


class ActionEditDialog(wx.Frame):
    """动作编辑对话框，用于创建或编辑动作"""
    def __init__(
        self,
        parent: wx.Window,  # 父窗口
        title: str,  # 对话框标题
        callback: Callable[[TheAction], None],  # 回调函数，用于处理完成的动作
        action_init: TheAction = None,  # 初始化的动作(编辑时传入)
    ):
        super().__init__(get_window_name(parent, "Client"), title=title, size=(420, 390))
        self.callback = callback  # 保存回调函数

        # 界面布局
        self.SetFont(ft(12))  # 设置字体
        self.sizer = wx.BoxSizer(wx.VERTICAL)  # 主布局管理器(垂直)
        self.name_inputter = LabelEntry(self, "名称: ")  # 名称输入框
        self.prq_sizer = wx.BoxSizer(wx.HORIZONTAL)  # 条件布局管理器(水平)
        self.start_prqs = StartPrqList(self)  # 开始条件列表
        self.end_prqs = EndPrqList(self)  # 结束条件列表
        self.actions_chooser = LabelCombobox(self, "动作: ")  # 动作选择下拉框
        self.bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)  # 底部按钮布局
        self.ok_btn = wx.Button(self, label="确定")  # 确定按钮
        self.cancel_btn = wx.Button(self, label="取消")  # 取消按钮

        # 初始化动作选择下拉框
        for _, action_type in actions_map.items():
            self.actions_chooser.add_choice(action_type.ch_name(), action_type)
        
        # 绑定事件
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        
        # 设置字体
        self.name_inputter.label_ctl.SetFont(ft(13))
        self.actions_chooser.label_ctl.SetFont(ft(13))

        # 添加控件到布局
        self.sizer.Add(self.name_inputter, flag=wx.EXPAND, proportion=0)
        self.sizer.AddSpacer(6)  # 添加间距
        self.prq_sizer.Add(self.start_prqs, flag=wx.EXPAND, proportion=50)
        self.prq_sizer.AddSpacer(6)
        self.prq_sizer.Add(self.end_prqs, flag=wx.EXPAND, proportion=50)
        self.sizer.Add(self.prq_sizer, flag=wx.EXPAND, proportion=1)
        self.sizer.AddSpacer(6)
        self.sizer.Add(self.actions_chooser, flag=wx.EXPAND, proportion=0)
        self.sizer.AddSpacer(12)
        self.bottom_sizer.Add(self.ok_btn, proportion=0)
        self.bottom_sizer.AddSpacer(6)
        self.bottom_sizer.Add(self.cancel_btn, proportion=0)
        self.sizer.Add(self.bottom_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=6)
        
        # 设置布局和图标
        self.SetSizer(self.sizer)
        self.SetIcon(wx.Icon(abspath(r"assets\action_editor.ico")))
        self.Show()

    def on_ok(self, _):
        """确定按钮点击事件处理"""
        msg = self.callback_action()
        if msg:  # 如果有错误消息
            MessageBox(self.Handle, msg, "错误", wx.OK | wx.ICON_ERROR)
        else:
            self.Close()

    def callback_action(self) -> None | str:
        """处理动作回调，返回错误消息或None"""
        name = self.name_inputter.text.GetValue()  # 获取动作名称

        # 获取开始和结束条件
        start_prqs = self.start_prqs.get_items()
        end_prqs = self.end_prqs.get_items()
        if start_prqs == []:  # 检查开始条件
            return "请选择至少一个开始条件"
        if end_prqs == []:  # 如果没有结束条件，添加默认条件
            end_prqs.append(NoneEndPrq())

        # 获取动作类型
        action_type: AnAction = self.actions_chooser.get_data()
        if action_type is None:
            return "请选择要执行的操作"
        
        # 如果动作需要参数，弹出参数输入对话框
        if action_type.params:
            DataInputDialog(
                self,
                "输入动作参数",
                action_type.params,
                lambda datas: self.action_params_cbk(datas, (name, start_prqs, end_prqs, action_type)),
            )
        else:
            self.action_params_cbk({}, (name, start_prqs, end_prqs, action_type))
        return None

    def action_params_cbk(
        self, datas: dict[str, Any], flash: tuple[str, list[StartPrq], list[EndPrq], AnAction]
    ):
        """动作参数回调函数"""
        action: AnAction = flash[3](**datas)  # 创建动作实例
        self.callback(TheAction(flash[0], 1, [action], flash[1], flash[2]))  # 调用回调

    def on_cancel(self, _):
        """取消按钮点击事件处理"""
        self.Close()


class DataInputter(wx.Panel):
    """数据输入控件，用于输入不同类型的参数"""
    def __init__(self, parent, param: ActionParam) -> None:
        super().__init__(parent)
        self.SetWindowStyle(wx.MINIMIZE_BOX)
        self.param = param  # 保存参数定义
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)  # 水平布局
        self.label = wx.StaticText(self, label=param.label)  # 参数标签
        self.label.SetFont(ft(13))
        self.sizer.Add(self.label, proportion=0)
        self.sizer.AddSpacer(6)
        self.normal_color = None  # 保存正常背景色
        
        # 根据参数类型创建不同的输入控件
        if param.type in [ParamType.FLOAT, ParamType.INT, ParamType.STRING]:
            self.inputter = wx.TextCtrl(self)  # 文本输入框
            self.normal_color = self.inputter.GetBackgroundColour()
            self.inputter.SetValue(str(param.default))  # 设置默认值
        elif param.type == ParamType.BOOL:
            self.inputter = wx.CheckBox(self)  # 复选框
            self.inputter.SetValue(param.default)
        elif param.type == ParamType.CHOICE:
            assert isinstance(param, ChoiceParam)
            self.inputter = wx.ComboBox(self, style=wx.CB_READONLY)  # 下拉框
            self.inputter.SetItems([name for name, _ in param.choices.items()])
            self.inputter.SetValue(param.default)
        self.inputter.SetFont(ft(13))

        self.sizer.Add(self.inputter, flag=wx.EXPAND, proportion=1)
        self.SetSizer(self.sizer)

    def valid(self):
        """验证输入是否有效"""
        return self.param.valid(self.inputter.GetValue())

    def get_data(self):
        """获取输入的数据"""
        if self.valid() is None:  # 如果验证通过
            return self.param.parse_string(self.inputter.GetValue())  # 解析输入值
        else:
            return None


class DataInputDialog(wx.Dialog):
    """数据输入对话框，用于输入多个参数"""
    def __init__(
        self,
        parent: wx.Window,
        title: str,
        params: dict[str, ActionParam],  # 参数字典，key为参数名，value为参数定义
        callback: Callable[[dict[str, Any]], None],  # 回调函数
    ):
        super().__init__(get_window(parent), title=title, size=(420, 390))
        self.SetFont(font)
        self.callback = callback  # 保存回调函数
        self.params = params  # 保存参数定义

        # 界面布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.inputter_container = wx.ScrolledWindow(self)  # 可滚动的输入控件容器
        self.ok_btn = wx.Button(self, label="确定")
        self.cancel_btn = wx.Button(self, label="取消")
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, lambda _: self.Close())
        bottom_bar = wx.BoxSizer(wx.HORIZONTAL)

        # 创建输入控件
        container_sizer = wx.BoxSizer(wx.VERTICAL)
        self.inputters: dict[str, DataInputter] = {}  # 保存所有输入控件
        for name, param in params.items():
            inputter = DataInputter(self.inputter_container, param)
            self.inputters[name] = inputter
            container_sizer.Add(inputter, flag=wx.EXPAND, proportion=0)
            container_sizer.AddSpacer(6)
        self.inputter_container.SetSizer(container_sizer)

        # 添加控件到布局
        sizer.Add(self.inputter_container, flag=wx.EXPAND, proportion=1)
        sizer.AddSpacer(6)
        bottom_bar.Add(self.ok_btn, proportion=0)
        bottom_bar.AddSpacer(6)
        bottom_bar.Add(self.cancel_btn, proportion=0)
        sizer.Add(bottom_bar, flag=wx.ALIGN_RIGHT | wx.ALL, border=6)
        self.SetSizer(sizer)
        self.ShowModal()  # 模态显示对话框

    def on_ok(self, _):
        """确定按钮点击事件处理"""
        data = {}
        for name, inputter in self.inputters.items():
            data[name] = inputter.get_data()  # 收集所有输入数据
            
        if None in data.values():  # 如果有无效输入
            print(data)
            wx.MessageBox("请检查输入", "错误", wx.OK | wx.ICON_ERROR)
        else:
            self.callback(data)  # 调用回调函数
            self.Close()


class ActionGrid(grid.Grid):
    """动作表格，显示所有动作"""
    def __init__(self, parent: "ActionEditor"):
        super().__init__(parent, size=MAX_SIZE)
        self.action_editor: ActionEditor = parent  # 保存父窗口引用
        self.CreateGrid(1, 4)  # 创建4列的表格
        
        # 表格列定义
        gui_data = [
            ("名称", 100),  # 列名和宽度
            ("触发条件", 300),
            ("执行操作", 180),
            ("停止条件", 300),
        ]

        # 初始化表格列
        for i in range(len(gui_data)):
            name, width = gui_data[i]
            self.SetColLabelValue(i, name)  # 设置列名
            self.SetColSize(i, width)  # 设置列宽
            
        self.datas: list[TheAction] = []  # 保存动作数据
        self.first_add = True  # 是否是第一次添加动作
        self.api = get_api(self)  # 获取API
        self.SetDefaultCellAlignment(wx.ALIGN_CENTER, wx.ALIGN_CENTER)  # 设置单元格对齐方式

        # 表格样式设置
        self.SetRowLabelSize(1)  # 隐藏行号
        self.EnableEditing(False)  # 禁用编辑
        self.SetLabelFont(font)  # 设置标签字体
        self.SetDefaultCellFont(font)  # 设置单元格字体
        self.Bind(grid.EVT_GRID_CELL_RIGHT_CLICK, self.on_row_menu)  # 绑定右键菜单事件

    def on_row_menu(self, event: grid.GridEvent):
        """行右键菜单事件处理"""
        row = event.GetRow()
        menu = wx.Menu()
        menu.Append(1, "新建")
        menu.Append(2, "编辑")
        menu.Bind(wx.EVT_MENU, self.action_editor.on_add_action, id=1)
        menu.Bind(wx.EVT_MENU, lambda: self.on_edit(row), id=2)
        self.PopupMenu(menu)

    def on_empty_menu(self, event: wx.MenuEvent):
        """空白处右键菜单事件处理"""
        menu = wx.Menu()
        menu.Append(1, "新建")
        menu.Bind(wx.EVT_MENU, self.action_editor.on_add_action, id=1)
        self.PopupMenu(menu)

    def on_edit(self, row: int):
        """编辑动作"""
        action = self.datas[row]
        ActionEditDialog(self, action)

    def add_action(self, the_action: TheAction) -> TheAction:
        """添加动作到表格"""
        if self.first_add:  # 如果是第一次添加
            self.first_add = False
            row = 0
        else:
            self.AppendRows(1)  # 添加新行
            row = self.GetNumberRows() - 1

        # 设置单元格值
        self.SetCellValue(row, 0, the_action.name)
        self.SetCellValue(row, 1, " ".join([start.name() for start in the_action.start_prqs]))
        self.SetCellValue(row, 2, " ".join([action.name() for action in the_action.actions]))
        self.SetCellValue(row, 3, " ".join([end.name() for end in the_action.end_prqs]))
        self.datas.append(the_action)  # 保存动作数据
        return the_action


class StartPrqList(AddableList):
    """开始条件列表"""
    def __init__(self, parent):
        data = [(prq.ch_name(), prq) for prq in start_prqs_map.values()]  # 获取所有开始条件
        super().__init__(parent, "开始条件", data, "添加开始条件")

    def add_item(self, name: str, _type: StartPrq, index: int = -1):
        """添加条件项(异步)"""
        wx.CallAfter(self.request_data, _type)

    def request_data(self, _type: StartPrq):
        """请求条件参数"""
        if _type.params:  # 如果条件需要参数
            DataInputDialog(self, "输入条件参数", _type.params, lambda ps: self.add_prq(ps, _type))
        else:
            self.add_prq({}, _type)

    def add_prq(self, params: dict[str, Any], _type: StartPrq):
        """添加带参数的条件"""
        prq: StartPrq = _type(**params)  # 创建条件实例
        super().add_item(prq.name(), prq)  # 添加到列表


class EndPrqList(AddableList):
    """结束条件列表"""
    def __init__(self, parent):
        data = [(prq.ch_name(), prq) for prq in end_prqs_map.values()]  # 获取所有结束条件
        super().__init__(parent, "结束条件", data, "添加结束条件")

    def add_item(self, name: str, _type: EndPrq, index: int = -1):
        """添加条件项(异步)"""
        wx.CallAfter(self.request_data, _type)

    def request_data(self, _type: EndPrq):
        """请求条件参数"""
        if _type.params:  # 如果条件需要参数
            DataInputDialog(self, "输入条件参数", _type.params, lambda ps: self.add_prq(ps, _type))
        else:
            self.add_prq({}, _type)

    def add_prq(self, params: dict[str, Any], _type: EndPrq):
        """添加带参数的条件"""
        prq: EndPrq = _type(**params)  # 创建条件实例
        super().add_item(prq.name(), prq)  # 添加到列表


class ActionEditor(Panel):
    """动作编辑器主面板"""
    def __init__(self, parent: wx.Window):
        super().__init__(parent, size=MAX_SIZE)
        self.sizer = wx.BoxSizer(wx.VERTICAL)  # 主布局
        self.grid = ActionGrid(self)  # 动作表格
        self.api = get_api(self)  # 获取API

        # 按钮栏
        self.bar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(self, label="添加操作")
        self.remove_btn = wx.Button(self, label="删除操作")
        self.add_btn.Bind(wx.EVT_BUTTON, self.on_add_action)
        self.grid.SetWindowStyle(wx.SIMPLE_BORDER)
        self.bar_sizer.Add(self.add_btn)
        self.bar_sizer.AddSpacer(6)
        self.bar_sizer.Add(self.remove_btn)

        # 添加控件到布局
        self.sizer.Add(
            self.bar_sizer,
            flag=wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT,
            border=6,
        )
        self.sizer.Add(self.grid, flag=wx.EXPAND | wx.ALL, border=6)
        self.SetSizer(self.sizer)

    def on_add_action(self, _=None):
        """添加动作按钮点击事件"""
        ActionEditDialog(self, "增加操作", self.add_action, None)

    def add_action(self, the_action: TheAction):
        """添加动作到表格并发送到服务器"""
        self.grid.add_action(the_action)  # 添加到表格
        packet = {"type": ACTION_ADD, **the_action.build_packet()}  # 构建数据包
        self.api.send_packet(packet)  # 发送到服务器


class ActionList(Panel):
    """动作列表面板"""
    def __init__(self, parent):
        super().__init__(parent=parent, size=(250, 703))
        self.sizer = wx.BoxSizer(wx.VERTICAL)  # 主布局管理器(垂直)
        self.top_sizer = wx.BoxSizer(wx.HORIZONTAL)  # 顶部布局管理器(水平)
        self.sizer = wx.BoxSizer(wx.VERTICAL)  # 主布局管理器(垂直)
        self.top_sizer = wx.BoxSizer(wx.HORIZONTAL)  # 顶部标题栏布局(水平)

        # 创建控件
        self.text = wx.StaticText(self, label="操作列表", style=wx.ALIGN_LEFT)  # 标题文本
        bmp = wx.Bitmap()  # 添加按钮图标
        bmp.LoadFile(abspath(r"assets\add.png"), wx.BITMAP_TYPE_PNG)
        self.add_btn = wx.BitmapButton(self, bitmap=bmp)  # 添加按钮(带图标)
        self.listbox = wx.ListBox(self, style=wx.LB_SINGLE)  # 动作列表框(单选)
        self.text.SetFont(ft(13))  # 设置标题字体

        # 添加控件到顶部布局
        self.top_sizer.Add(self.text, flag=wx.EXPAND | wx.TOP | wx.LEFT, proportion=1, border=4)
        self.top_sizer.Add(self.add_btn, flag=wx.TOP | wx.RIGHT, proportion=0, border=4)
        
        # 添加控件到主布局
        self.sizer.Add(
            self.top_sizer,
            flag=wx.ALIGN_TOP | wx.EXPAND | wx.LEFT | wx.RIGHT,
            proportion=0,
            border=3,
        )
        self.sizer.Add(
            self.listbox,
            flag=wx.ALIGN_TOP | wx.EXPAND | wx.ALL,
            proportion=1,
            border=5,
        )
        self.SetSizer(self.sizer)  # 设置主布局
        self.SetWindowStyle(wx.SIMPLE_BORDER)  # 设置简单边框样式

        # 初始化列表框内容
        for action in Actions.action_list:
            self.listbox.Append(action.label)  # 添加动作到列表框


class ActionTab(Panel):
    """动作标签页，包含动作编辑器和动作列表"""
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)  # 主布局管理器(水平)
        
        # 创建子控件
        self.editor = ActionEditor(self)  # 动作编辑器
        self.action_list = ActionList(self)  # 动作列表
        
        # 添加控件到布局
        self.sizer.Add(self.editor, flag=wx.EXPAND, proportion=1)  # 编辑器占主要空间
        self.sizer.Add(self.action_list, flag=wx.EXPAND | wx.ALL, proportion=0, border=5)
        self.SetSizer(self.sizer)  # 设置主布局
