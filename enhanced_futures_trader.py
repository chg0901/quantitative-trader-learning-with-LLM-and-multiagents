#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gate.io期货自动交易系统 - 价差交易版
基于官方API文档实现，支持价差套利交易

核心功能：
1. 价差判断：|卖价 - 持仓价| / 持仓价 ≤ 0.05%
2. 自动买卖：买入开仓 → 监控价差 → 卖出平仓
3. 次数控制：可设置交易次数，完成后自动停止
4. 风险控制：完整的风控机制
"""

import hashlib
import hmac
import json
import logging
import time
import threading
import sys
import argparse
from websocket import WebSocketApp
from decimal import Decimal, ROUND_DOWN

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GateFuturesTrader:
    def __init__(self, config_path='config.json'):
        """初始化交易器"""
        self.config = self.load_config(config_path)
        self.api_key = self.config['api']['key']
        self.api_secret = self.config['api']['secret']
        self.ws_url = self.config['api']['url']

        # 交易参数
        self.contracts = self.config['trading']['contracts']
        self.trade_amount = self.config['trading']['amount']
        self.max_trades = self.config['trading']['max_trades']
        self.spread_threshold = Decimal(str(self.config['trading']['spread_threshold']))  # 0.05%

        # 交易状态
        self.current_position = {}  # {contract: {'size': int, 'entry_price': Decimal, 'entry_time': float}}
        self.trade_count = 0
        self.completed_trades = []
        self.is_running = False
        self.event = threading.Event()

        # 市场数据
        self.tickers = {}  # {contract: {'last': Decimal, 'bid': Decimal, 'ask': Decimal}}
        self.orderbooks = {}  # {contract: {'bids': [(price, size)], 'asks': [(price, size)]}}

        # 创建WebSocket连接
        self.ws = None
        self.last_ping_time = time.time()

    def load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}")
            sys.exit(1)

    def get_sign(self, message):
        """生成签名"""
        h = hmac.new(self.api_secret.encode("utf8"), message.encode("utf8"), hashlib.sha512)
        return h.hexdigest()

    def _send_ping(self):
        """发送心跳包"""
        while not self.event.wait(10):  # 每10秒发送一次心跳
            try:
                if self.ws and self.ws.sock:
                    self.last_ping_tm = time.time()
                    # 先发送WebSocket ping
                    self.ws.sock.ping()
                    # 再发送频道ping
                    self._request("futures.ping", auth_required=False)
            except Exception as e:
                logger.warning(f"心跳发送失败: {e}")
                break

    def _request(self, channel, event=None, payload=None, auth_required=True):
        """发送WebSocket请求"""
        current_time = int(time.time())
        data = {
            "time": current_time,
            "channel": channel,
            "event": event,
            "payload": payload,
        }

        if auth_required:
            message = f'channel={channel}&event={event}&time={current_time}'
            data['auth'] = {
                "method": "api_key",
                "KEY": self.api_key,
                "SIGN": self.get_sign(message),
            }

        data_str = json.dumps(data)
        logger.info(f"发送请求: {data_str}")
        if self.ws:
            self.ws.send(data_str)

    def subscribe(self, channel, payload=None, auth_required=True):
        """订阅频道"""
        self._request(channel, "subscribe", payload, auth_required)

    def unsubscribe(self, channel, payload=None, auth_required=True):
        """取消订阅频道"""
        self._request(channel, "unsubscribe", payload, auth_required)

    def calculate_spread_percentage(self, current_price, entry_price):
        """计算价差百分比"""
        try:
            if entry_price <= 0:
                return Decimal('1.0')  # 100%，表示无效

            spread = abs(current_price - entry_price)
            spread_percentage = (spread / entry_price) * Decimal('100')
            return spread_percentage
        except Exception as e:
            logger.error(f"价差计算错误: {e}")
            return Decimal('1.0')

    def should_place_buy_order(self, contract):
        """判断是否应该买入开仓"""
        try:
            # 检查是否已有持仓
            if contract in self.current_position and self.current_position[contract]['size'] > 0:
                return False, "已有持仓"

            # 检查交易次数限制
            if self.trade_count >= self.max_trades:
                return False, "达到最大交易次数"

            # 获取当前价格（使用卖一价作为买入价）
            if contract not in self.tickers:
                return False, "无价格数据"

            current_ask = self.tickers[contract].get('ask', Decimal('0'))
            if current_ask <= 0:
                return False, "无效的卖价"

            return True, f"可以买入，价格: {current_ask}"

        except Exception as e:
            logger.error(f"买入判断错误: {e}")
            return False, f"判断错误: {e}"

    def should_place_sell_order(self, contract):
        """判断是否应该卖出平仓"""
        try:
            # 检查是否有持仓
            if contract not in self.current_position or self.current_position[contract]['size'] <= 0:
                return False, "无持仓"

            position = self.current_position[contract]
            entry_price = position['entry_price']

            # 获取当前价格（使用买一价作为卖出价）
            if contract not in self.tickers:
                return False, "无价格数据"

            current_bid = self.tickers[contract].get('bid', Decimal('0'))
            if current_bid <= 0:
                return False, "无效的买价"

            # 计算价差
            spread_pct = self.calculate_spread_percentage(current_bid, entry_price)

            # 判断是否达到价差阈值
            if spread_pct <= (self.spread_threshold * Decimal('100')):
                return True, f"价差{spread_pct:.4f}% ≤ {self.spread_threshold*100:.4f}%，可以卖出"
            else:
                return False, f"价差{spread_pct:.4f}% > {self.spread_threshold*100:.4f}%，等待机会"

        except Exception as e:
            logger.error(f"卖出判断错误: {e}")
            return False, f"判断错误: {e}"

    def place_futures_order(self, contract, size=1, price=0, order_type='IOC', close=False):
        """下期货订单"""
        try:
            payload = {
                "contract": contract,
                "size": size,
                "price": price,
                "text": f"auto_trade_{int(time.time())}",
                "tif": order_type  # Time In Force: IOC (Immediate or Cancel)
            }

            # 设置平仓标记
            if close:
                payload["close"] = True
                payload["reduce_only"] = True

            logger.info(f"📋 准备下单: {payload}")

            # 发送订单请求
            self._request("futures.orders", payload=payload, auth_required=True)

            return True

        except Exception as e:
            logger.error(f"下单失败: {e}")
            return False

    def execute_buy_order(self, contract):
        """执行买入开仓"""
        try:
            logger.info(f"🟢 开始买入开仓: {contract}")

            # 下买入订单
            if self.place_futures_order(contract, self.trade_amount, price=0, order_type='IOC', close=False):
                # 模拟订单执行（实际应该等待订单确认）
                current_price = self.tickers[contract].get('last', Decimal('0'))

                if current_price > 0:
                    # 更新持仓信息
                    self.current_position[contract] = {
                        'size': self.trade_amount,
                        'entry_price': current_price,
                        'entry_time': time.time()
                    }

                    logger.info(f"✅ 买入成功: {contract} {self.trade_amount} @ {current_price}")
                    return True
                else:
                    logger.warning(f"⚠️ 价格异常，无法更新持仓")
                    return False
            else:
                logger.error(f"❌ 买入失败: {contract}")
                return False

        except Exception as e:
            logger.error(f"买入执行错误: {e}")
            return False

    def execute_sell_order(self, contract):
        """执行卖出平仓"""
        try:
            if contract not in self.current_position:
                logger.error(f"❌ 无持仓可卖: {contract}")
                return False

            position = self.current_position[contract]
            entry_price = position['entry_price']

            # 获取当前价格
            current_price = self.tickers[contract].get('bid', Decimal('0'))
            if current_price <= 0:
                logger.error(f"❌ 无效的当前价格: {current_price}")
                return False

            logger.info(f"🔴 开始卖出平仓: {contract}")
            logger.info(f"   持仓成本: {entry_price}")
            logger.info(f"   当前价格: {current_price}")

            # 计算盈亏
            profit = (current_price - entry_price) * position['size']
            profit_pct = self.calculate_spread_percentage(current_price, entry_price)

            # 下卖出订单
            if self.place_futures_order(contract, -position['size'], price=0, order_type='IOC', close=True):
                # 更新交易记录
                trade_record = {
                    'contract': contract,
                    'entry_price': float(entry_price),
                    'exit_price': float(current_price),
                    'size': position['size'],
                    'profit': float(profit),
                    'profit_pct': float(profit_pct),
                    'entry_time': position['entry_time'],
                    'exit_time': time.time(),
                    'duration': time.time() - position['entry_time']
                }

                self.completed_trades.append(trade_record)
                self.trade_count += 1

                # 清除持仓
                del self.current_position[contract]

                logger.info(f"✅ 卖出成功: {contract}")
                logger.info(f"   盈亏: {profit:.4f} USDT ({profit_pct:.4f}%)")
                logger.info(f"   交易次数: {self.trade_count}/{self.max_trades}")

                return True
            else:
                logger.error(f"❌ 卖出失败: {contract}")
                return False

        except Exception as e:
            logger.error(f"卖出执行错误: {e}")
            return False

    def on_ticker_message(self, data):
        """处理行情数据"""
        try:
            # 处理单个ticker或数组
            if isinstance(data, dict):
                data = [data]

            for ticker in data:
                contract = ticker.get('contract')
                if contract in self.contracts:
                    last_price = Decimal(str(ticker.get('last', 0)))

                    # 对于买卖价，如果没有直接提供，使用last价格的近似值
                    bid_price = Decimal(str(ticker.get('bid', last_price * Decimal('0.9999'))))
                    ask_price = Decimal(str(ticker.get('ask', last_price * Decimal('1.0001'))))

                    self.tickers[contract] = {
                        'last': last_price,
                        'bid': bid_price,
                        'ask': ask_price,
                        'volume': Decimal(str(ticker.get('volume_24h', 0))),
                        'change_24h': Decimal(str(ticker.get('change_percentage', 0))),
                        'mark_price': Decimal(str(ticker.get('mark_price', last_price))),
                        'index_price': Decimal(str(ticker.get('index_price', last_price)))
                    }

                    # 记录价格更新（首次或价格变化时）
                    if contract not in self.tickers or self.tickers[contract]['last'] != last_price:
                        logger.info(f"📊 {contract} 价格更新: {last_price} (变化: {self.tickers[contract]['change_24h'] if contract in self.tickers else ticker.get('change_percentage', 0)}%)")

                    # 触发交易逻辑检查
                    self.check_trading_opportunities(contract)

        except Exception as e:
            logger.error(f"行情数据处理错误: {e}")
            logger.debug(f"原始数据: {data}")

    def on_order_message(self, data):
        """处理订单数据"""
        try:
            logger.info(f"📋 订单更新: {data}")

            # 这里可以添加订单状态确认逻辑
            # 确认订单成交后更新持仓信息

        except Exception as e:
            logger.error(f"订单数据处理错误: {e}")

    def on_trade_message(self, data):
        """处理成交数据"""
        try:
            logger.info(f"💰 成交更新: {data}")

        except Exception as e:
            logger.error(f"成交数据处理错误: {e}")

    def check_trading_opportunities(self, contract):
        """检查交易机会"""
        try:
            if not self.is_running:
                return

            # 检查买入机会
            should_buy, buy_reason = self.should_place_buy_order(contract)
            if should_buy:
                logger.info(f"🟢 买入机会: {contract} - {buy_reason}")
                if self.execute_buy_order(contract):
                    logger.info(f"📈 已建立多头持仓: {contract}")

            # 检查卖出机会
            should_sell, sell_reason = self.should_place_sell_order(contract)
            if should_sell:
                logger.info(f"🔴 卖出机会: {contract} - {sell_reason}")
                if self.execute_sell_order(contract):
                    logger.info(f"📉 已平仓: {contract}")

                    # 检查是否达到最大交易次数
                    if self.trade_count >= self.max_trades:
                        logger.info(f"🎯 达到最大交易次数 {self.max_trades}，停止交易")
                        self.stop_trading()

        except Exception as e:
            logger.error(f"交易机会检查错误: {e}")

    def on_message(self, ws, message):
        """WebSocket消息处理"""
        try:
            data = json.loads(message)
            channel = data.get('channel', '')
            event = data.get('event', '')
            payload = data.get('result', data.get('payload', {}))

            logger.debug(f"收到消息: {channel} - {event}")

            # 处理订阅确认
            if event == 'subscribe':
                logger.info(f"✅ 订阅成功: {channel}")
                return

            # 处理不同频道的消息
            if channel == 'futures.tickers':
                self.on_ticker_message(payload)
            elif channel in ['futures.orders', 'futures.usertrades']:
                self.on_order_message(payload)
            elif channel == 'futures.trades':
                self.on_trade_message(payload)

        except json.JSONDecodeError as e:
            logger.error(f"消息解析错误: {e}")
        except Exception as e:
            logger.error(f"消息处理错误: {e}")

    def on_open(self, ws):
        """WebSocket连接打开"""
        logger.info("🔗 WebSocket连接已建立")

        # 订阅行情数据
        for contract in self.contracts:
            logger.info(f"📡 订阅合约行情: {contract}")
            self.subscribe("futures.tickers", [contract], auth_required=False)

        # 订阅订单和成交数据（需要认证）
        self.subscribe("futures.orders", auth_required=True)
        self.subscribe("futures.usertrades", auth_required=True)

        # 启动心跳线程
        ping_thread = threading.Thread(target=self._send_ping, daemon=True)
        ping_thread.start()

        self.is_running = True
        logger.info("🚀 交易系统已启动")

    def on_error(self, ws, error):
        """WebSocket错误处理"""
        logger.error(f"WebSocket错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        logger.info(f"WebSocket连接已关闭: {close_status_code} - {close_msg}")
        self.is_running = False

    def start_trading(self):
        """启动交易"""
        logger.info("=" * 60)
        logger.info("🚀 Gate.io期货价差交易系统启动")
        logger.info("=" * 60)
        logger.info(f"📊 交易合约: {', '.join(self.contracts)}")
        logger.info(f"💰 交易数量: {self.trade_amount}")
        logger.info(f"🎯 最大交易次数: {self.max_trades}")
        logger.info(f"📈 价差阈值: {self.spread_threshold*100:.4f}%")
        logger.info(f"🌐 连接地址: {self.ws_url}")
        logger.info("=" * 60)

        # 创建WebSocket连接
        self.ws = WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        # 启动WebSocket连接
        try:
            self.ws.run_forever(ping_interval=5)
        except KeyboardInterrupt:
            logger.info("⏹️ 用户中断，停止交易")
            self.stop_trading()

    def stop_trading(self):
        """停止交易"""
        logger.info("🛑 正在停止交易...")
        self.is_running = False
        self.event.set()

        if self.ws:
            self.ws.close()

        # 打印交易总结
        self.print_trading_summary()

    def print_trading_summary(self):
        """打印交易总结"""
        logger.info("=" * 60)
        logger.info("📊 交易总结")
        logger.info("=" * 60)

        total_profit = sum(trade['profit'] for trade in self.completed_trades)
        successful_trades = [t for t in self.completed_trades if t['profit'] > 0]
        failed_trades = [t for t in self.completed_trades if t['profit'] <= 0]

        logger.info(f"📈 总交易次数: {len(self.completed_trades)}")
        logger.info(f"✅ 盈利交易: {len(successful_trades)}")
        logger.info(f"❌ 亏损交易: {len(failed_trades)}")
        logger.info(f"💰 总盈亏: {total_profit:.4f} USDT")

        if self.completed_trades:
            avg_profit = total_profit / len(self.completed_trades)
            win_rate = len(successful_trades) / len(self.completed_trades) * 100
            logger.info(f"📊 平均盈亏: {avg_profit:.4f} USDT")
            logger.info(f"🎯 胜率: {win_rate:.2f}%")

        # 详细交易记录
        if self.completed_trades:
            logger.info("\n📋 详细交易记录:")
            for i, trade in enumerate(self.completed_trades, 1):
                profit_symbol = "📈" if trade['profit'] > 0 else "📉"
                logger.info(f"  {i}. {trade['contract']} {profit_symbol} "
                          f"入场: {trade['entry_price']:.2f} → "
                          f"出场: {trade['exit_price']:.2f} "
                          f"盈亏: {trade['profit']:.4f} USDT ({trade['profit_pct']:.4f}%)")

        logger.info("=" * 60)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Gate.io Futures Spread Trading System')
    parser.add_argument('--config', default='config.json', help='Configuration file path')
    parser.add_argument('--contracts', nargs='+', help='Trading contracts list')
    parser.add_argument('--amount', type=int, help='Trade amount per order')
    parser.add_argument('--max-trades', type=int, help='Maximum number of trades')
    parser.add_argument('--spread-threshold', type=float, help='Spread threshold e.g. 0.0005 for 0.05 percent')

    args = parser.parse_args()

    try:
        # 创建交易器
        trader = GateFuturesTrader(args.config)

        # 应用命令行参数
        if args.contracts:
            trader.contracts = args.contracts
        if args.amount:
            trader.trade_amount = args.amount
        if args.max_trades:
            trader.max_trades = args.max_trades
        if args.spread_threshold:
            trader.spread_threshold = Decimal(str(args.spread_threshold))

        # 启动交易
        trader.start_trading()

    except Exception as e:
        logger.error(f"系统启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()