#!/usr/bin/env python
# coding: utf-8

# 导入必要的库
import hashlib    # 用于哈希计算
import hmac       # 用于HMAC签名
import json       # 用于JSON数据处理
import logging    # 日志记录
import time       # 时间相关功能
import threading  # 多线程支持
from tkinter import Y  # (未使用，可考虑移除)

from websocket import WebSocketApp  # WebSocket客户端库

# 配置基础日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 线程事件对象，用于控制线程执行
event = threading.Event()

class GateWebSocketApp(WebSocketApp):
    """Gate.io交易所WebSocket客户端实现类"""

    def __init__(self, url, api_key, api_secret, **kwargs):
        """初始化WebSocket连接
        Args:
            url: WebSocket服务器URL
            api_key: Gate.io API密钥
            api_secret: Gate.io API密钥对应的密钥
            **kwargs: 传递给父类的其他参数
        """
        super(GateWebSocketApp, self).__init__(url, **kwargs)
        self._api_key = api_key      # 存储API密钥
        self._api_secret = api_secret  # 存储API密钥对应的密钥

    def _send_ping(self):
        """定期发送ping消息保持连接活跃
        每10秒发送一次ping，防止连接超时断开
        """
        while not event.wait(10):  # 每10秒执行一次
            self.last_ping_tm = time.time()  # 记录最后ping时间
            if self.sock:  # 检查socket连接是否存在
                try:
                    self.sock.ping()  # 发送底层ping
                except Exception as ex:
                    logger.warning("send_ping routine terminated: {}".format(ex))
                    break
                try:
                    self._request("futures.ping", auth_required=False)  # 发送业务ping
                except Exception as e:
                    raise e

    def _request(self, channel, event=None, payload=None, auth_required=True):
        """构造并发送WebSocket请求
        Args:
            channel: 订阅的频道名称
            event: 事件类型(subscribe/unsubscribe等)
            payload: 附加数据
            auth_required: 是否需要认证
        """
        current_time = int(time.time())  # 获取当前时间戳
        data = {
            "time": current_time,    # 请求时间
            "channel": channel,      # 订阅频道
            "event": event,          # 事件类型
            "payload": payload,      # 附加数据
        }
        if auth_required:  # 如果需要认证
            message = 'channel=%s&event=%s&time=%d' % (channel, event, current_time)
            data['auth'] = {  # 添加认证信息
                "method": "api_key",  # 认证方法
                "KEY": self._api_key,  # API密钥
                "SIGN": self.get_sign(message),  # 签名
            }
        data = json.dumps(data)  # 转换为JSON字符串
        logger.info('request: %s', data)  # 记录请求日志
        self.send(data)  # 发送请求

    def get_sign(self, message):
        """生成HMAC-SHA512签名
        Args:
            message: 要签名的消息
        Returns:
            签名结果的十六进制字符串
        """
        h = hmac.new(self._api_secret.encode("utf8"), message.encode("utf8"), hashlib.sha512)
        return h.hexdigest()

    def subscribe(self, channel, payload=None, auth_required=True):
        """订阅指定频道
        Args:
            channel: 要订阅的频道名称
            payload: 附加数据
            auth_required: 是否需要认证
        """
        self._request(channel, "subscribe", payload, auth_required)

    def unsubscribe(self, channel, payload=None, auth_required=True):
        """取消订阅指定频道
        Args:
            channel: 要取消订阅的频道名称
            payload: 附加数据
            auth_required: 是否需要认证
        """
        self._request(channel, "unsubscribe", payload, auth_required)


def on_message(ws, message):
    # type: (GateWebSocketApp, str) -> None
    """WebSocket消息接收回调函数
    Args:
        ws: WebSocketApp实例
        message: 接收到的消息内容
    """
    logger.info("message received from server: {}".format(message))


def on_open(ws):
    # type: (GateWebSocketApp) -> None
    """WebSocket连接建立回调函数
    Args:
        ws: WebSocketApp实例
    """
    logger.info('websocket connected')
    # 连接建立后自动订阅BTC_USDT合约的行情频道
    ws.subscribe("futures.tickers", ['BTC_USDT'], False)


if __name__ == "__main__":
    """主程序入口"""
    logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.DEBUG)
    # 注意：这里使用示例API密钥，实际使用时应替换为您自己的密钥

    # YOUR_API_KEY = ""
    # YOUR_API_SECRET= ""
    
    YOUR_API_KEY = "03cb2a2eca9e1844c9878e4dd6f61963"
    YOUR_API_SECRET = "13ebc1ffa57558929a040e9133423a6d71efdb03af0f94978ce02d486fd0263f"

    # 创建WebSocket客户端实例
    app = GateWebSocketApp("wss://fx-ws.gateio.ws/v4/ws/usdt",
                           YOUR_API_KEY,
                           YOUR_API_SECRET,
                           on_open=on_open,    # 设置连接建立回调
                           on_message=on_message)  # 设置消息接收回调
    # 启动WebSocket连接，保持5秒ping间隔
    app.run_forever(ping_interval=5)

