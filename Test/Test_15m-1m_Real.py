import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd

# === PARÁMETROS ===
symbol = "EURUSD"
risk_pct_loss = 0.001
tramos = 2
operaciones_realizadas = set()
correo_enviado_inicio_operacion = set()
correo_enviado_fin_operacion = set()
niveles_detectados = {}

EMAIL_FROM = "castrillonosorio12@gmail.com"
EMAIL_TO = "castrillonosorio12@gmail.com"
EMAIL_PASS = "qknwerxaoalerbtn"

# === INICIALIZACIÓN MT5 ===
if not mt5.initialize():
    print("❌ Error al conectar con MT5:", mt5.last_error())
    quit()
else:
    print("✅ Conectado a MT5")

# === FUNCIONES ===

def hora_mt5():
    return datetime.now(timezone.utc) + timedelta(hours=3)

def enviar_email(asunto, cuerpo):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain"))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")

def calcular_zigzag(df, tramos):
    pivotes = []
    for i in range(tramos, len(df) - tramos):
        es_alto = all(df.loc[i, 'high'] > df.loc[i - j, 'high'] and df.loc[i, 'high'] > df.loc[i + j, 'high'] for j in range(1, tramos + 1))
        es_bajo = all(df.loc[i, 'low'] < df.loc[i - j, 'low'] and df.loc[i, 'low'] < df.loc[i + j, 'low'] for j in range(1, tramos + 1))
        if es_alto:
            pivotes.append({'tipo': 'alto', 'valor': df.loc[i, 'high'], 'tiempo': datetime.fromtimestamp(df.loc[i, 'time'])})
        elif es_bajo:
            pivotes.append({'tipo': 'bajo', 'valor': df.loc[i, 'low'], 'tiempo': datetime.fromtimestamp(df.loc[i, 'time'])})
    return pivotes

def cuerpo_supera_nivel(vela, nivel, tipo):
    open_ = vela['open']
    close = vela['close']
    cuerpo_alto = max(open_, close)
    cuerpo_bajo = min(open_, close)
    cuerpo_total = abs(close - open_)
    if cuerpo_total == 0:
        return False  # vela doji
    if tipo == "compra":
        cuerpo_superior = max(0, cuerpo_alto - max(nivel, cuerpo_bajo))
        return cuerpo_superior >= 0.5 * cuerpo_total
    elif tipo == "venta":
        cuerpo_inferior = max(0, min(nivel, cuerpo_alto) - cuerpo_bajo)
        return cuerpo_inferior >= 0.5 * cuerpo_total
    return False

def obtener_pivotes_m15():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 76)
    if rates is None or len(rates) < tramos * 2:
        return None, None
    df = pd.DataFrame(rates)
    df['tiempo'] = pd.to_datetime(df['time'], unit='s')
    pivotes = calcular_zigzag(df, tramos)
    altos = [p for p in pivotes if p['tipo'] == 'alto']
    bajos = [p for p in pivotes if p['tipo'] == 'bajo']
    alto_reciente = max(altos, key=lambda x: x['tiempo']) if altos else None
    bajo_reciente = max(bajos, key=lambda x: x['tiempo']) if bajos else None
    return alto_reciente, bajo_reciente

def calcular_lote(balance, riesgo_pct, entrada, sl):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return 0.01
    riesgo_usd = balance * riesgo_pct
    riesgo_pips = abs(entrada - sl)
    valor_por_pip_lote = 10
    if riesgo_pips == 0:
        return symbol_info.volume_min
    lotes = riesgo_usd / (riesgo_pips * valor_por_pip_lote)
    paso = symbol_info.volume_step
    lotes = max(symbol_info.volume_min, min(symbol_info.volume_max, lotes))
    lotes = round(lotes / paso) * paso
    return lotes

def abrir_operacion(tipo, entrada, sl, tp, lot_size_inicial):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print("❌ Error: No se pudo obtener información del símbolo.")
        return

    paso = symbol_info.volume_step
    lote = lot_size_inicial

    print(f"🟡 Intentando abrir operación {tipo.upper()} con lote inicial: {lote:.2f}")
    print(f"🔍 Entrada: {entrada:.5f}, SL: {sl:.5f}, TP: {tp:.5f}")

    operacion_exitosa = False
    ultimo_error = None
    lote_usado = None

    def enviar_orden(volumen):
        return mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volumen,
            "type": mt5.ORDER_TYPE_BUY if tipo == "compra" else mt5.ORDER_TYPE_SELL,
            "price": mt5.symbol_info_tick(symbol).ask if tipo == "compra" else mt5.symbol_info_tick(symbol).bid,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": 123456,
            "comment": f"entrada_{tipo}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })

    while lote >= symbol_info.volume_min:
        result = enviar_orden(lote)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            operacion_exitosa = True
            lote_usado = lote
            break
        else:
            ultimo_error = result.retcode
            lote -= paso
            lote = round(lote / paso) * paso

    if operacion_exitosa:
        print(f"✅ Operación ejecutada: {tipo.upper()}")
        print(f"📌 BE (entrada): {entrada:.5f}, SL: {sl:.5f}, TP: {tp:.5f}, Lote: {lote_usado:.2f}")
        enviar_email(
            f"[Breakout] Operación ABIERTA: {tipo.upper()}",
            f"🔔 Operación ejecutada:\nTipo: {tipo.upper()}\nEntrada: {entrada}\nSL: {sl}\nTP: {tp}\nLote: {lote_usado}"
        )
    else:
        print(f"⚠️ Falló intento con lote {lot_size_inicial:.2f} - Código de error: {ultimo_error}")
        print("❌ No se pudo ejecutar la orden. Lote rechazado incluso en el mínimo permitido.")

# === LOOP PRINCIPAL ===
print("🚀 Estrategia en vivo iniciada...")
ahora = hora_mt5()
print(f"⏰ Hora MT5: {ahora.strftime('%H:%M:%S')}")
while True:
    
   
    hora = ahora.hour
    minuto = ahora.minute
    hoy = ahora.date()

    if hora == 6 and minuto == 0 and hoy not in correo_enviado_inicio_operacion:
        enviar_email("[Breakout] 🕒 Inicio sesión", "Evaluación activa hasta las 9:00am.")
        correo_enviado_inicio_operacion.add(hoy)

    if hora == 9 and minuto == 0 and hoy not in correo_enviado_fin_operacion:
        enviar_email("[Breakout] 🕔 Fin sesión", "Ventana operativa cerrada.")
        correo_enviado_fin_operacion.add(hoy)

    if hoy in operaciones_realizadas:
        time.sleep(1)
        continue

    if 6 <= hora < 9:
        if hoy not in niveles_detectados:
            alto, bajo = obtener_pivotes_m15()
            if not alto or not bajo:
                time.sleep(1)
                continue
            high_ref = alto['valor']
            low_ref = bajo['valor']
            niveles_detectados[hoy] = (high_ref, low_ref)
            print(f"📊 Niveles detectados para {hoy} -> Resistencia: {high_ref:.5f}, Soporte: {low_ref:.5f}")
            enviar_email(
                f"[Breakout] Niveles detectados - {hoy}",
                f"Resistencia: {high_ref}\nSoporte: {low_ref}"
            )
        else:
            high_ref, low_ref = niveles_detectados[hoy]

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            time.sleep(1)
            continue

        info = mt5.account_info()
        if not info:
            time.sleep(1)
            continue

        balance = info.balance

        # COMPRA
        if tick.ask > high_ref:
            velas = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, hora_mt5() - timedelta(minutes=3), 3)
            if velas is None or len(velas) < 3:
                time.sleep(1)
                continue
            vela = velas[0]
            if not cuerpo_supera_nivel(vela, high_ref, "compra"):
                time.sleep(1)
                continue
            sl = vela['open']
            entrada = tick.ask
            tp = entrada + 2 * abs(entrada - sl)
            lot_size = calcular_lote(balance, risk_pct_loss, entrada, sl)
            abrir_operacion("compra", entrada, sl, tp, lot_size)
            operaciones_realizadas.add(hoy)
            time.sleep(60 * 10)

        # VENTA
        elif tick.bid < low_ref:
            velas = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, hora_mt5() - timedelta(minutes=3), 3)
            if velas is None or len(velas) < 3:
                time.sleep(1)
                continue
            vela = velas[1]
            if not cuerpo_supera_nivel(vela, low_ref, "venta"):
                time.sleep(1)
                continue
            sl = vela['open']
            entrada = tick.bid
            tp = entrada - 2 * abs(entrada - sl)
            lot_size = calcular_lote(balance, risk_pct_loss, entrada, sl)
            abrir_operacion("venta", entrada, sl, tp, lot_size)
            operaciones_realizadas.add(hoy)
            time.sleep(60 * 10)

    time.sleep(1)
