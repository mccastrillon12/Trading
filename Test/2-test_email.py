import smtplib
from email.message import EmailMessage

EMAIL_FROM = "castrillonosorio12@gmail.com"
EMAIL_TO = "castrillonosorio12@gmail.com"
EMAIL_PASS = "qknwerxaoalerbtn"  # muy importante

def enviar_correo(asunto, cuerpo):
    try:
        msg = EmailMessage()
        msg['Subject'] = asunto
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg.set_content(cuerpo)

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_FROM, EMAIL_PASS)
            smtp.send_message(msg)
            print("✅ Correo enviado correctamente")
    except Exception as e:
        print("❌ Error al enviar correo:", str(e))

# Ejecutar prueba
enviar_correo("🔔 Prueba", "Este es un mensaje de prueba desde el script.")