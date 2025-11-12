# !/usr/bin/env python
# coding: utf-8

import hashlib
import hmac
import json
import logging
import time
import threading
from tkinter import Y

from websocket import WebSocketApp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

event = threading.Event()

class GateWebSocketApp(WebSocketApp):

  def __init__(self, url, api_key, api_secret, **kwargs):
    super(GateWebSocketApp, self).__init__(url, **kwargs)
    self._api_key = api_key
    self._api_secret = api_secret

  def _send_ping(self):
    while not event.wait(10):
      self.last_ping_tm = time.time()
      if self.sock:
        try:
          self.sock.ping()
        except Exception as ex:
          logger.warning("send_ping routine terminated: {}".format(ex))
          break
        try:
          self._request("futures.ping", auth_required=False)
        except Exception as e:
          raise e

  def _request(self, channel, event=None, payload=None, auth_required=True):
    current_time = int(time.time())
    data = {
      "time": current_time,
      "channel": channel,
      "event": event,
      "payload": payload,
    }
    if auth_required:
      message = 'channel=%s&event=%s&time=%d' % (channel, event, current_time)
      data['auth'] = {
        "method": "api_key",
        "KEY": self._api_key,
        "SIGN": self.get_sign(message),
      }
    data = json.dumps(data)
    logger.info('request: %s', data)
    self.send(data)

  def get_sign(self, message):
    h = hmac.new(self._api_secret.encode("utf8"), message.encode("utf8"), hashlib.sha512)
    return h.hexdigest()

  def subscribe(self, channel, payload=None, auth_required=True):
    self._request(channel, "subscribe", payload, auth_required)

  def unsubscribe(self, channel, payload=None, auth_required=True):
    self._request(channel, "unsubscribe", payload, auth_required)


def on_message(ws, message):
  # type: (GateWebSocketApp, str) -> None
  # handle message received
  logger.info("message received from server: {}".format(message))


def on_open(ws):
  # type: (GateWebSocketApp) -> None
  # subscribe to channels interested
  logger.info('websocket connected')
  ws.subscribe("futures.tickers", ['BTC_USDT'], False)


if __name__ == "__main__":
  logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.DEBUG)
  YOUR_API_KEY = "03cb2a2eca9e1844c9878e4dd6f61963"
  YOUR_API_SECRET = "13ebc1ffa57558929a040e9133423a6d71efdb03af0f94978ce02d486fd0263f"

  app = GateWebSocketApp("wss://fx-ws.gateio.ws/v4/ws/usdt",
                         YOUR_API_KEY,
                         YOUR_API_SECRET,
                         on_open=on_open,
                         on_message=on_message)
  app.run_forever(ping_interval=5)

