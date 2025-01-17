import json
import random
from typing import Any
from posixpath import abspath
from genericpath import isfile


class DefaultConfig:
    """设置默认值, 并将键名称作为配置文件的名称"""

    HOST = "127.0.0.1"  # 服务器地址
    PORT = 10616  # 服务器端口
    UUID = hex(int.from_bytes(random.randbytes(8), "big"))[2:]  # 客户端默认UUID
    FILE_BLOCK_SIZE = 1024 * 100  # 文件块大小
    RECONNECT_TIME = 2  # 重连间隔时间
    CONNECT_TIMEOUT = 2  # 连接超时时间
    HOST_CHANGED = None  # 地址被服务端改变后，该值为[old_host, old_port]
    TIMEOUT_ADD = False  # 连接失败后是否增加重试间隔
    TIMEOUT_ADD_MULTIPLIER = 1.5  # 每次增加的时间倍率
    RECORD_KEY = False  # 启用按键记录


class Config:
    """配置文件 加载, 调用, 保存 器"""

    raw_config = {}

    def __init__(self, config_path: str = "config.json"):
        self.config_path = abspath(config_path)
        self.load_config()
        print(self.raw_config)

    def load_config(self):
        config_data = self.load_file_config()
        for attr_name in dir(DefaultConfig):
            if not attr_name.startswith("__"):
                key_name = attr_name.lower()
                config_data[key_name] = config_data.get(key_name, getattr(DefaultConfig, attr_name))
        self.raw_config = config_data
        self.save_config()

    def load_file_config(self) -> dict:
        config_data = {}
        if isfile(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    config_data = json.load(f)
            except OSError as e:
                print(f"Error loading config: {e}")
        return config_data

    def save_config(self):
        config_path = abspath("config.json")
        try:
            with open(config_path, "w") as f:
                json.dump(self.raw_config, f, indent=4)
        except OSError as e:
            print(f"Error saving config: {e}")

    def __getattr__(self, name: str):
        raw_config: dict = object.__getattribute__(self, "raw_config")
        if name in raw_config.keys():
            return raw_config[name]
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any):
        raw_config: dict = object.__getattribute__(self, "raw_config")
        if name in raw_config.keys():
            raw_config[name] = value
        object.__setattr__(self, name, value)
