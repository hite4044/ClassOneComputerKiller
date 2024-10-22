import wx
from wx import grid
from gui.widgets import *
from libs.action import *
from libs.api import get_api, get_window_name


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
        self.api = get_api(self)
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
        the_action = TheAction(name, actions, start_prqs, end_prqs)
        self.datas.append(the_action)
        self.api.send_packet(the_action.build_packet())


class StartPrqList(AddableList):
    def __init__(self, parent):
        super().__init__(parent, "开始条件")

    def on_add(self):
        ItemChoiceDialog(self, "选择开始条件", [("1", "条件1"), ("2", "条件2")], self.add_callback)

    def add_callback(self, name: str, data: str):
        self.add_item(name, data)


class EndPrqList(AddableList):
    def __init__(self, parent):
        super().__init__(parent, "结束条件")

    def on_add(self):
        ItemChoiceDialog(self, "选择结束条件", [("1", "条件1"), ("2", "条件2")], self.add_callback)

    def add_callback(self, name: str, data: str):
        self.add_item(name, data)


class ActionAddDialog(wx.Frame):
    def __init__(self, parent):
        assert isinstance(parent, ActionEditor)
        super().__init__(get_window_name(parent, "Client"), title="动作编辑器", size=(420, 390))
        self.action_editor = parent
        self.SetFont(ft(12))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.name_inputter = LabelEntry(self, "名称: ")
        self.prq_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_prqs = StartPrqList(self)
        self.end_prqs = EndPrqList(self)
        self.actions_chooser = LabelCombobox(self, "动作: ", [("动作1", "114514"), ("动作2", "54188")])
        self.bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_btn = wx.Button(self, label="确定")
        self.cancel_btn = wx.Button(self, label="取消")

        for i in range(10):
            self.start_prqs.listbox.Append(f"Test:{i}")
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.name_inputter.label_ctl.SetFont(ft(13))
        self.actions_chooser.label_ctl.SetFont(ft(13))

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
        self.grid = ActionGrid(self)

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

    def on_add_action(self, _):
        ActionAddDialog(self)

    def add_action(self, name: str, start_prqs: list, end_prqs: list, actions: list[AnAction]):
        self.grid.add_action(name, start_prqs, end_prqs, actions)


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
