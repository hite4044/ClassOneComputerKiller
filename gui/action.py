import wx
from wx import grid
from gui.widgets import *
from libs.action import *
from libs.api import get_api, get_window_name
from libs.packets import Any


class ActionEditDialog(wx.Frame):
    def __init__(
        self,
        parent: wx.Window,
        title: str,
        callback: Callable[[TheAction], None],
        action_init: TheAction = None,
    ):
        super().__init__(get_window_name(parent, "Client"), title=title, size=(420, 390))
        self.callback = callback

        self.SetFont(ft(12))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.name_inputter = LabelEntry(self, "名称: ")
        self.prq_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_prqs = StartPrqList(self)
        self.end_prqs = EndPrqList(self)
        self.actions_chooser = LabelCombobox(self, "动作: ")
        self.bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_btn = wx.Button(self, label="确定")
        self.cancel_btn = wx.Button(self, label="取消")

        for _, action_type in actions_map.items():
            self.actions_chooser.add_choice(action_type.ch_name(), action_type)
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.name_inputter.label_ctl.SetFont(ft(13))
        self.actions_chooser.label_ctl.SetFont(ft(13))

        self.sizer.Add(self.name_inputter, flag=wx.EXPAND, proportion=0)
        self.sizer.AddSpacer(6)
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
        self.SetSizer(self.sizer)
        self.SetIcon(wx.Icon(abspath(r"assets\action_editor.ico")))
        self.Show()

    def on_ok(self, _):
        msg = self.callback_action()
        if msg:
            MessageBox(self.Handle, msg, "错误", wx.OK | wx.ICON_ERROR)
        else:
            self.Close()

    def callback_action(self) -> None | str:
        name = self.name_inputter.text.GetValue()

        start_prqs = self.start_prqs.get_items()
        end_prqs = self.end_prqs.get_items()
        if start_prqs == []:
            return "请选择至少一个开始条件"
        if end_prqs == []:
            end_prqs.append(NoneEndPrq())

        action_type: AnAction = self.actions_chooser.get_data()
        if action_type is None:
            return "请选择要执行的操作"
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
        action: AnAction = flash[3](**datas)
        self.callback(TheAction(flash[0], 1, [action], flash[1], flash[2]))

    def on_cancel(self, _):
        self.Close()


class DataInputter(wx.Panel):
    def __init__(self, parent, param: ActionParam) -> None:
        super().__init__(parent)
        self.SetWindowStyle(wx.MINIMIZE_BOX)
        self.param = param
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.label = wx.StaticText(self, label=param.label)
        self.label.SetFont(ft(13))
        self.sizer.Add(self.label, proportion=0)
        self.sizer.AddSpacer(6)
        self.normal_color = None
        if param.type in [ParamType.FLOAT, ParamType.INT, ParamType.STRING]:
            self.inputter = wx.TextCtrl(self)
            self.normal_color = self.inputter.GetBackgroundColour()
            self.inputter.SetValue(str(param.default))
        elif param.type == ParamType.BOOL:
            self.inputter = wx.CheckBox(self)
            self.inputter.SetValue(param.default)
        elif param.type == ParamType.CHOICE:
            assert isinstance(param, ChoiceParam)
            self.inputter = wx.ComboBox(self, style=wx.CB_READONLY)
            self.inputter.SetItems([name for name, _ in param.choices.items()])
            self.inputter.SetValue(param.default)
        self.inputter.SetFont(ft(13))

        self.sizer.Add(self.inputter, flag=wx.EXPAND, proportion=1)
        self.SetSizer(self.sizer)

    def valid(self):
        return self.param.valid(self.inputter.GetValue())

    def get_data(self):
        if self.valid() is None:
            return self.param.parse_string(self.inputter.GetValue())
        else:
            return None


class DataInputDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        title: str,
        params: dict[str, ActionParam],
        callback: Callable[[dict[str, Any]], None],
    ):
        super().__init__(get_window(parent), title=title, size=(420, 390))
        self.callback = callback

        self.params = params

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.inputter_container = wx.ScrolledWindow(self)
        self.ok_btn = wx.Button(self, label="确定")
        self.cancel_btn = wx.Button(self, label="取消")
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, lambda: self.Close())
        bottom_bar = wx.BoxSizer(wx.HORIZONTAL)

        container_sizer = wx.BoxSizer(wx.VERTICAL)
        self.inputters: dict[str, DataInputter] = {}
        for name, param in params.items():
            inputter = DataInputter(self.inputter_container, param)
            self.inputters[name] = inputter
            container_sizer.Add(inputter, flag=wx.EXPAND, proportion=0)
            container_sizer.AddSpacer(6)
        self.inputter_container.SetSizer(container_sizer)

        sizer.Add(self.inputter_container, flag=wx.EXPAND, proportion=1)
        sizer.AddSpacer(6)
        bottom_bar.Add(self.ok_btn, proportion=0)
        bottom_bar.AddSpacer(6)
        bottom_bar.Add(self.cancel_btn, proportion=0)
        sizer.Add(bottom_bar, flag=wx.ALIGN_RIGHT | wx.ALL, border=6)
        self.SetSizer(sizer)
        self.ShowModal()

    def on_ok(self, _):
        data = {}
        for name, inputter in self.inputters.items():
            data[name] = inputter.get_data()
        if None in data.values():
            print(data)
            wx.MessageBox("请检查输入", "错误", wx.OK | wx.ICON_ERROR)
        else:
            self.callback(data)
            self.Close()


class ActionGrid(grid.Grid):
    def __init__(self, parent: "ActionEditor"):
        super().__init__(parent, size=MAX_SIZE)
        self.action_editor: ActionEditor = parent
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
        self.api = get_api(self)
        self.SetDefaultCellAlignment(wx.ALIGN_CENTER, wx.ALIGN_CENTER)

        self.SetRowLabelSize(1)
        self.EnableEditing(False)
        self.SetLabelFont(font)
        self.SetDefaultCellFont(font)
        self.Bind(grid.EVT_GRID_CELL_RIGHT_CLICK, self.on_row_menu)

    def on_row_menu(self, event: grid.GridEvent):
        row = event.GetRow()
        menu = wx.Menu()
        menu.Append(1, "新建")
        menu.Append(2, "编辑")
        menu.Bind(wx.EVT_MENU, self.action_editor.on_add_action, id=1)
        menu.Bind(wx.EVT_MENU, lambda: self.on_edit(row), id=2)
        self.PopupMenu(menu)

    def on_empty_menu(self, event: wx.MenuEvent):
        menu = wx.Menu()
        menu.Append(1, "新建")
        menu.Bind(wx.EVT_MENU, self.action_editor.on_add_action, id=1)
        self.PopupMenu(menu)

    def on_edit(self, row: int):
        action = self.datas[row]
        ActionEditDialog(self, action)

    def add_action(self, the_action: TheAction) -> TheAction:
        if self.first_add:
            self.first_add = False
            row = 0
        else:
            self.AppendRows(1)
            row = self.GetNumberRows() - 1

        self.SetCellValue(row, 0, the_action.name)
        self.SetCellValue(row, 1, " ".join([start.name() for start in the_action.start_prqs]))
        self.SetCellValue(row, 2, " ".join([action.name() for action in the_action.actions]))
        self.SetCellValue(row, 3, " ".join([end.name() for end in the_action.end_prqs]))
        self.datas.append(the_action)
        return the_action


class StartPrqList(AddableList):
    def __init__(self, parent):
        data = [(prq.ch_name(), prq) for prq in start_prqs_map.values()]
        super().__init__(parent, "开始条件", data, "添加开始条件")

    def add_item(self, name: str, _type: StartPrq, index: int = -1):
        """稍后请求条件数据"""
        wx.CallAfter(self.request_data, _type)

    def request_data(self, _type: StartPrq):
        """如果需要参数, 则弹出数据请求窗口"""
        if _type.params:
            DataInputDialog(self, "输入条件参数", _type.params, lambda ps: self.add_prq(ps, _type))
        else:
            self.add_prq({}, _type)

    def add_prq(self, params: dict[str, Any], _type: StartPrq):
        """添加一个以特定参数初始化的条件进入列表"""
        prq: StartPrq = _type(**params)
        super().add_item(prq.name(), prq)


class EndPrqList(AddableList):
    def __init__(self, parent):
        data = [(prq.ch_name(), prq) for prq in end_prqs_map.values()]
        super().__init__(parent, "结束条件", data, "添加结束条件")

    def add_item(self, name: str, _type: EndPrq, index: int = -1):
        """稍后请求条件数据"""
        wx.CallAfter(self.request_data, _type)

    def request_data(self, _type: EndPrq):
        """如果需要参数, 则弹出数据请求窗口"""
        if _type.params:
            DataInputDialog(self, "输入条件参数", _type.params, lambda ps: self.add_prq(ps, _type))
        else:
            self.add_prq({}, _type)

    def add_prq(self, params: dict[str, Any], _type: EndPrq):
        """添加一个以特定参数初始化的条件进入列表"""
        prq: EndPrq = _type(**params)
        super().add_item(prq.name(), prq)


class ActionEditor(Panel):
    def __init__(self, parent: wx.Window):
        super().__init__(parent, size=MAX_SIZE)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.grid = ActionGrid(self)
        self.api = get_api(self)

        self.bar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(self, label="添加操作")
        self.remove_btn = wx.Button(self, label="删除操作")
        self.add_btn.Bind(wx.EVT_BUTTON, self.on_add_action)
        self.grid.SetWindowStyle(wx.SIMPLE_BORDER)
        self.bar_sizer.Add(self.add_btn)
        self.bar_sizer.AddSpacer(6)
        self.bar_sizer.Add(self.remove_btn)

        self.sizer.Add(
            self.bar_sizer,
            flag=wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT,
            border=6,
        )
        self.sizer.Add(self.grid, flag=wx.EXPAND | wx.ALL, border=6)
        self.SetSizer(self.sizer)

    def on_add_action(self, _=None):
        ActionEditDialog(self, "增加操作", self.add_action, None)

    def add_action(self, the_action: TheAction):
        self.grid.add_action(the_action)
        packet = {"type": ACTION_ADD, **the_action.build_packet()}
        self.api.send_packet(packet)


class ActionList(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(250, 703))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.text = wx.StaticText(self, label="操作列表", style=wx.ALIGN_LEFT)
        bmp = wx.Bitmap()
        bmp.LoadFile(abspath(r"assets\add.png"), wx.BITMAP_TYPE_PNG)
        self.add_btn = wx.BitmapButton(self, bitmap=bmp)
        self.listbox = wx.ListBox(self, style=wx.LB_SINGLE)
        self.text.SetFont(ft(13))

        self.top_sizer.Add(self.text, flag=wx.EXPAND | wx.TOP | wx.LEFT, proportion=1, border=4)
        self.top_sizer.Add(self.add_btn, flag=wx.TOP | wx.RIGHT, proportion=0, border=4)
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
        self.SetSizer(self.sizer)
        self.SetWindowStyle(wx.SIMPLE_BORDER)

        for action in Actions.action_list:
            self.listbox.Append(action.label)


class ActionTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.editor = ActionEditor(self)
        self.action_list = ActionList(self)
        self.sizer.Add(self.editor, flag=wx.EXPAND, proportion=1)
        self.sizer.Add(self.action_list, flag=wx.EXPAND | wx.ALL, proportion=0, border=5)
        self.SetSizer(self.sizer)
