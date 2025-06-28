import os
import wx
from gui.widgets import *
from libs.api import get_api
from posixpath import normpath
from posixpath import join as path_join
from win32con import FILE_ATTRIBUTE_NORMAL
from win32com.shell import shell, shellcon # type: ignore


def extension_to_bitmap(extension) -> wx.Bitmap:
    """
    将文件扩展名转换为位图图标。

    参数:
        extension (str): 文件扩展名，必须包含点号（例如 '.txt'）。

    返回:
        wx.Bitmap: 与文件扩展名关联的位图图标。
    """
    # 获取文件扩展名对应的图标信息
    flags = shellcon.SHGFI_SMALLICON | shellcon.SHGFI_ICON | shellcon.SHGFI_USEFILEATTRIBUTES
    retval, info = shell.SHGetFileInfo(extension, FILE_ATTRIBUTE_NORMAL, flags)
    assert retval
    
    # 提取图标句柄并创建图标对象
    hicon, _, _, _, _ = info
    icon: wx.Icon = wx.Icon()
    icon.SetHandle(hicon)
    
    # 创建位图对象并从图标复制图像
    bmp = wx.Bitmap()
    bmp.CopyFromIcon(icon)
    return bmp


class DataType:
    FILE = 0
    FOLDER = 1


class FilesData:
    def __init__(self, _type: int, name: str, item_id: wx.TreeItemId):
        # 初始化文件数据对象
        # 
        # 参数:
        # _type: 文件类型标识符
        # name: 文件名称
        # item_id: wx.TreeCtrl中的对应项ID
        # 
        # 属性:
        # name_dict: 存储名称到类型、ID和数据的映射
        # id_dict: 存储TreeItemId到类型、名称和数据的映射
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
            if not name:  # 跳过空路径段
                continue
            if name not in ret.name_dict:
                # 如果路径不存在，返回一个空的FilesData对象
                return FilesData(DataType.FOLDER, "", None)
            ret = ret.name_dict[name][2]
            if ret is None:  # 处理空节点
                return FilesData(DataType.FOLDER, "", None)
        return ret

    def clear(self):
        self.name_dict.clear()
        self.id_dict.clear()

    def clear_files(self):
        """仅清除文件项，保留目录项"""
        keys_to_remove = []
        for name, (_, _, data) in self.name_dict.items():
            if data and data.type == DataType.FILE:
                keys_to_remove.append(name)
        
        for key in keys_to_remove:
            del self.name_dict[key]

        ids_to_remove = []
        for item_id, (_, _, data) in self.id_dict.items():
            if data and data.type == DataType.FILE:
                ids_to_remove.append(item_id)
        
        for item_id in ids_to_remove:
            del self.id_dict[item_id]


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

        self.AppendItem(root, "加载中...")

        self.Bind(wx.EVT_TREE_ITEM_MENU, self.on_menu)

    def load_drive_list(self, drives: list[str]):
        """动态加载盘符列表"""
        root = self.GetRootItem()
        
        # 清除根节点下所有子项
        self.DeleteChildren(root)
        self.files_data.clear()
        
        # 添加实际盘符
        for drive in drives:
            drive_node = self.AppendItem(root, drive, image=self.folder_icon)
            self.AppendItem(drive_node, "加载中...")
            self.files_data.add(DataType.FOLDER, drive, drive_node)
        
        # 展开根节点
        self.Expand(root)

    def load_packet(self, packet: Packet):
        if packet.get("type") == "drive_list":  # 处理盘符列表
            self.load_drive_list(packet["drives"])
            return
        root_path = packet["path"]
        dirs = packet["dirs"]
        files = packet["files"]

        # 统一处理路径格式
        root_path = root_path.replace("\\", "/").replace("//", "/")
        # 提取盘符作为根节点
        drive, path_part = self.parse_drive_and_path(root_path)
        
        # 获取盘符节点
        drive_node = self.files_data.name_dict.get(drive)
        if not drive_node:
            return
        
        # 拆分路径部分
        paths = path_part.split("/") if path_part else []
        paths = [p for p in paths if p]  # 移除空路径段
        
        # 从盘符节点开始查找
        current_node = drive_node[2]  # FilesData对象
        for name in paths:
            if name not in current_node.name_dict:
                # 路径不存在，创建中间节点
                parent_id = current_node.item_id
                new_item = self.AppendItem(parent_id, name, image=self.folder_icon)
                self.AppendItem(new_item, "加载中...")
                current_node.add(DataType.FOLDER, name, new_item)
            current_node = current_node.name_dict[name][2]
        
        # 现在current_node是目标节点
        root_id = current_node.item_id
        
        # 清除现有文件项（保留目录项）
        current_node.clear_files()
        
        # 删除现有文件子项
        children = []
        cookie = wx.TreeItemId()
        child, cookie = self.GetFirstChild(root_id)
        while child.IsOk():
            children.append(child)
            child, cookie = self.GetNextChild(root_id, cookie)

        for child in children:
            if not self.ItemHasChildren(child):  # 只删除文件项
                self.Delete(child)
        
        # 添加新目录
        for dir_name in dirs:
            item_id = self.AppendItem(root_id, dir_name, image=self.folder_icon)
            self.AppendItem(item_id, "加载中...")
            current_node.add(DataType.FOLDER, dir_name, item_id)
        
        # 添加新文件
        for file_name in files:
            assert isinstance(file_name, str)
            icon = self.default_icon
            if "." in file_name:
                extension = file_name.split(".")[-1]
                if extension not in self.icons:
                    self.icons[extension] = self.image_list.Add(extension_to_bitmap("." + extension))
                icon = self.icons[extension]
            item_id = self.AppendItem(root_id, file_name, image=icon)
            current_node.add(DataType.FILE, file_name, item_id)
        
        if len(dirs + files) != 0 and root_id != self.GetRootItem():
            self.load_over_flag = True
            self.Expand(root_id)

    def parse_drive_and_path(self, path: str) -> tuple[str, str]:
        """提取盘符和剩余路径"""
        if ":/" in path:
            drive, path = path.split(":/", 1)
            return drive + ":", path.lstrip("/")
        return "", path.lstrip("/")


    def name_tree_get(self, names: list[str]):
        ret = self.files_data
        for name in names:
            if not name:  # 跳过空路径段
                continue
            if name not in ret.name_dict:
                # 如果路径不存在，创建一个新的FilesData对象
                new_item_id = self.AppendItem(ret.item_id, name, image=self.folder_icon)
                new_data = FilesData(DataType.FOLDER, name, new_item_id)
                ret.add(DataType.FOLDER, name, new_item_id)
                ret = new_data
            else:
                ret = ret.name_dict[name][2]
                if ret is None:  # 处理空节点
                    return FilesData(DataType.FOLDER, "", None)
        return ret

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
        path_parts = []
        current = item
        
        # 向上遍历直到根节点
        while current and current != self.GetRootItem():
            name = self.GetItemText(current)
            path_parts.insert(0, name)
            current = self.GetItemParent(current)
        
        # 合并路径部分
        if not path_parts:
            return ""
        
        # 确保盘符格式正确
        if len(path_parts) > 0 and path_parts[0].endswith(':'):
            # 盘符后添加斜杠
            path = path_parts[0] + "\\" + "\\".join(path_parts[1:])
        else:
            path = "\\".join(path_parts)
        
        # 替换可能的双斜杠
        path = path.replace("\\\\", "\\")
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
            menu.Bind(wx.EVT_MENU, lambda _: self.download_file(path), id=2)  # 下载功能
            menu.Bind(wx.EVT_MENU, lambda _: self.delete_path(path, item_id), id=3)
            menu.Bind(wx.EVT_MENU, lambda _: self.get_file_attributes(path), id=4)  # 属性功能
        elif files_data.type == DataType.FOLDER:
            menu.Append(1, "刷新此文件夹")
            menu.Append(2, "属性")
            menu.Bind(wx.EVT_MENU, lambda _: self.refresh_dir(path, item_id), id=1)
            menu.Bind(wx.EVT_MENU, lambda _: self.get_file_attributes(path), id=2)  # 属性功能
        self.PopupMenu(menu)
    
    def download_file(self, path: str):
        """请求下载文件"""
        packet = {"type": FILE_DOWNLOAD, "path": path}
        self.api.send_packet(packet)
    
    def get_file_attributes(self, path: str):
        """请求文件属性"""
        packet = {"type": FILE_ATTRIBUTES, "path": path}
        self.api.send_packet(packet)

    def view_file(self, path: str):
        # 检查路径是否合法
        if ".." in path or not os.path.isfile(path):
            wx.MessageBox("无效文件路径", "错误", wx.OK | wx.ICON_ERROR)
            return
        
        path = normpath(path)
        packet = {"type": FILE_VIEW, "path": path, "data_max_size": 1024 * 1024 * 1024}
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