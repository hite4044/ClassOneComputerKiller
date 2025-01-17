import wx
from typing import Callable
from libs.packets import *


class Client:
    def send_packet(self, packet, loss_enable: bool = False, priority: int = Priority.HIGHER): ...
    def recv_packet(self) -> tuple[int, None] | tuple[int, Packet]: ...
    def set_screen_send(self, enable: bool): ...
    def set_screen_fps(self, fps: int): ...
    def set_screen_quality(self, quality: int): ...
    def send_command(self, command: str): ...
    def restore_shell(self): ...

    sending_screen: bool = False
    pre_scale: bool = False
    mouse_control: bool = False
    keyboard_control: bool = False
    connected: bool = False
    screen_counter: int = 0
    screen_network_counter: int = 0


class ClientAPI:
    def __init__(self, client: Client):
        self.client = client
        self.send_callbacks = []
        self.recv_callbacks = []
        self.raw_recv_func = client.recv_packet
        client.recv_packet = self._recv_packet
        self.raw_send_func = client.send_packet
        client.send_packet = self._send_packet

    def register_recv_cbk(self, callback: Callable[[int, Packet], None]):
        self.recv_callbacks.append(callback)
    
    def register_send_cbk(self, callback: Callable[[int, bytes], None]):
        self.send_callbacks.append(callback)

    def send_packet(self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER):
        return self.client.send_packet(packet, loss_enable, priority)

    def set_screen_send(self, enable: bool):
        self.client.set_screen_send(enable)

    def set_screen_fps(self, fps: int):
        self.client.set_screen_fps(fps)

    def set_screen_quality(self, quality: int):
        self.client.set_screen_quality(quality)
    
    def send_command(self, command: str):
        self.client.send_command(command)
    
    def restore_shell(self):
        self.client.restore_shell()

    def set_keyboard_ctl(self, enable: bool):
        self.client.keyboard_control = enable

    def set_mouse_ctl(self, enable: bool):
        self.client.mouse_control = enable

    def set_pre_scale(self, enable: bool):
        self.client.pre_scale = enable

    def _recv_packet(self):
        length, packet = self.raw_recv_func()
        for callback in self.recv_callbacks:
            callback(length, packet)
        return length, packet
    
    def _send_packet(self, packet: Packet, loss_enable: bool = False, priority: int = Priority.HIGHER):
        length, data = self.raw_send_func(packet, loss_enable, priority)
        for callback in self.send_callbacks:
            callback(length, data)

    @property
    def sending_screen(self):
        return self.client.sending_screen

    @sending_screen.setter
    def sending_screen(self, value: bool):
        self.client.sending_screen = value

    @property
    def pre_scale(self):
        return self.client.pre_scale

    @pre_scale.setter
    def pre_scale(self, value: float):
        self.client.pre_scale = value

    @property
    def mouse_control(self):
        return self.client.mouse_control

    @mouse_control.setter
    def mouse_control(self, value: bool):
        self.client.mouse_control = value

    @property
    def keyboard_control(self):
        return self.client.keyboard_control

    @keyboard_control.setter
    def keyboard_control(self, value: bool):
        self.client.keyboard_control = value

    @property
    def connected(self):
        return self.client.connected

    @connected.setter
    def connected(self, value: bool):
        self.client.connected = value

    @property
    def screen_counter(self):
        return self.client.screen_counter

    @screen_counter.setter
    def screen_counter(self, value: int):
        self.client.screen_counter = value

    @property
    def screen_network_counter(self):
        return self.client.screen_network_counter

    @screen_network_counter.setter
    def screen_network_counter(self, value: int):
        self.client.screen_network_counter = value


def get_window_name(widget: wx.Window, name: str) -> str:
    while True:
        if not widget:
            raise Exception("Can't find Client window")
        widget = widget.GetParent()
        if type(widget).__name__ == name:
            return widget

def get_api(widget: wx.Window) -> ClientAPI:
    return get_window_name(widget, "Client").api
