import wx
from gui.widgets import *
from libs.api import get_api
from posixpath import normpath
from posixpath import join as path_join
from win32con import FILE_ATTRIBUTE_NORMAL
from win32com.shell import shell, shellcon # type: ignore


def extension_to_bitmap(extension) -> wx.Bitmap:
    """dot is mandatory in extension"""

    flags = shellcon.SHGFI_SMALLICON | shellcon.SHGFI_ICON | shellcon.SHGFI_USEFILEATTRIBUTES
    retval, info = shell.SHGetFileInfo(extension, FILE_ATTRIBUTE_NORMAL, flags)
    assert retval
    hicon, _, _, _, _ = info
    icon: wx.Icon = wx.Icon()
    icon.SetHandle(hicon)
    bmp = wx.Bitmap()
    bmp.CopyFromIcon(icon)
    return bmp


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


class FilesTreeView(wx.TreeCtrl):
    def __init__(self, parent):
        super().__init__(parent=parent, size=MAX_SIZE, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT)

        self.image_list = wx.ImageList(16, 16, True)
        self.folder_icon = self.image_list.Add(
            wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
        )
        self.default_icon = self.image_list.Add(
            wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
        )
        self.icons = {}
        self.AssignImageList(self.image_list)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.on_expend)

        self.api = get_api(self)
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

        paths: list = normpath(root_path).split("\\")
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
                    self.icons[extension] = self.image_list.Add(extension_to_bitmap("." + extension))
                icon = self.icons[extension]
            else:
                icon = self.default_icon
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
        self.api.send_packet(packet)

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
        self.api.send_packet(packet)

    def refresh_dir(self, path: str, item_id: wx.TreeItemId):
        path = normpath(path)
        self.Collapse(item_id)
        self._request_list_dir(path)

    def delete_path(self, path: str, item_id: wx.TreeItemId):
        packet = {"type": FILE_DELETE, "path": path}
        self.api.send_packet(packet)
        self.Delete(item_id)


class FileTransport(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(400, 668))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_bar = wx.Gauge(self, range=100)


class FilesTab(Panel):
    def __init__(self, parent):
        super().__init__(parent=parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.viewer = FilesTreeView(self)
        self.files_transport_panel = FileTransport(self)
        self.sizer.Add(self.viewer, flag=wx.ALIGN_TOP | wx.EXPAND)
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

        self.ctrl_down = False
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
