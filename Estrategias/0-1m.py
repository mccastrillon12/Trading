import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === CONFIGURACIÓN GENERAL ===
symbol = "EURUSD"
riesgo_pct = 0.005
max_riesgo_diario = 0.01
rango_velas = 5
pip_value = 10  # $10 por pip por lote
magic_number = 10001

# === DATOS SMTP (MODIFICA ESTO) ===
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "castrillonosorio12@gmail.com"
smtp_pass = "qknwerxaoalerbtn"
destinatario = "castrillonosorio12@gmail.com"


# === ENVIAR CORREO AL ABRIR OPERACIÓN ===
def enviar_correo_operacion(tipo, entrada, sl, tp):
    asunto = f"Operacion - {'Compra' if tipo == mt5.ORDER_TYPE_BUY else 'Venta'}"
    cuerpo = f"""Se abrió una operación en {symbol}.

🔹 Entrada: {entrada:.5f}
🔻 SL: {sl:.5f}
🔺 TP: {tp:.5f}
"""
    enviar_email(asunto, cuerpo)

# === ENVIAR CORREO AL CERRAR OPERACIÓN ===
def enviar_correo_cierre_operacion(ganancia_usd):
    signo = "+" if ganancia_usd >= 0 else "-"
    asunto = f"Cierre {signo}{abs(ganancia_usd):.2f}"
    cuerpo = f"La operación fue cerrada.\n\n💰 Resultado: {ganancia_usd:.2f} USD"
    enviar_email(asunto, cuerpo)

# === ENVÍO DE CORREO GENERAL ===
def enviar_email(asunto, cuerpo):
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = destinatario
    msg["Subject"] = asunto

    msg.attach(MIMEText(cuerpo, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, destinatario, msg.as_string())
            print(f"📧 Correo enviado: {asunto}")
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")

# === CONECTAR A MT5 ===
if not mt5.initialize():
    print("❌ No se pudo conectar a MetaTrader 5")
    quit()

account = mt5.account_info()
if account is None:
    print("❌ No se pudo obtener información de la cuenta")
    mt5.shutdown()
    quit()

capital_inicial = account.balance
capital = capital_inicial
print(f"💰 Balance inicial de la cuenta: ${capital:,.2f}")

# === FUNCIONES ===
def obtener_ultimas_velas(hora_servidor_actual):
    desde = hora_servidor_actual - timedelta(minutes=rango_velas + 1)
    datos = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, desde, hora_servidor_actual)
    if datos is None or len(datos) < rango_velas + 1:
        return None
    df = pd.DataFrame(datos)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df

def enviar_orden(tipo, lotaje, sl, tp):
    precio = mt5.symbol_info_tick(symbol).ask if tipo == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lotaje,
        "type": tipo,
        "price": precio,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": magic_number,
        "comment": "operacion_rango_vivo",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    return mt5.order_send(request)

# === VARIABLES DE CONTROL ===
perdida_diaria = 0
ultimo_dia = None
inicio_operativa_notificado = False
ultima_hora_fuera_operativa = None
tickets_abiertos = set()

# === BUCLE PRINCIPAL EN VIVO ===
while True:
    tick_info = mt5.symbol_info_tick(symbol)
    if tick_info is None or tick_info.time == 0:
        print("⚠️ No se pudo obtener la hora del servidor, reintentando...")
        time.sleep(5)
        continue

    hora_servidor_actual = pd.to_datetime(tick_info.time, unit="s")
    hora = hora_servidor_actual.time()
    fecha = hora_servidor_actual.date()

    print(f"\n🕒 Hora del servidor MT5: {hora_servidor_actual.strftime('%Y-%m-%d %H:%M:%S')}")

    if not (hora.hour >= 23 or hora.hour < 6):     
        if (ultima_hora_fuera_operativa is None) or (hora.hour != ultima_hora_fuera_operativa):
            print("⌛ Fuera de horario de operativa ")
            ultima_hora_fuera_operativa = hora.hour
        inicio_operativa_notificado = False
        time.sleep(60)
        continue

    if not inicio_operativa_notificado:
        print("✅ Inicio operativa")
        inicio_operativa_notificado = True

    # Actualizar capital con balance actual
    account = mt5.account_info()
    if account is None:
        print("⚠️ No se pudo actualizar el balance. Reintentando...")
        time.sleep(30)
        continue

    capital = account.balance
    print(f"💰 Balance actual: ${capital:,.2f}")

    if fecha != ultimo_dia:
        perdida_diaria = 0
        ultimo_dia = fecha

    if perdida_diaria >= capital * max_riesgo_diario:
        print("🚫 Límite de pérdida diaria alcanzado.")
        time.sleep(60)
        continue

    # Revisar si alguna operación abierta fue cerrada
    ordenes_cerradas = mt5.history_deals_get(datetime.now() - timedelta(days=1), datetime.now())
    if ordenes_cerradas:
        for orden in ordenes_cerradas:
            if orden.magic == magic_number and orden.type == mt5.DEAL_TYPE_CLOSE and orden.ticket not in tickets_abiertos:
                enviar_correo_cierre_operacion(orden.profit)
                tickets_abiertos.add(orden.ticket)

    df = obtener_ultimas_velas(hora_servidor_actual)
    if df is None or len(df) < rango_velas + 1:
        print("⚠️ No se pudieron obtener suficientes velas.")
        time.sleep(30)
        continue

    rango_df = df.iloc[-(rango_velas + 1):-1]
    vela_actual = df.iloc[-2]
    siguiente_vela = df.iloc[-1]

    high_range = rango_df["high"].max()
    low_range = rango_df["low"].min()
    rango_pips = high_range - low_range

    if rango_pips < 0.0005:
        print("📏 Rango demasiado pequeño, no se opera.")
        time.sleep(60)
        continue

    precio_actual = vela_actual["close"]
    riesgo_por_trade = capital * riesgo_pct
    stop_loss = rango_pips
    take_profit = rango_pips

    stop_loss_pips = stop_loss * 10_000
    if stop_loss_pips == 0:
        print("❌ Stop Loss cero, operación descartada.")
        time.sleep(60)
        continue

    lotaje = riesgo_por_trade / (stop_loss_pips * pip_value)
    lotaje = round(lotaje, 2)
    if lotaje <= 0:
        print("❌ Lotaje calculado es cero.")
        time.sleep(60)
        continue

    if precio_actual > high_range:  # Entrada LONG
        sl = precio_actual - stop_loss
        tp = precio_actual + take_profit
        result = enviar_orden(mt5.ORDER_TYPE_BUY, lotaje, sl, tp)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ LONG ejecutada @ {precio_actual:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
            enviar_correo_operacion(mt5.ORDER_TYPE_BUY, precio_actual, sl, tp)
        else:
            print(f"❌ Error al ejecutar LONG: {result.comment}")

    elif precio_actual < low_range:  # Entrada SHORT
        sl = precio_actual + stop_loss
        tp = precio_actual - take_profit
        result = enviar_orden(mt5.ORDER_TYPE_SELL, lotaje, sl, tp)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ SHORT ejecutada @ {precio_actual:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
            enviar_correo_operacion(mt5.ORDER_TYPE_SELL, precio_actual, sl, tp)
        else:
            print(f"❌ Error al ejecutar SHORT: {result.comment}")
    else:
        print("📉 Sin ruptura válida. Esperando siguiente vela...")

    time.sleep(60)
