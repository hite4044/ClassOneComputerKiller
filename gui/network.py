import wx
from gui.widgets import *
from libs.api import get_api


class NTWConfig:
    view_x = 80
    view_y = 0
    view_Ox = 0
    view_Oy = 50


class NetworkUtilization(Panel):
    """显示网络占用的图表控件"""

    def __init__(self, parent: wx.Window):
        super().__init__(parent, size=MAX_SIZE)
        self.datas: list[tuple[int, int]] = []  # 储存数据帧
        self.data_lock = Lock()
        self.send_counter = 0  # 发送字节计数器
        self.recv_counter = 0  # 接收字节计数器
        self.last_upt = perf_counter()
        self.api = get_api(self)
        self.api.register_recv_cbk(self.recv_cbk)
        self.api.register_send_cbk(self.send_cbk)

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.upt_timer = wx.Timer(self)
        self.upt_timer.Start(1000)
        self.Bind(wx.EVT_TIMER, self.update_data, self.upt_timer)
        self.Bind(wx.EVT_KEY_DOWN, lambda e: self.update_data() if e.GetKeyCode() == wx.WXK_F5 else None)

    def recv_cbk(self, length: int, _: Packet):
        self.recv_counter += length

    def send_cbk(self, length: int, _: bytes):
        self.send_counter += length

    def update_data(self, *_):
        """添加数据进入列表"""
        self.add_frame(
            int(self.send_counter * round(perf_counter() - self.last_upt, 2)),
            int(self.recv_counter * round(perf_counter() - self.last_upt, 2)),
        )
        self.last_upt = perf_counter()
        self.send_counter = 0
        self.recv_counter = 0

    def add_frame(self, send: int, recv: int):
        """添加一个数据帧 (发送的字节数, 接收的字节数)"""
        with self.data_lock:
            self.datas.append((send, recv))
            if len(self.datas) > 100:
                self.datas.pop(0)
        self.Refresh()

    def OnPaint(self, event: wx.PaintEvent):
        """用不同的颜色绘制网络流量折线图, 并自适应数据绘制倍率"""
        dc = wx.PaintDC(self)
        dc.SetBrush(wx.Brush(wx.Colour(255, 0, 0)))

        w, h = self.GetClientSize()
        with self.data_lock:
            if self.datas == []:
                event.Skip()
                return

            max_data = max(max(send, recv) for send, recv in self.datas[len(self.datas) // 10 :])
            if max_data == 0:
                event.Skip()
                return

            magnification = h / max_data
            self.draw_data_lines(
                dc,
                magnification,
                wx.Rect(
                    NTWConfig.view_x, NTWConfig.view_y, w - NTWConfig.view_Ox, h - NTWConfig.view_Oy
                ),
            )
            self.draw_scale(
                dc,
                magnification,
                wx.Rect(
                    NTWConfig.view_x - 70,
                    NTWConfig.view_y + 23,
                    w - NTWConfig.view_Ox,
                    h - NTWConfig.view_Oy - 5,
                ),
            )

        event.Skip()

    def draw_scale(self, dc: wx.PaintDC, magnification: float, rect: wx.Rect = None):
        """绘制纵向的速度刻度和横向的时间刻度"""
        if rect is None:
            rect = wx.Rect(0, 0, *self.GetClientSize())
        w, h = rect.GetSize()
        xOft = rect.GetX()
        yOft = rect.GetY()
        max_data = max(max(send, recv) for send, recv in self.datas)
        step = max_data / 10

        # 绘制纵向的速度刻度
        for i in range(11):
            y = h - i * step * magnification
            dc.DrawLine(
                0 + xOft,
                int(y) + yOft + NTWConfig.view_Oy,
                10 + xOft,
                int(y) + yOft + NTWConfig.view_Oy,
            )
            dc.DrawText(str(format_size(i * step, 1)), 12 + xOft, int(y - 10) + yOft + NTWConfig.view_Oy)

        w += 5
        # 绘制横向的时间刻度
        if len(self.datas) > 1:
            step = (w - NTWConfig.view_x) / (len(self.datas) - 1)
            for i in range(0, len(self.datas), max(1, len(self.datas) // 15)):
                x = i * step
                dc.DrawLine(
                    wx.Point((int(x) + xOft + NTWConfig.view_x, h - 10 + yOft)),
                    wx.Point((int(x) + xOft + NTWConfig.view_x, h + yOft)),
                )
                if len(str(i)) == 1:
                    x_offset = -5
                else:
                    x_offset = -8
                dc.DrawText(str(i), int(x + x_offset) + xOft + NTWConfig.view_x, h + 5 + yOft)

    def draw_data_lines(self, dc: wx.PaintDC, magnification: float, rect: wx.Rect = None):
        """绘制数据折线图"""
        if rect is None:
            rect = wx.Rect(0, 0, *self.GetClientSize())
        w, h = rect.GetSize()

        # 绘制坐标轴
        dc.DrawLine(0, h, w, h)
        dc.DrawLine(0, 0, 0, h)

        # 绘制发送和接收的折线图
        send_points = [
            wx.Point((i * (w / len(self.datas)), h - send * magnification))
            for i, (send, _) in enumerate(self.datas)
        ]
        recv_points = [
            wx.Point((i * (w / len(self.datas)), h - recv * magnification))
            for i, (_, recv) in enumerate(self.datas)
        ]
        dc.SetPen(wx.Pen(wx.Colour(255, 0, 0)))
        dc.DrawLines(send_points, 0 + rect.GetX(), -1 + rect.GetY())
        dc.SetPen(wx.Pen(wx.Colour(0, 255, 0)))
        dc.DrawLines(recv_points, 0 + rect.GetX(), -1 + rect.GetY())


class NetworkTab(Panel):
    def __init__(self, parent: wx.Window):
        super().__init__(parent, size=(1210, 668))
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.net_util = NetworkUtilization(self)
        self.sizer.Add(self.net_util, wx.EXPAND)
        self.SetSizer(self.sizer)
