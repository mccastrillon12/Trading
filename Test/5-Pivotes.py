import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN ===
symbol = "EURUSD"

# === CONEXIÓN MT5 ===
if not mt5.initialize():
    print("❌ No se pudo conectar a MT5")
    quit()

# === OBTENER DATOS DE 15M ===
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 200)
mt5.shutdown()

if rates is None or len(rates) < 3:
    print("⚠️ No se pudieron obtener suficientes velas")
    quit()

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

# === DETECTAR CAMBIO DE DIRECCIÓN (ZIGZAG SIMPLE) ===
pivotes_altos = []
pivotes_bajos = []

for i in range(1, len(df) - 1):
    prev_high = df.loc[i - 1, 'high']
    curr_high = df.loc[i, 'high']
    next_high = df.loc[i + 1, 'high']

    prev_low = df.loc[i - 1, 'low']
    curr_low = df.loc[i, 'low']
    next_low = df.loc[i + 1, 'low']

    if curr_high > prev_high and curr_high > next_high:
        pivotes_altos.append((df.loc[i, 'time'], curr_high))

    if curr_low < prev_low and curr_low < next_low:
        pivotes_bajos.append((df.loc[i, 'time'], curr_low))

# === IMPRIMIR RESULTADOS (orden cronológico) ===
print("\n📈 Últimos 3 Picos ALTOS (ZigZag) [más antiguos → recientes]:")
for t, v in pivotes_altos[-3:]:
    print(f"   ➤ {v:.5f} @ {t}")

print("\n📉 Últimos 3 Picos BAJOS (ZigZag) [más antiguos → recientes]:")
for t, v in pivotes_bajos[-3:]:
    print(f"   ➤ {v:.5f} @ {t}")
