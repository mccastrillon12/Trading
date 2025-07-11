import MetaTrader5 as mt5
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from collections import defaultdict
from calendar import month_name
import os

# === CONEXIÓN CON MT5 ===
if not mt5.initialize():
    print("❌ No se pudo conectar a MetaTrader 5")
    quit()

symbol = "EURUSD"

# === OBTENER HORA DEL SERVIDOR MT5 (SIN CONVERSIÓN) ===
tick_info = mt5.symbol_info_tick(symbol)
if tick_info is None or tick_info.time == 0:
    print("❌ No se pudo obtener la hora del servidor MT5")
    mt5.shutdown()
    quit()

fecha_fin = pd.to_datetime(tick_info.time, unit="s")
print(f"🕒 Hora del servidor MT5: {fecha_fin.strftime('%Y-%m-%d %H:%M:%S')}")

# === PARÁMETROS DE TRADING ===
capital_inicial = 10_000
capital = capital_inicial
riesgo_pct = 0.005
max_riesgo_diario = 0.01
rango_velas = 5

fecha_inicio = fecha_fin - timedelta(days=60)

# === OBTENER DATOS M1 ===
datos = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, fecha_inicio, fecha_fin)
mt5.shutdown()

if datos is None or len(datos) == 0:
    print("❌ No se encontraron datos")
    quit()

df = pd.DataFrame(datos)
df["time"] = pd.to_datetime(df["time"], unit="s")
df.set_index("time", inplace=True)
df = df[["open", "high", "low", "close"]]
df["fecha"] = df.index.date

# === BACKTEST ===
ganadas = 0
perdidas = 0
resultados = []
operaciones = []
lotajes = []
tipos_op = []  # 🔁 MODIFICADO: para guardar tipo de operación

perdida_diaria = 0
ultimo_dia = None

motivos_descartes = defaultdict(int)
stats_por_dia = defaultdict(lambda: {"ganadas": 0, "perdidas": 0})

for i in range(rango_velas, len(df) - 1):
    ahora = df.index[i]
    hora = ahora.time()
    fecha_actual = ahora.date()

    if fecha_actual != ultimo_dia:
        perdida_diaria = 0
        ultimo_dia = fecha_actual

    if perdida_diaria >= capital * max_riesgo_diario:
        motivos_descartes["riesgo_diario_excedido"] += 1
        continue

    if not (6 <= hora.hour < 18):
        motivos_descartes["fuera_de_horario"] += 1
        continue

    rango_df = df.iloc[i - rango_velas:i]
    high_range = rango_df["high"].max()
    low_range = rango_df["low"].min()
    rango_pips = high_range - low_range

    if rango_pips < 0.0005:
        motivos_descartes["rango_pips_bajo"] += 1
        continue

    precio_actual = df.iloc[i]["close"]
    riesgo_por_trade = capital * riesgo_pct
    stop_loss = rango_pips
    take_profit = rango_pips

    pip_value = 10  # $10 por pip por lote en EUR/USD
    stop_loss_pips = stop_loss * 10_000
    if stop_loss_pips == 0:
        motivos_descartes["stop_loss_cero"] += 1
        continue

    lotaje = riesgo_por_trade / (stop_loss_pips * pip_value)
    lotaje = round(lotaje, 2)
    if lotaje <= 0:
        motivos_descartes["lotaje_cero"] += 1
        continue

    siguiente = df.iloc[i + 1]
    entrada_long = precio_actual > high_range
    entrada_short = precio_actual < low_range

    if entrada_long:
        tp = precio_actual + take_profit
        sl = precio_actual - stop_loss
        high = siguiente["high"]
        low = siguiente["low"]

        if low <= sl:
            capital -= riesgo_por_trade
            perdidas += 1
            perdida_diaria += riesgo_por_trade
            resultados.append(-riesgo_por_trade)
            operaciones.append(ahora)
            lotajes.append(lotaje)
            tipos_op.append("Long")  # 🔁 MODIFICADO
            stats_por_dia[fecha_actual]["perdidas"] += 1
        elif high >= tp:
            capital += riesgo_por_trade
            ganadas += 1
            resultados.append(riesgo_por_trade)
            operaciones.append(ahora)
            lotajes.append(lotaje)
            tipos_op.append("Long")  # 🔁 MODIFICADO
            stats_por_dia[fecha_actual]["ganadas"] += 1

    elif entrada_short:
        tp = precio_actual - take_profit
        sl = precio_actual + stop_loss
        high = siguiente["high"]
        low = siguiente["low"]

        if high >= sl:
            capital -= riesgo_por_trade
            perdidas += 1
            perdida_diaria += riesgo_por_trade
            resultados.append(-riesgo_por_trade)
            operaciones.append(ahora)
            lotajes.append(lotaje)
            tipos_op.append("Short")  # 🔁 MODIFICADO
            stats_por_dia[fecha_actual]["perdidas"] += 1
        elif low <= tp:
            capital += riesgo_por_trade
            ganadas += 1
            resultados.append(riesgo_por_trade)
            operaciones.append(ahora)
            lotajes.append(lotaje)
            tipos_op.append("Short")  # 🔁 MODIFICADO
            stats_por_dia[fecha_actual]["ganadas"] += 1

# === RESUMEN GENERAL ===
print(f"\n🧾 Resultados del backtest:")
print(f"Capital inicial:  ${capital_inicial:,.2f}")
print(f"Capital final:    ${capital:,.2f}")
print(f"Operaciones:      {ganadas + perdidas}")
print(f"Ganadas:          {ganadas}")
print(f"Perdidas:         {perdidas}")
print(f"Winrate:          {ganadas / (ganadas + perdidas) * 100:.2f}%" if (ganadas + perdidas) > 0 else "Winrate: N/A")

# === AGRUPACIÓN POR MES Y EFECTIVIDAD ===
stats_por_mes = defaultdict(list)
for dia in sorted(stats_por_dia.keys()):
    stats_por_mes[(dia.year, dia.month)].append((dia, stats_por_dia[dia]))

print("\n📅 Resumen mensual de operaciones:")
for (anio, mes), lista_dias in stats_por_mes.items():
    print(f"\n📆 {month_name[mes]} {anio}")
    total_mes = 0
    ganadas_mes = 0
    perdidas_mes = 0
    for dia, datos in lista_dias:
        ganadas_dia = datos["ganadas"]
        perdidas_dia = datos["perdidas"]
        total_dia = ganadas_dia + perdidas_dia
        resumen = f"{ganadas_dia} Ganada" if ganadas_dia == 1 else f"{ganadas_dia} Ganadas"
        resumen += ", "
        resumen += f"{perdidas_dia} Perdida" if perdidas_dia == 1 else f"{perdidas_dia} Perdidas"
        print(f"  {dia}: {total_dia} operaciones - {resumen}")
        total_mes += total_dia
        ganadas_mes += ganadas_dia
        perdidas_mes += perdidas_dia
    winrate_mes = (ganadas_mes / total_mes * 100) if total_mes > 0 else 0
    print(f"\n📊 Efectividad {month_name[mes]} {anio}: {winrate_mes:.2f}%")

# === GRAFICAR EVOLUCIÓN DEL CAPITAL ===
resultado_dia = {}
equity_dia = {}
capital_tmp = capital_inicial
acumulado = 0
fecha_actual = None

for idx, r in enumerate(resultados):
    fecha_op = operaciones[idx].date()
    if fecha_op != fecha_actual:
        if fecha_actual is not None:
            resultado_dia[fecha_actual] = acumulado
            capital_tmp += acumulado
            equity_dia[fecha_actual] = capital_tmp
        fecha_actual = fecha_op
        acumulado = 0
    acumulado += r

if fecha_actual is not None:
    resultado_dia[fecha_actual] = acumulado
    capital_tmp += acumulado
    equity_dia[fecha_actual] = capital_tmp

plt.figure(figsize=(12, 6))
fechas = list(equity_dia.keys())
capitales = list(equity_dia.values())
pnl_dia = [resultado_dia[fecha] for fecha in fechas]

plt.plot(fechas, capitales, marker='o', linestyle='-', color='steelblue')
for fecha, capital, pnl in zip(fechas, capitales, pnl_dia):
    color = "green" if pnl >= 0 else "red"
    signo = "+" if pnl >= 0 else ""
    plt.text(fecha, capital + 25, f"{signo}{int(pnl)}", fontsize=9, color=color, ha='center')

plt.title("Evolución diaria del capital")
plt.xlabel("Fecha")
plt.ylabel("Capital ($)")
plt.grid(True)
plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=1))
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# === EXPORTAR A EXCEL ===
excel_data = []
for i in range(len(operaciones)):
    dt = operaciones[i]
    resultado = resultados[i]
    estado = "Ganada" if resultado > 0 else "Perdida"
    excel_data.append({
        "Fecha": dt.date().strftime('%Y-%m-%d'),
        "Hora": dt.time().strftime('%H:%M:%S'),
        "Resultado": estado,
        "PnL ($)": resultado,
        "Lotaje": lotajes[i],
        "Tipo": tipos_op[i]  # 🔁 MODIFICADO: tipo de operación
    })

df_excel = pd.DataFrame(excel_data)
ruta_excel = r"C:\Users\USUARIO\Desktop\python\Estrategias\operaciones.xlsx"
os.makedirs(os.path.dirname(ruta_excel), exist_ok=True)
df_excel.to_excel(ruta_excel, index=False)
print(ruta_excel)
print(df_excel.head())
print("Filas:", len(df_excel))

# 🔁 MODIFICADO: abrir automáticamente el archivo
if os.path.exists(ruta_excel):
    print(f"\n✅ Archivo guardado en: {ruta_excel}")
    try:
        os.startfile(ruta_excel)
    except Exception as e:
        print(f"⚠️ No se pudo abrir automáticamente el archivo: {e}")
else:
    print(f"❌ No se encontró el archivo en: {ruta_excel}")
