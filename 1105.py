import requests
import time
import json
import logging
from collections import deque
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, time as dt_time

# --- 配置区 ---

# Bybit V5 API URL
TICKER_URL = "https://api.bybit.com/v5/market/tickers"
PARAMS = {
    "category": "linear",
    "symbol": "BTCUSDT"
}

# 风险控制参数
PRICE_HISTORY_SECONDS = 3  # 监控几秒内的价格
RISK_DROP_PERCENTAGE = 0.02 # 跌幅百分比 (2%)

# --- 模拟数据配置 ---
# 将此设置为 True 来测试风控逻辑，设置为 False 来使用 Bybit 真实数据
USE_MOCK_DATA = False

# 模拟价格序列 (t=0, t=1, t=2, t=3, t=4, t=5...)
# 在 t=4 时，价格从 99.9 (t=2) 跌到 97.0，(99.9 - 97.0) / 99.9 = 2.9% > 2%
# 这将触发风控暂停
mock_price_iterator = iter([
    100.0,  # t=0, history=[100.0]
    100.1,  # t=1, history=[100.0, 100.1]
    99.9,   # t=2, history=[100.0, 100.1, 99.9], 3s check (100.0 -> 99.9), OK
    99.8,   # t=3, history=[100.1, 99.9, 99.8], 3s check (100.1 -> 99.8), OK
    97.0,   # t=4, history=[99.9, 99.8, 97.0], 3s check (99.9 -> 97.0), DROP >= 2% -> PAUSE!
    97.1,   # t=5, (脚本已暂停, 不会再获取)
    97.2,   # t=6, (脚本已暂停)
])

# --- 全局状态变量 ---
is_running = False  # 定时器开关 (9:00-18:00)
is_paused_due_to_risk = False  # 风控开关
price_history = deque(maxlen=PRICE_HISTORY_SECONDS)

# --- 日志配置 ---
# 减少 APScheduler 的日志刷屏
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logging.getLogger('apscheduler').setLevel(logging.WARNING)


def get_bybit_last_price():
    """
    获取 Bybit BTCUSDT 最新成交价。
    如果 USE_MOCK_DATA 为 True, 则返回模拟数据。
    """
    global mock_price_iterator
    
    # 模拟数据模式
    if USE_MOCK_DATA:
        try:
            mock_price = next(mock_price_iterator)
            return mock_price
        except StopIteration:
            print("模拟数据已用完。")
            return None

    # 真实 API 请求
    try:
        # 设置一个较短的超时时间，例如 3 秒
        response = requests.get(url=TICKER_URL, params=PARAMS, timeout=3)
        response.raise_for_status()  # 处理 HTTP 错误
        data = response.json()

        if data.get("retCode") == 0 and data.get("retMsg") == "OK":
            ticker_list = data.get("result", {}).get("list", [])
            if ticker_list:
                last_price_str = ticker_list[0].get("lastPrice")
                if last_price_str:
                    return float(last_price_str)
            print("错误：API 响应中未找到 'list' 或 'lastPrice'。")
            return None
        else:
            print(f"API 返回错误: {data.get('retMsg')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"网络或请求错误: {e}")
        return None
    except json.JSONDecodeError:
        print("错误：解析 API 响应失败。")
        return None
    except Exception as e:
        print(f"获取价格时发生未知错误: {e}")
        return None

# --- 核心风控逻辑 ---
def check_price_and_risk():
    """
    获取当前价格，并检查是否触发风控。
    此函数应每 1 秒执行一次。
    """
    global is_paused_due_to_risk, price_history

    current_price = get_bybit_last_price()
    
    if current_price is None:
        print(f"[{datetime.now().strftime('%T')}] 获取价格失败，跳过此次检查。")
        return

    print(f"[{datetime.now().strftime('%T')}] 获取价格: {current_price:<8}")
    price_history.append(current_price)

    # 检查风险：我们是否已有足够的数据 (例如 3 秒)
    if len(price_history) == PRICE_HISTORY_SECONDS:
        price_3s_ago = price_history[0]
        price_now = price_history[-1] # 即 current_price

        # 检查价格是否下跌
        if price_now < price_3s_ago:
            percentage_drop = (price_3s_ago - price_now) / price_3s_ago
            
            # 调试信息 (可以注释掉)
            # print(f"  [DEBUG] 3s 前: {price_3s_ago}, 现在: {price_now}, 跌幅: {percentage_drop*100:.2f}%")

            if percentage_drop >= RISK_DROP_PERCENTAGE:
                # 触发风控！
                is_paused_due_to_risk = True
                print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                print(f"[{datetime.now().strftime('%T')}] !! 风险警告：暂停运行 !!")
                print(f"  价格在 {PRICE_HISTORY_SECONDS} 秒内从 {price_3s_ago} 跌至 {price_now}")
                print(f"  跌幅: {percentage_drop*100:.2f}% (阈值: {RISK_DROP_PERCENTAGE*100}%)")
                print("  脚本已暂停，将在明天 9:00 自动重置。")
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")


# --- 定时任务函数 ---
def start_monitoring():
    """APScheduler 任务：早上 9 点启动"""
    global is_running, is_paused_due_to_risk, price_history
    is_running = True
    is_paused_due_to_risk = False # 每天启动时重置风控开关
    price_history.clear()         # 清空昨天的价格历史
    print(f"\n--- {datetime.now()} ---")
    print("定时任务：脚本已启动 (9:00 AM)。风控已重置。")
    print("-------------------------------------------\n")

def stop_monitoring():
    """APScheduler 任务：下午 18 点停止"""
    global is_running
    is_running = False
    print(f"\n--- {datetime.now()} ---")
    print("定时任务：脚本已停止 (18:00 PM)。")
    print("-------------------------------------------\n")


# --- 主程序入口 ---
if __name__ == "__main__":
    # 1. 配置 APScheduler
    scheduler = BackgroundScheduler()
    # 每天 9:00:00 运行 start_monitoring
    scheduler.add_job(start_monitoring, 'cron', hour=9, minute=0, second=0)
    # 每天 18:00:00 运行 stop_monitoring
    scheduler.add_job(stop_monitoring, 'cron', hour=18, minute=0, second=0)
    scheduler.start()
    
    print(f"脚本启动于 {datetime.now()}")
    print(f"定时任务已设置：每天 9:00 启动，18:00 停止。")
    if USE_MOCK_DATA:
        print("!!! 警告：正在使用模拟数据模式 (USE_MOCK_DATA=True) !!!")
    
    # 2. 检查初始状态
    # (如果脚本在 9:00 到 18:00 之间启动，立即设为 is_running=True)
    current_time = datetime.now().time()
    if dt_time(9, 0) <= current_time < dt_time(18, 0):
        print("在活动时间窗口内启动，立即开始监控。")
        is_running = True
    else:
        print("在活动时间窗口外启动，等待 9:00 AM...")

    # 3. 主循环 (每秒 1 次)
    try:
        while True:
            if is_running and not is_paused_due_to_risk:
                # *** 核心逻辑 ***
                # 这是脚本的“活动”状态
                # (在这里可以添加您的真实交易或监控逻辑)
                check_price_and_risk()
            
            elif is_paused_due_to_risk:
                # 风控已触发，打印等待信息 (每 10 秒)
                if datetime.now().second % 10 == 0:
                    print(f"[{datetime.now().strftime('%T')}] (已暂停 - 等待风控重置)")
            
            elif not is_running:
                # 定时器已关闭 (18:00 之后)，打印等待信息 (每 10 秒)
                if datetime.now().second % 10 == 0:
                    print(f"[{datetime.now().strftime('%T')}] (已停止 - 等待 9:00 启动)")
            
            # 轮询间隔：1 秒
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，正在关闭脚本...")
        scheduler.shutdown()
        print("APScheduler 已关闭。再见。")