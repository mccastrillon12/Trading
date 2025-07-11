import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

# === PARÁMETROS ===
symbol = "EURUSD"
risk_pct = 0.01  # 1% de riesgo

# === CONEXIÓN ===
if not mt5.initialize():
    print("❌ No se pudo conectar a MT5", mt5.last_error())
    quit()
else:
    print("✅ Conectado a MetaTrader 5")

# === INFORMACIÓN DE CUENTA ===
account = mt5.account_info()
if account is None:
    print("❌ No se pudo obtener información de la cuenta.")
    mt5.shutdown()
    quit()

capital = account.balance
risk_usd = capital * risk_pct
print(f"💰 Capital: {capital:.2f}, Riesgo 1%: {risk_usd:.2f}")

# === OBTENER LA VELA CERRADA ANTERIOR ===
velas = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, 1)  # o TIMEFRAME_M1
if velas is None or len(velas) < 1:
    print("⚠️ No se pudo obtener la vela anterior.")
    mt5.shutdown()
    quit()
vela_anterior = velas[0]
open_anterior = vela_anterior['open']

# === PRECIO ACTUAL ===
tick = mt5.symbol_info_tick(symbol)
bid = tick.bid if tick else None
if bid is None:
    print("❌ No se pudo obtener el precio actual.")
    mt5.shutdown()
    quit()

# === INFO DEL SÍMBOLO ===
info = mt5.symbol_info(symbol)
if info is None or not info.visible:
    print("❌ Símbolo no habilitado.")
    mt5.shutdown()
    quit()

# === DISTANCIA DEL SL (basada en apertura de vela anterior)
pip_size = 0.0001  # para EURUSD
sl_distance = abs(bid - open_anterior)
sl_pips = sl_distance / pip_size
if sl_pips == 0:
    print("⚠️ SL en 0 pips. No se puede operar.")
    mt5.shutdown()
    quit()

# === CÁLCULO DEL LOTE ===
pip_value_per_lot = 10  # USD/pip por 1 lote
lot = risk_usd / (sl_pips * pip_value_per_lot)
lot = round(max(info.volume_min, min(lot, info.volume_max)), 2)

# === SL y TP
sl = bid + sl_distance  # SL por arriba
tp = bid - 2 * sl_distance  # TP por debajo

print(f"📊 SL: {sl:.5f}, TP: {tp:.5f}, SL pips: {sl_pips:.2f}, Lote: {lot}")

# === ENVÍO DE ORDEN
orden = mt5.order_send({
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lot,
    "type": mt5.ORDER_TYPE_SELL,
    "price": bid,
    "sl": sl,
    "tp": tp,
    "deviation": 10,
    "magic": 999999,
    "comment": "AutoSell",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC
})

if orden is None:
    print("❌ mt5.order_send retornó None.")
    print("📛 Error:", mt5.last_error())
elif orden.retcode != mt5.TRADE_RETCODE_DONE:
    print(f"❌ Error al enviar orden: {orden.retcode}")
    print("📛 Error:", mt5.last_error())
else:
    print(f"✅ VENTA ejecutada: Precio: {bid}, SL: {sl}, TP: {tp}, Lote: {lot}")

mt5.shutdown()
