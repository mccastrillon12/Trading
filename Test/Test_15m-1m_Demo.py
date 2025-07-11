import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta

symbol = "EURUSD"

# === CONEXIÓN INICIAL A MT5 ===
if not mt5.initialize():
    print("❌ No se pudo conectar a MT5")
    quit()

# === FUNCIÓN PARA DETECTAR PIVOTES EN M15 (solo una vez) ===
def obtener_ultimos_pivotes():
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 200)
    if rates_m15 is None or len(rates_m15) < 3:
        return None, None

    df = pd.DataFrame(rates_m15)
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
print(f"soporte    : {ultimo_bajo:.5f}")
print(f"resistencia: {ultimo_alto:.5f}")

ultimo_chequeo = None
ultimo_mensaje_info = datetime.now() - timedelta(minutes=15)

# === LOOP PARA MONITOREO DE ROMPIMIENTO ===
while True:
    if not mt5.initialize():
        print("❌ Reconexión fallida a MT5")
        time.sleep(60)
        continue

    rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 1)
    if rates_m1 is None or len(rates_m1) == 0:
        mt5.shutdown()
        time.sleep(60)
        continue

    vela = rates_m1[0]
    tiempo_vela = datetime.fromtimestamp(vela['time'])

    if tiempo_vela == ultimo_chequeo:
        time.sleep(1)
        continue

    open_ = vela['open']
    close = vela['close']
    cuerpo = abs(close - open_)
    mitad_cuerpo = cuerpo * 0.5

    # Detectar ruptura de resistencia
    if close > ultimo_alto and (close - open_ > mitad_cuerpo) and close > open_:
        print("\nROMPIMIENTO")
        print(f" Cierre vela: {close:.5f} @ {tiempo_vela}")
        print(" rompio resistencia")
        print("finalizado")
        mt5.shutdown()
        break

    # Detectar ruptura de soporte
    elif close < ultimo_bajo and (open_ - close > mitad_cuerpo) and close < open_:
        print("\nROMPIMIENTO")
        print(f" Cierre vela: {close:.5f} @ {tiempo_vela}")
        print(" rompio soporte")
        print("finalizado")
        mt5.shutdown()
        break

    # Mostrar mensaje solo cada 15 minutos
    ahora = datetime.now()
    if ahora - ultimo_mensaje_info >= timedelta(minutes=15):
        print("⏳ Esperando rompimiento...")
        ultimo_mensaje_info = ahora

    ultimo_chequeo = tiempo_vela
    mt5.shutdown()
    time.sleep(60)
