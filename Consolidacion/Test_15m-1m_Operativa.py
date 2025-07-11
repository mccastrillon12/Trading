import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, timezone

symbol = "EURUSD"

# === CONEXIÓN INICIAL A MT5 ===
if not mt5.initialize():
    print("❌ No se pudo conectar a MT5")
    quit()

# === OBTENER HORA DEL SERVIDOR MT5 ===
tick = mt5.symbol_info_tick(symbol)
if tick is not None:
    hora_utc = datetime.fromtimestamp(tick.time, tz=timezone.utc)
  
    print(f"🕒 Hora del servidor MT5 (GMT+3): {hora_utc.strftime('%Y-%m-%d %H:%M:%S')}")
else:
    print("⚠️ No se pudo obtener la hora del servidor.")

# === FUNCIÓN PARA DETECTAR PIVOTES EN M1 ===
def obtener_ultimos_pivotes():
    rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 200)
    if rates_m1 is None or len(rates_m1) < 3:
        return None, None

    df = pd.DataFrame(rates_m1)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    pivotes_altos = []
    pivotes_bajos = []

    for i in range(1, len(df) - 1):
        if df.loc[i, 'high'] > df.loc[i - 1, 'high'] and df.loc[i, 'high'] > df.loc[i + 1, 'high']:
            pivotes_altos.append(df.loc[i, 'high'])
        if df.loc[i, 'low'] < df.loc[i - 1, 'low'] and df.loc[i, 'low'] < df.loc[i + 1, 'low']:
            pivotes_bajos.append(df.loc[i, 'low'])

    if not pivotes_altos or not pivotes_bajos:
        return None, None

    return pivotes_altos[-1], pivotes_bajos[-1]  # último alto y bajo

# === DETECTAR SOPORTE Y RESISTENCIA UNA SOLA VEZ ===
ultimo_alto, ultimo_bajo = obtener_ultimos_pivotes()
if ultimo_alto is None or ultimo_bajo is None:
    print("❌ No se pudieron detectar los pivotes")
    mt5.shutdown()
    quit()

print("🟣 Niveles detectados:")
print(f"resistencia: {ultimo_alto:.5f}")
print(f"soporte    : {ultimo_bajo:.5f}")

# === CIERRE DE CONEXIÓN A MT5 ===
mt5.shutdown()
