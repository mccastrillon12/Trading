import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import pandas as pd
import time

# === CONFIGURACIÓN GENERAL ===
symbol = "EURUSD"
timeframe_m1 = mt5.TIMEFRAME_M1
timeframe_m15 = mt5.TIMEFRAME_M15
risk_pct_loss = 0.01

# === CONEXIÓN A MT5 ===
if not mt5.initialize():
    print("❌ Error al conectar con MT5:", mt5.last_error())
    quit()
print("✅ Conectado a MT5")

# === FUNCIONES AUXILIARES ===

def calcular_zigzag(df, tramos=2):
    pivotes = []
    for i in range(tramos, len(df) - tramos):
        es_alto = all(df.loc[i, 'high'] > df.loc[i - j, 'high'] and df.loc[i, 'high'] > df.loc[i + j, 'high'] for j in range(1, tramos + 1))
        es_bajo = all(df.loc[i, 'low'] < df.loc[i - j, 'low'] and df.loc[i, 'low'] < df.loc[i + j, 'low'] for j in range(1, tramos + 1))
        if es_alto:
            pivotes.append({'tipo': 'alto', 'valor': df.loc[i, 'high'], 'tiempo': df.loc[i, 'time']})
        elif es_bajo:
            pivotes.append({'tipo': 'bajo', 'valor': df.loc[i, 'low'], 'tiempo': df.loc[i, 'time']})
    return pd.DataFrame(pivotes)

def calcular_lote(entrada, sl):
    cuenta = mt5.account_info()
    if cuenta is None:
        print("⚠️ No se pudo obtener la información de la cuenta.")
        return 0

    capital_actual = cuenta.balance
    riesgo_monetario = capital_actual * risk_pct_loss
    valor_pip = 10  # Para EURUSD, 1 lote estándar = $10 por pip
    riesgo_pips = abs(entrada - sl) * 10000
    return round(riesgo_monetario / (riesgo_pips * valor_pip), 2) if riesgo_pips != 0 else 0

def ejecutar_orden(tipo, entrada, sl, tp, lote):
    tipo_orden = mt5.ORDER_TYPE_BUY if tipo == 'compra' else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(symbol).ask if tipo == 'compra' else mt5.symbol_info_tick(symbol).bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lote,
        "type": tipo_orden,
        "price": price,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "deviation": 10,
        "magic": 234000,
        "comment": "Breakout en vivo",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ {tipo.upper()} ejecutada a {round(price,5)} | TP: {round(tp,5)} | SL: {round(sl,5)}")
    else:
        print(f"❌ Error al ejecutar orden: {result.retcode} | {result.comment}")

# === HORA SERVIDOR (desde vela M1) ===
def obtener_hora_servidor():
    velas = mt5.copy_rates_from_pos(symbol, timeframe_m1, 0, 1)
    if velas is None or len(velas) == 0:
        return None
    return datetime.fromtimestamp(velas[0]['time'], tz=timezone.utc)

# === OBTENER NIVELES DE RUPTURA (pivotes M15) ===
def obtener_niveles_ruptura():
    now = obtener_hora_servidor()
    if now is None:
        return (None, None)

    hoy_3am = now.replace(hour=3, minute=0, second=0, microsecond=0).replace(tzinfo=None)

    desde = hoy_3am - timedelta(hours=24)
    datos_m15 = mt5.copy_rates_range(symbol, timeframe_m15, desde, hoy_3am)

    df_15m = pd.DataFrame(datos_m15)
    df_15m['time'] = pd.to_datetime(df_15m['time'], unit='s')

    zigzag = calcular_zigzag(df_15m)
    zigzag = zigzag[zigzag['tiempo'] < hoy_3am]  # Solo pivotes antes de las 3:00am exactas

    ult_alto = zigzag[zigzag['tipo'] == 'alto'].iloc[-1] if not zigzag[zigzag['tipo'] == 'alto'].empty else None
    ult_bajo = zigzag[zigzag['tipo'] == 'bajo'].iloc[-1] if not zigzag[zigzag['tipo'] == 'bajo'].empty else None

    if ult_alto is not None and ult_bajo is not None:
        print(f"📈 Último ALTO antes de las 3:00am: {round(ult_alto['valor'], 5)} a las {ult_alto['tiempo'].strftime('%H:%M:%S')}")
        print(f"📉 Último BAJO antes de las 3:00am: {round(ult_bajo['valor'], 5)} a las {ult_bajo['tiempo'].strftime('%H:%M:%S')}")
        return (ult_alto['valor'], ult_bajo['valor'])
    else:
        print("❌ No se encontraron pivotes antes de las 3:00am.")
        return (None, None)

def detectar_primera_ruptura_m1(high_ref, low_ref, desde):
    hasta = obtener_hora_servidor()
    datos_m1 = mt5.copy_rates_range(symbol, timeframe_m1, desde, hasta)

    if datos_m1 is None or len(datos_m1) == 0:
        print("⚠️ No se pudieron obtener velas M1 para detectar ruptura.")
        return None, None

    for vela in datos_m1:
        time_utc = datetime.fromtimestamp(vela['time'], tz=timezone.utc)
        if vela['high'] > high_ref:
            return "alcista", time_utc
        elif vela['low'] < low_ref:
            return "bajista", time_utc
    return None, None

# === EJECUCIÓN EN TIEMPO REAL ===
print("⏳ Esperando que sea hora de operar (3:00am servidor)...")
sesion_iniciada = False
niveles_establecidos = False
high_ref, low_ref = None, None
ultimo_aviso_fuera_de_horario = datetime.min.replace(tzinfo=timezone.utc)
ultima_impresion = None

while True:
    now = obtener_hora_servidor()
    if now is None:
        print("⚠️ No se pudo obtener hora del servidor. Reintentando...")
        time.sleep(60)
        continue

    if 3 <= now.hour < 5:
        if not sesion_iniciada:
            print(f"\n🕒 Inicia sesión de trading (Hora servidor UTC): {now.strftime('%H:%M:%S')}")
            if not niveles_establecidos:
                high_ref, low_ref = obtener_niveles_ruptura()
                
                if high_ref is not None and low_ref is not None:
                    print(f"📈 Nivel resistencia (High M15): {round(high_ref, 5)}")
                    print(f"📉 Nivel soporte (Low M15):     {round(low_ref, 5)}")
                    niveles_establecidos = True
                                    # Buscar primera vela que rompió
                hoy_3am = now.replace(hour=3, minute=0, second=0, microsecond=0).replace(tzinfo=timezone.utc)
                tipo, hora_ruptura = detectar_primera_ruptura_m1(high_ref, low_ref, hoy_3am)
                if tipo and hora_ruptura:
                    if tipo == "alcista":
                        print(f"🚀 Primera ruptura ALCISTA detectada en vela de las {hora_ruptura.strftime('%H:%M:%S')} (UTC)")
                    else:
                        print(f"📉 Primera ruptura BAJISTA detectada en vela de las {hora_ruptura.strftime('%H:%M:%S')} (UTC)")
                else:
                    print("🔍 Aún no hay ruptura desde las 3:00am.")

            else:
                    print("❌ No se pudieron calcular los niveles de ruptura.")
                    time.sleep(60)
                    continue
            sesion_iniciada = True

        velas = mt5.copy_rates_from_pos(symbol, timeframe_m1, 1, 2)
        if velas is None or len(velas) < 2:
            print("⚠️ Sin datos suficientes. Esperando...")
            time.sleep(60)
            continue

        vela = velas[0]
        high = vela['high']
        low = vela['low']
        vela_time = datetime.fromtimestamp(vela['time'], tz=timezone.utc)

        if high_ref is not None and high > high_ref:
            entrada = mt5.symbol_info_tick(symbol).ask
            sl = low
            riesgo = abs(entrada - sl)
            tp = entrada + 2 * riesgo
            lote = calcular_lote(entrada, sl)
            ejecutar_orden("compra", entrada, sl, tp, lote)
            print(f"📍 Rompimiento ALCISTA detectado en vela de las {vela_time.strftime('%H:%M:%S')} (UTC)")
            break

        elif low_ref is not None and low < low_ref:
            entrada = mt5.symbol_info_tick(symbol).bid
            sl = high
            riesgo = abs(entrada - sl)
            tp = entrada - 2 * riesgo
            lote = calcular_lote(entrada, sl)
            ejecutar_orden("venta", entrada, sl, tp, lote)
            print(f"📍 Rompimiento BAJISTA detectado en vela de las {vela_time.strftime('%H:%M:%S')} (UTC)")
            break

        else:
            if ultima_impresion is None or (now - ultima_impresion).seconds >= 900:
                print(f"⏱️ [{now.strftime('%H:%M:%S')}] Sin ruptura. Esperando...")
                ultima_impresion = now
    else:
        if sesion_iniciada:
            print("🛑 Sesión finalizada. Hora fuera del rango operativo.")
            break
        else:
            if (now - ultimo_aviso_fuera_de_horario).total_seconds() >= 900:
                print(f"⏸️ Esperando horario de operación. Hora servidor: {now.strftime('%H:%M:%S')} (UTC)")
                ultimo_aviso_fuera_de_horario = now

    time.sleep(60)

# === CERRAR CONEXIÓN ===
mt5.shutdown()
