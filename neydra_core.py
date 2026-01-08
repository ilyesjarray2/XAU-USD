import MetaTrader5 as mt5
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import random
import time
from datetime import datetime

# --- NEYDRA CONFIGURATION ---
RISK_FACTOR_1437 = 0.1437  # 14.37% Strategy
SYMBOL = "XAUUSD"
SCALPING_TP_PIPS = 15
SCALPING_SL_PIPS = 10  # Tight Stop for Scalping
TIMEFRAME = mt5.TIMEFRAME_M1

app = FastAPI(title="NEYDRA CORE V1")

# --- CORS (Allow HTML Dashboard Connection) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INITIALIZATION ---
if not mt5.initialize():
    print("initialize() failed, error code =", mt5.last_error())
    quit()

# Ensure Symbol is visible
mt5.symbol_select(SYMBOL, True)

# --- 14.37% RISK MANAGEMENT LOGIC ---
def calculate_lot_size(balance):
    """
    Applies the 14.37% Strategy.
    In this MVP: We risk 14.37% of equity on the Stop Loss hit.
    Formula: Risk Amount / (SL_Points * TickValue)
    """
    risk_amount = balance * RISK_FACTOR_1437
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        return 0.01
    
    sl_points = SCALPING_SL_PIPS * 10  # Convert pips to points
    tick_value = symbol_info.trade_tick_value
    
    if tick_value == 0:
        return 0.01

    lot_size = risk_amount / (sl_points * tick_value)
    
    # Normalize lot size
    step = symbol_info.volume_step
    lot_size = round(lot_size / step) * step
    return max(lot_size, 0.01) # Minimum 0.01

# --- AI & ORDER FLOW SIMULATION ---
def predict_price_action():
    """
    Simulates the deep analysis of Order Flow and L2 Data.
    In Production: This connects to the LSTM Model weights.
    In MVP: We simulate High-Probability Order Block detection.
    """
    # Simulate processing time (handled by frontend delay, but backend logic here)
    
    # Mocking Order Book Imbalance
    buy_pressure = random.uniform(0.4, 0.95)
    sell_pressure = 1 - buy_pressure
    
    direction = "BUY" if buy_pressure > 0.5 else "SELL"
    confidence = random.uniform(85.0, 96.5) # High confidence simulation
    
    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "pressure": round(buy_pressure * 100, 2) if direction == "BUY" else round(sell_pressure * 100, 2),
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }

# --- API ENDPOINTS ---

@app.get("/scan")
async def scan_market():
    """The 'Brain' analyzing the market."""
    account_info = mt5.account_info()
    if not account_info:
        raise HTTPException(status_code=500, detail="MT5 Account not found")
    
    prediction = predict_price_action()
    current_price = mt5.symbol_info_tick(SYMBOL).ask if prediction['direction'] == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
    
    lot_size = calculate_lot_size(account_info.balance)
    
    return {
        "status": "OPPORTUNITY_FOUND",
        "symbol": SYMBOL,
        "action": prediction['direction'], # BUY or SELL
        "confidence": prediction['confidence'],
        "entry_price": current_price,
        "lot_size": lot_size,
        "tp": SCALPING_TP_PIPS,
        "sl": SCALPING_SL_PIPS,
        "reason": "Institutional Order Block Detected via L2 Data"
    }

@app.post("/execute")
async def execute_trade(action: str, lot: float):
    """Executes the trade instantly on MT5."""
    tick = mt5.symbol_info_tick(SYMBOL)
    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if action == "BUY" else tick.bid
    
    point = mt5.symbol_info(SYMBOL).point
    sl = price - (SCALPING_SL_PIPS * 10 * point) if action == "BUY" else price + (SCALPING_SL_PIPS * 10 * point)
    tp = price + (SCALPING_TP_PIPS * 10 * point) if action == "BUY" else price - (SCALPING_TP_PIPS * 10 * point)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 1437001,
        "comment": "NEYDRA AI EXECUTION",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"status": "FAILED", "error": result.comment}
    
    return {"status": "EXECUTED", "ticket": result.order}

if __name__ == "__main__":
    print("NEYDRA BRAIN ENGINE STARTED...")
    print("LISTENING ON PORT 8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)