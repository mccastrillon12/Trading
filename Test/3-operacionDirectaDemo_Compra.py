import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

# === PARÁMETROS ===
symbol = "EURUSD"
risk_pct = 0.01  # Porcentaje de riesgo por operación

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

capital = account.balance  # Usa .balance si no quieres contar operaciones abiertas
risk_usd = capital * risk_pct
print(f"💰 Capital actual (equity): {capital:.2f} USD")
print(f"🔒 Riesgo por operación ({risk_pct*100}%): {risk_usd:.2f} USD")

# === OBTENER LA ÚLTIMA VELA CERRADA (completa) ===
velas = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 1, 1)  # Posición 1 para obtener la vela anterior
if velas is None or len(velas) < 1:
    print("⚠️ No se pudo obtener la vela cerrada anterior.")
    mt5.shutdown()
    quit()

vela_anterior = velas[0]
sl = vela_anterior['open']  # SL al precio de apertura de la vela anterior

# === PRECIO ACTUAL ===
tick = mt5.symbol_info_tick(symbol)
ask = tick.ask if tick else None

if ask is None:
    print("❌ No se pudo obtener el precio actual.")
    mt5.shutdown()
    quit()

# === CÁLCULOS ===
riesgo = abs(ask - sl)
tp = ask + 2 * riesgo
sl_pips = riesgo * 10000
pip_value = 10  # Para EURUSD 1 lote = $10/pip
lote = round(risk_usd / (sl_pips * pip_value), 2)
lote = max(0.01, min(lote, 10.0))  # Control de riesgo: mínimo 0.01, máximo 10 lotes

print(f"🟢 Enviando compra con precio actual: {ask}, SL: {sl}, TP: {tp}, lote: {lote}")

# === ORDEN DE COMPRA ===
orden = mt5.order_send({
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lote,
    "type": mt5.ORDER_TYPE_BUY,
    "price": ask,
    "sl": sl,
    "tp": tp,
    "deviation": 10,
    "magic": 999999,
    "comment": "AutoBuy",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC
})

# === RESULTADO ===
if orden is None:
    print("❌ mt5.order_send retornó None.")
    print("📛 Error:", mt5.last_error())
elif orden.retcode != mt5.TRADE_RETCODE_DONE:
    print(f"❌ Error al enviar orden: {orden.retcode}")
    print("📛 Error:", mt5.last_error())
else:
    print(f"✅ Orden de COMPRA ejecutada:\n   Precio: {ask}\n   SL: {sl}\n   TP: {tp}\n   Lote: {lote}")

mt5.shutdown()
