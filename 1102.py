import requests
import time
import json

# Bybit V5 API URL
# V5 行情接口

# Get Tickers 
# Query for the latest price snapshot, best bid/ask price, and trading volume in the last 24 hours.
# 获取股票代码
# 查询最新价格快照、最佳买卖价格以及过去 24 小时内的交易量

# 枚举定义：https://bybit-exchange.github.io/docs/v5/enum
# Category: https://bybit-exchange.github.io/docs/v5/enum#category
# Symbol: https://bybit-exchange.github.io/docs/v5/enum#symbol

TICKER_URL = "https://api.bybit.com/v5/market/tickers"


# 要查询的合约信息
# category=linear 表示永续合约/交割合约
    # 其他可选值：option, inverse, spot
    # linear： USDT perpetual, USDT Futures and USDC contract, including USDC perp, USDC futures
    # inverse： Inverse contract, including Inverse perp, Inverse futures
# symbol=BTCUSDT 表示 BTC/USDT 永续合约

PARAMS = {
    "category": "linear",
    "symbol": "BTCUSDT"
}

def get_bybit_price():
    """
    获取并打印 Bybit BTC/USDT 永续合约的买一价和卖一价
    """
    try:
        # 发送 GET 请求 
        # 请求 URL: https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT
        response = requests.get(url=TICKER_URL, params=PARAMS) 
        response.raise_for_status()  # 如果请求失败 (非 200 状态码), 抛出异常

        # 解析 JSON 响应
        data = response.json()   # 解析 JSON 响应, 返回一个字典, 
        # 字典的键是 "retCode", "retMsg", "result", "retExtInfo", "time"
        # 列表的元素是字典, 字典的键是 （以下只展示几个，后面展示了完整的json输出）
        # "symbol", "lastPrice", "bid1Price", "ask1Price", 
        # "bid1Size", "ask1Size", "bid1Time", "ask1Time", "bid1Volume", "ask1Volume"

        # 检查 Bybit API 返回状态
        if data.get("retCode") == 0 and data.get("retMsg") == "OK":
            # 提取结果列表中的第一个元素 (即我们查询的 BTCUSDT)
            ticker_info = data.get("result", {}).get("list", [])

            if not ticker_info:
                print("错误：API 返回了空的结果列表。")
                return

            # 提取买一价 (bid1Price) 和 卖一价 (ask1Price)
            bid1_price = ticker_info[0].get("bid1Price")
            ask1_price = ticker_info[0].get("ask1Price")

            if bid1_price and ask1_price:
                # 获取当前时间
                current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                # 打印到控制台
                print(f"--- {current_time} ---")
                print(f"合约: BTC/USDT 永续合约")
                print(f"买一价 (Bid 1): {bid1_price}")
                print(f"卖一价 (Ask 1): {ask1_price}\n")
            else:
                print("错误：未能在 API 响应中找到买一价或卖一价。")

        else:
            print(f"API 返回错误: {data.get('retMsg')}")

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response headers: {e.response.headers}")
            try:
                print(f"Response text: {e.response.text}")
            except Exception as text_e:
                print(f"Could not print response text: {text_e}")
    except json.JSONDecodeError:
        print("错误：解析 API 响应失败，返回的可能不是有效的 JSON。")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    print("开始获取 Bybit 实时价格 (按 Ctrl+C 停止)...")

    # 无限循环，以实现“实时”
    while True:
        get_bybit_price()
        # 每 2 秒刷新一次
        # 注意：API 有频率限制，请勿设置过短的时间
        time.sleep(2)

# ------------------------------
############ 输出示例 ############
# ------------------------------

# 开始获取 Bybit 实时价格 (按 Ctrl+C 停止)...
# --- 2025-11-04 10:50:24 ---
# 合约: BTC/USDT 永续合约
# 买一价 (Bid 1): 106864.40
# 卖一价 (Ask 1): 106864.50

# --- 2025-11-04 10:50:26 ---
# 合约: BTC/USDT 永续合约
# 买一价 (Bid 1): 106862.60
# 卖一价 (Ask 1): 106862.70

# --- 2025-11-04 10:50:28 ---
# 合约: BTC/USDT 永续合约
# 买一价 (Bid 1): 106862.60
# 卖一价 (Ask 1): 106862.70

# --- 2025-11-04 10:50:31 ---
# 合约: BTC/USDT 永续合约
# 买一价 (Bid 1): 106846.40
# 卖一价 (Ask 1): 106846.50

# --- 2025-11-04 10:50:33 ---
# 合约: BTC/USDT 永续合约
# 买一价 (Bid 1): 106848.50
# 卖一价 (Ask 1): 106848.60


# https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT

# API 返回的 JSON 响应示例
# {"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[{"symbol":"BTCUSDT","lastPrice":"107089.20","indexPrice":"107135.27","markPrice":"107084.00","prevPrice24h":"109740.00","price24hPcnt":"-0.024155","highPrice24h":"109833.00","lowPrice24h":"105178.20","prevPrice1h":"106668.50","openInterest":"50923.331","openInterestValue":"5453073976.80","turnover24h":"10983940889.6900","volume24h":"102583.4090","fundingRate":"0.00001938","nextFundingTime":"1762243200000","predictedDeliveryPrice":"","basisRate":"","deliveryFeeRate":"","deliveryTime":"0","ask1Size":"0.012","bid1Price":"107089.10","ask1Price":"107089.20","bid1Size":"2.529","basis":"","preOpenPrice":"","preQty":"","curPreListingPhase":"","fundingIntervalHour":"8","basisRateYear":"","fundingCap":"0.005"}]},"retExtInfo":{},"time":1762220791908}

# 响应结果示例 json 格式化输出
# {
#     "retCode": 0,
#     "retMsg": "OK",
#     "result": {
#         "category": "linear",
#         "list": [
#             {
#                 "symbol": "BTCUSDT",
#                 "lastPrice": "107089.20",
#                 "indexPrice": "107135.27",
#                 "markPrice": "107084.00",
#                 "prevPrice24h": "109740.00",
#                 "price24hPcnt": "-0.024155",
#                 "highPrice24h": "109833.00",
#                 "lowPrice24h": "105178.20",
#                 "prevPrice1h": "106668.50",
#                 "openInterest": "50923.331",
#                 "openInterestValue": "5453073976.80",
#                 "turnover24h": "10983940889.6900",
#                 "volume24h": "102583.4090",
#                 "fundingRate": "0.00001938",
#                 "nextFundingTime": "1762243200000",
#                 "predictedDeliveryPrice": "",
#                 "basisRate": "",
#                 "deliveryFeeRate": "",
#                 "deliveryTime": "0",
#                 "ask1Size": "0.012",
#                 "bid1Price": "107089.10",
#                 "ask1Price": "107089.20",
#                 "bid1Size": "2.529",
#                 "basis": "",
#                 "preOpenPrice": "",
#                 "preQty": "",
#                 "curPreListingPhase": "",
#                 "fundingIntervalHour": "8",
#                 "basisRateYear": "",
#                 "fundingCap": "0.005"
#             }
#         ]
#     },
#     "retExtInfo": {

#     },
#     "time": 1762220791908
# }