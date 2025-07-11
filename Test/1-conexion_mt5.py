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
timeframe = mt5.TIMEFRAME_M1
rr_ratio = 2
risk_pips = 10
pip_value = 0.0001
capital_inicial = 10000
capital = capital_inicial
risk_pct_loss = 0.01
risk_pct_win = 0.02

# RANGO DE FECHAS
hasta = datetime.now()
desde = hasta - timedelta(days=30)

# DATOS HISTÓRICOS
datos = mt5.copy_rates_range(symbol, timeframe, desde, hasta)
mt5.shutdown()

df = pd.DataFrame(datos)
df['time'] = pd.to_datetime(df['time'], unit='s')
ny_tz = pytz.timezone("America/New_York")
df['time'] = df['time'].dt.tz_localize('UTC')
df['hora_ny'] = df['time'].dt.tz_convert(ny_tz).dt.hour
df['date_only'] = df['time'].dt.tz_convert(ny_tz).dt.date

# FUNCIONES DEL PATRÓN
def es_correccion_suficiente(prev_cuerpo, retroceso):
    return retroceso >= 0.05 * prev_cuerpo

def detectar_3_drives(df, i, tipo):
    try:
        p1 = df.iloc[i-6]
        p2 = df.iloc[i-4]
        p3 = df.iloc[i-2]

        if tipo == 'compra':
            cond = p1['low'] > p2['low'] > p3['low']
            retro1 = p1['high'] - p2['low']
            retro2 = p2['high'] - p3['low']
            cuerpo1 = abs(p1['open'] - p1['close'])
            cuerpo2 = abs(p2['open'] - p2['close'])
        else:
            cond = p1['high'] < p2['high'] < p3['high']
            retro1 = p2['high'] - p1['low']
            retro2 = p3['high'] - p2['low']
            cuerpo1 = abs(p1['open'] - p1['close'])
            cuerpo2 = abs(p2['open'] - p2['close'])

        return cond and es_correccion_suficiente(cuerpo1, retro1) and es_correccion_suficiente(cuerpo2, retro2)
    except:
        return False

def detectar_fvg(df, i):
    vela = df.iloc[i]
    cuerpo = abs(vela['open'] - vela['close'])
    mecha_opuesta = abs(vela['high'] - vela['low']) - cuerpo
    return cuerpo > mecha_opuesta * 1.5

def evaluar_operacion(df, i, tipo):
    entrada = df.iloc[i]['close']
    if tipo == 'compra':
        sl = entrada - risk_pips * pip_value
        tp = entrada + rr_ratio * risk_pips * pip_value
        sl_break_even = entrada
        objetivo_break_even = entrada + 0.01 * entrada
    else:
        sl = entrada + risk_pips * pip_value
        tp = entrada - rr_ratio * risk_pips * pip_value
        sl_break_even = entrada
        objetivo_break_even = entrada - 0.01 * entrada

    sl_ajustado = False

    for j in range(i+1, len(df)):
        vela = df.iloc[j]

        if tipo == 'compra':
            if not sl_ajustado and vela['high'] >= objetivo_break_even:
                sl = sl_break_even
                sl_ajustado = True
            if vela['low'] <= sl:
                return ("BE" if sl_ajustado else False), vela['time'], entrada, sl, tp
            elif vela['high'] >= tp:
                return True, vela['time'], entrada, sl, tp
        else:
            if not sl_ajustado and vela['low'] <= objetivo_break_even:
                sl = sl_break_even
                sl_ajustado = True
            if vela['high'] >= sl:
                return ("BE" if sl_ajustado else False), vela['time'], entrada, sl, tp
            elif vela['low'] <= tp:
                return True, vela['time'], entrada, sl, tp
    return None, None, entrada, sl, tp

# BACKTESTING
operaciones = []
fechas_operadas = set()
historico_capital = []

for i in range(10, len(df)-10):
    if df.iloc[i]['hora_ny'] < 8 or df.iloc[i]['hora_ny'] > 17:
        continue

    fecha_actual = df.iloc[i]['date_only']
    if fecha_actual in fechas_operadas:
        continue

    for tipo in ['compra', 'venta']:
        if detectar_3_drives(df, i, tipo) and detectar_fvg(df, i):
            exito, cierre, entrada, sl, tp = evaluar_operacion(df, i, tipo)
            if exito is not None:
                if exito == True:
                    resultado = "ganada"
                    capital += capital_inicial * risk_pct_win
                elif exito == "BE":
                    resultado = "BE"
                else:
                    resultado = "perdida"
                    capital -= capital_inicial * risk_pct_loss

                historico_capital.append({"fecha": cierre, "capital": capital})

                operaciones.append({
                    "fecha_ingreso": df.iloc[i]['time'].date(),
                    "hora_ingreso": df.iloc[i]['time'].time(),
                    "fecha_cierre": cierre.date(),
                    "hora_cierre": cierre.time(),
                    "tipo": tipo,
                    "entrada": round(entrada, 5),
                    "tp": round(tp, 5),
                    "sl": round(sl, 5),
                    "resultado": resultado,
                    "capital_post": round(capital, 2)
                })
                fechas_operadas.add(fecha_actual)
            break

# CALCULAR DURACIONES
for op in operaciones:
    op["total_dias"] = (op["fecha_cierre"] - op["fecha_ingreso"]).days
    ingreso_dt = datetime.combine(op["fecha_ingreso"], op["hora_ingreso"])
    cierre_dt = datetime.combine(op["fecha_cierre"], op["hora_cierre"])
    duracion = cierre_dt - ingreso_dt
    horas, resto = divmod(duracion.seconds, 3600)
    minutos = resto // 60
    op["duracion_operacion"] = f"{horas}h {minutos}m"

# GENERAR NOMBRES DE ARCHIVOS ÚNICOS
base_path = "C:\\Users\\USUARIO\\Desktop\\python"
csv_base = os.path.join(base_path, "operaciones_backtesting")
img_base = os.path.join(base_path, "grafico_backtesting")

csv_path = csv_base + ".csv"
grafico_path = img_base + ".png"
csv_idx, img_idx = 1, 1

while os.path.exists(csv_path):
    csv_path = f"{csv_base}_{csv_idx}.csv"
    csv_idx += 1

while os.path.exists(grafico_path):
    grafico_path = f"{img_base}_{img_idx}.png"
    img_idx += 1

# EXPORTAR A CSV
df_operaciones = pd.DataFrame(operaciones)[[
    "fecha_ingreso", "fecha_cierre", "total_dias",
    "hora_ingreso", "hora_cierre", "duracion_operacion",
    "tipo", "entrada", "tp", "sl", "resultado", "capital_post"
]]
df_operaciones.to_csv(csv_path, index=False, sep=';')

porcentaje_final = ((capital - capital_inicial) / capital_inicial) * 100
with open(csv_path, "a", encoding="utf-8") as f:
    f.write(f"\nPorcentaje total de ganancia/pérdida:;{porcentaje_final:.2f}%")

# RESULTADOS EN CONSOLA
total = len(df_operaciones)
ganadas = df_operaciones[df_operaciones['resultado'] == 'ganada'].shape[0]
perdidas = df_operaciones[df_operaciones['resultado'] == 'perdida'].shape[0]
break_even = df_operaciones[df_operaciones['resultado'] == 'BE'].shape[0]

print("\n📊 RESULTADOS DEL BACKTESTING:")
print(f"✅ Ganadas: {ganadas}")
print(f"❌ Perdidas: {perdidas}")
print(f"➖ Break Even: {break_even}")
print(f"📋 Total: {total}")
print(f"🎯 Efectividad: {(ganadas / total * 100) if total else 0:.2f}%")
print(f"💰 Capital final: {capital:.2f} USD")

# GRÁFICO
fechas = [datetime.combine(op["fecha_ingreso"], op["hora_ingreso"]) for op in operaciones]
capitales = [op["capital_post"] for op in operaciones]

plt.figure(figsize=(12, 6))
plt.plot(fechas, capitales, marker='o', linestyle='-')
plt.title("📉 Evolución del capital (Backtesting EUR/USD)")
plt.xlabel("Fecha")
plt.ylabel("Capital ($)")
plt.xticks(ticks=fechas, labels=[f.strftime("%d-%b") for f in fechas], rotation=45)
plt.grid(True)
plt.tight_layout()

plt.savefig(grafico_path)
print(f"\n🖼️ Gráfico guardado: {grafico_path}")
plt.show()
