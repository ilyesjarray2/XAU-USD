import MetaTrader5 as mt5
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import time
from datetime import datetime, timedelta

# --- NEYDRA CONFIGURATION ---
SYMBOL = "XAUUSD"
RISK_FACTOR = 0.1437
MAGIC_NUMBER = 1437001
SCALPING_TP = 15
SCALPING_SL = 10

# --- MYFXBOOK CREDENTIALS ---
MFB_EMAIL = "jarrayilyes18@gmail.com"     # ضع إيميلك هنا
MFB_PASS = "mQcwv94dEJ@PbiK"               # ضع كلمة السر هنا
MFB_ACC_ID = "980046"                    # رقم حسابك في Myfxbook (Account ID)

class MyfxbookBridge:
    def __init__(self):
        self.base_url = "https://www.myfxbook.com/api"
        self.session = None
        self.last_login = 0
    
    def login(self):
        # تجديد الجلسة كل 10 دقائق لضمان عدم انقطاع الاتصال
        if self.session and (time.time() - self.last_login < 600):
            return self.session
        try:
            url = f"{self.base_url}/login.json?email={MFB_EMAIL}&password={MFB_PASS}"
            resp = requests.get(url).json()
            if not resp['error']:
                self.session = resp['session']
                self.last_login = time.time()
                print(f"✅ MFB Session Active: {self.session}")
                return self.session
        except Exception as e:
            print(f"❌ MFB Login Error: {e}")
        return None

    def get_all_data(self):
        s = self.login()
        if not s: return {"error": "No Session"}
        
        # تواريخ ديناميكية (آخر 30 يوم)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        data = {}

        # 1. Sentiment (Global & Country)
        try:
            sent = requests.get(f"{self.base_url}/get-community-sentiment.json?session={s}").json()
            # البحث عن الذهب
            xau_sent = next((item for item in sent.get('symbols', []) if item['name'] == 'XAUUSD'), None)
            data['sentiment_global'] = xau_sent
            
            # Sentiment by Country (مثال لزوج EURUSD أو XAUUSD حسب التوفر)
            country = requests.get(f"{self.base_url}/get-community-outlook-by-country.json?session={s}&symbol={SYMBOL}").json()
            data['sentiment_country'] = country.get('countries', [])
        except: data['sentiment_error'] = True

        # 2. Account Performance (Gain, Daily Gain, Data Daily)
        try:
            # Gain
            gain = requests.get(f"{self.base_url}/get-gain.json?session={s}&id={MFB_ACC_ID}&start={start_date}&end={end_date}").json()
            data['gain_period'] = gain.get('value', 0)

            # Daily Gain Chart Data
            daily_gain = requests.get(f"{self.base_url}/get-daily-gain.json?session={s}&id={MFB_ACC_ID}&start={start_date}&end={end_date}").json()
            data['daily_gain_chart'] = daily_gain.get('dailyGain', [])

            # Detailed Daily Data
            daily_data = requests.get(f"{self.base_url}/get-data-daily.json?session={s}&id={MFB_ACC_ID}&start={start_date}&end={end_date}").json()
            data['data_daily'] = daily_data.get('dataDaily', [])
        except: data['perf_error'] = True

        # 3. Trades & Orders (Live & History)
        try:
            open_trades = requests.get(f"{self.base_url}/get-open-trades.json?session={s}&id={MFB_ACC_ID}").json()
            data['open_trades'] = open_trades.get('openTrades', [])

            open_orders = requests.get(f"{self.base_url}/get-open-orders.json?session={s}&id={MFB_ACC_ID}").json()
            data['open_orders'] = open_orders.get('openOrders', [])

            history = requests.get(f"{self.base_url}/get-history.json?session={s}&id={MFB_ACC_ID}").json()
            data['history'] = history.get('history', [])
        except: data['trade_error'] = True
        
        # 4. Widget URL Construction (No API call needed, just URL generation)
        # Custom Widget Parameters: Dark theme style
        widget_url = f"https://widgets.myfxbook.com/api/get-custom-widget.png?session={s}&id={MFB_ACC_ID}&width=350&height=200&bart=1&linet=0&bgColor=050505&gridColor=333333&lineColor=39FF14&barColor=FF0039&fontColor=FFFFFF&title=NEYDRA&titles=14&chartbgc=101010"
        data['widget_url'] = widget_url

        return data

# --- FASTAPI SETUP ---
app = FastAPI(title="NEYDRA SYSTEM V4")
mfb = MyfxbookBridge()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if not mt5.initialize(): print("MT5 Init Failed")
mt5.symbol_select(SYMBOL, True)

# --- ENDPOINTS ---

@app.get("/scan")
async def scan_market():
    # Local Scalping Logic (Fast)
    mt5.market_book_add(SYMBOL)
    time.sleep(0.2)
    items = mt5.market_book_get(SYMBOL)
    mt5.market_book_release(SYMBOL)
    
    direction = "WAIT"
    imbalance = 0
    if items:
        bid = sum(i.volume for i in items if i.type in [mt5.BOOK_TYPE_BUY, mt5.BOOK_TYPE_BUY_MARKET])
        ask = sum(i.volume for i in items if i.type in [mt5.BOOK_TYPE_SELL, mt5.BOOK_TYPE_SELL_MARKET])
        total = bid + ask
        if total > 0: imbalance = (bid - ask) / total
        if imbalance > 0.05: direction = "BUY"
        elif imbalance < -0.05: direction = "SELL"

    acc = mt5.account_info()
    lot = round((acc.balance * RISK_FACTOR / 100) * 0.1, 2)
    
    return {
        "action": direction,
        "confidence": round(abs(imbalance)*100+60, 2),
        "lot_size": max(lot, 0.01),
        "price": mt5.symbol_info_tick(SYMBOL).ask if direction == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
    }

@app.get("/execute")
async def execute_trade(action: str, lot: float):
    tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    price = tick.ask if action == "BUY" else tick.bid
    sl = price - (SCALPING_SL * 10 * sym.point) if action == "BUY" else price + (SCALPING_SL * 10 * sym.point)
    tp = price + (SCALPING_TP * 10 * sym.point) if action == "BUY" else price - (SCALPING_TP * 10 * sym.point)
    
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price, "sl": sl, "tp": tp, "magic": MAGIC_NUMBER,
        "comment": "NEYDRA V4", "type_filling": mt5.ORDER_FILLING_IOC
    }
    res = mt5.order_send(req)
    return {"status": "DONE" if res.retcode == mt5.TRADE_RETCODE_DONE else "FAIL", "ticket": res.order}

@app.get("/mfb-data")
async def get_myfxbook_stats():
    # Global Intelligence Logic (Slower, rich data)
    return mfb.get_all_data()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
    
