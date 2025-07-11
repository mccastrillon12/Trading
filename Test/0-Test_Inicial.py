# IMPORTS Y CONFIGURACIÓN BASE
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import pytz
import os

# CONEXIÓN A MT5
if not mt5.initialize():
    print("❌ Error al conectar con MT5:", mt5.last_error())
    quit()
else:
    print("✅ Conexión establecida con MetaTrader 5")

# PARÁMETROS
symbol = "EURUSD"
timeframe_m15 = mt5.TIMEFRAME_M15
timeframe_m1 = mt5.TIMEFRAME_M1
capital_inicial = 10000
capital = capital_inicial
risk_pct_loss = 0.01

# RANGO DE FECHAS
hasta = datetime.now()
desde = hasta - timedelta(days=30)

# DATOS HISTÓRICOS M15 (para determinar alto y bajo)
datos_m15 = mt5.copy_rates_range(symbol, timeframe_m15, desde, hasta)

# DATOS HISTÓRICOS M1 (para entradas y gestión)
datos_m1 = mt5.copy_rates_range(symbol, timeframe_m1, desde, hasta)
mt5.shutdown()

# PREPROCESAMIENTO
df_15m = pd.DataFrame(datos_m15)
df_15m['time'] = pd.to_datetime(df_15m['time'], unit='s')
df_15m['hora_mt5'] = df_15m['time'].dt.hour

# Aplicar ZigZag para detectar pivotes en M15
def calcular_zigzag(df, desviacion=0.00001, tramos=2):
    pivotes = []
    for i in range(tramos, len(df) - tramos):
        es_alto = all(df.loc[i, 'high'] > df.loc[i - j, 'high'] and df.loc[i, 'high'] > df.loc[i + j, 'high'] for j in range(1, tramos + 1))
        es_bajo = all(df.loc[i, 'low'] < df.loc[i - j, 'low'] and df.loc[i, 'low'] < df.loc[i + j, 'low'] for j in range(1, tramos + 1))
        if es_alto:
            pivotes.append({'tipo': 'alto', 'valor': df.loc[i, 'high'], 'tiempo': df.loc[i, 'time']})
        elif es_bajo:
            pivotes.append({'tipo': 'bajo', 'valor': df.loc[i, 'low'], 'tiempo': df.loc[i, 'time']})
    return pd.DataFrame(pivotes)

zigzag_15m = calcular_zigzag(df_15m)

# DATOS M1
df = pd.DataFrame(datos_m1)
df['time'] = pd.to_datetime(df['time'], unit='s')
df['hora_mt5'] = df['time'].dt.hour
df['minuto_mt5'] = df['time'].dt.minute
df['fecha_mt5'] = df['time'].dt.date

# BACKTESTING
operaciones = []
historico_capital = []
fechas_operadas = set()

for fecha in sorted(df['fecha_mt5'].unique()):
    if fecha in fechas_operadas:
        continue

    pivotes_del_dia = zigzag_15m[zigzag_15m['tiempo'].dt.date == fecha]
    pivotes_previos = pivotes_del_dia[pivotes_del_dia['tiempo'].dt.hour < 19]
    if pivotes_previos.empty:
        continue

    ult_alto = pivotes_previos[pivotes_previos['tipo'] == 'alto'].iloc[-1] if not pivotes_previos[pivotes_previos['tipo'] == 'alto'].empty else None
    ult_bajo = pivotes_previos[pivotes_previos['tipo'] == 'bajo'].iloc[-1] if not pivotes_previos[pivotes_previos['tipo'] == 'bajo'].empty else None

    if ult_alto is None or ult_bajo is None:
        continue

    high_ref = ult_alto['valor']
    low_ref = ult_bajo['valor']

    df_dia = df[(df['fecha_mt5'] == fecha) & (((df['hora_mt5'] == 19) & (df['minuto_mt5'] >= 1)) | (df['hora_mt5'] == 20))]

    for i in range(1, len(df_dia) - 1):
        vela = df_dia.iloc[i]
        siguiente = df_dia.iloc[i + 1]

        tipo = None
        if vela['high'] > high_ref:
            tipo = 'compra'
            entrada = siguiente['open']
            sl = vela['low']
            riesgo = abs(entrada - sl)
            tp = entrada + 2 * riesgo
        elif vela['low'] < low_ref:
            tipo = 'venta'
            entrada = siguiente['open']
            sl = vela['high']
            riesgo = abs(entrada - sl)
            tp = entrada - 2 * riesgo

        if tipo is None:
            continue

        exito = None
        cierre = None
        for j in range(i + 2, len(df_dia)):
            vela_eval = df_dia.iloc[j]
            if tipo == 'compra':
                if vela_eval['low'] <= sl:
                    exito = False
                    cierre = vela_eval['time']
                    break
                elif vela_eval['high'] >= tp:
                    exito = True
                    cierre = vela_eval['time']
                    break
            else:
                if vela_eval['high'] >= sl:
                    exito = False
                    cierre = vela_eval['time']
                    break
                elif vela_eval['low'] <= tp:
                    exito = True
                    cierre = vela_eval['time']
                    break

        if exito is None:
            continue

        resultado = "ganada" if exito else "perdida"
        capital += capital_inicial * (risk_pct_loss * 2 if exito else -risk_pct_loss)

        operaciones.append({
            "fecha_ingreso": vela['time'].date(),
            "hora_ingreso": vela['time'].time(),
            "fecha_cierre": cierre.date(),
            "hora_cierre": cierre.time(),
            "tipo": tipo,
            "entrada": round(entrada, 5),
            "tp": round(tp, 5),
            "sl": round(sl, 5),
            "high_ref_m15": round(high_ref, 5),
            "low_ref_m15": round(low_ref, 5),
            "resultado": resultado,
            "capital_post": round(capital, 2)
        })

        historico_capital.append({"fecha": cierre, "capital": capital})
        fechas_operadas.add(fecha)
        break

# EXPORTACIÓN Y REPORTE
for op in operaciones:
    op["total_dias"] = (op["fecha_cierre"] - op["fecha_ingreso"]).days
    ingreso_dt = datetime.combine(op["fecha_ingreso"], op["hora_ingreso"])
    cierre_dt = datetime.combine(op["fecha_cierre"], op["hora_cierre"])
    duracion = cierre_dt - ingreso_dt
    horas, resto = divmod(duracion.seconds, 3600)
    minutos = resto // 60
    op["duracion_operacion"] = f"{horas}h {minutos}m"

base_path = "C:\\Users\\USUARIO\\Desktop\\python"
csv_path = os.path.join(base_path, "estrategia_breakout.csv")
img_path = os.path.join(base_path, "grafico_breakout.png")

df_operaciones = pd.DataFrame(operaciones)
df_operaciones.to_csv(csv_path, index=False, sep=';')

# RESULTADOS EN CONSOLA
total = len(df_operaciones)
ganadas = df_operaciones[df_operaciones['resultado'] == 'ganada'].shape[0]
perdidas = df_operaciones[df_operaciones['resultado'] == 'perdida'].shape[0]
efec = (ganadas / total * 100) if total else 0
print("\n📊 RESULTADOS ESTRATEGIA BREAKOUT:")
print(f"✅ Ganadas: {ganadas}")
print(f"❌ Perdidas: {perdidas}")
print(f"📋 Total: {total}")
print(f"🎯 Efectividad: {efec:.2f}%")
print(f"💰 Capital final: {capital:.2f} USD")

# GRÁFICO
fechas = [datetime.combine(op["fecha_ingreso"], op["hora_ingreso"]) for op in operaciones]
capitales = [op["capital_post"] for op in operaciones]

plt.figure(figsize=(12, 6))
plt.plot(fechas, capitales, marker='o', linestyle='-')
plt.title("📈 Evolución del capital (Breakout EUR/USD)")
plt.xlabel("Fecha")
plt.ylabel("Capital ($)")
plt.xticks(rotation=45)
plt.grid(True)
plt.tight_layout()
plt.savefig(img_path)
print(f"🖼️ Gráfico guardado: {img_path}")
plt.show()