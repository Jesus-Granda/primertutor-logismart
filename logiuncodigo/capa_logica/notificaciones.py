"""Notificación de incidentes a soporte por correo (del script original).

Por defecto es SIMULADO (no se conecta a ningún servidor). Para envío real define
SMTP_HOST, SMTP_PORT, SMTP_USER y SMTP_PASSWORD en el .env y desactiva la simulación.
"""
import os
import smtplib
from email.message import EmailMessage


def enviar_correo_soporte(asunto, cuerpo, destinatario="soporte@logismart.example",
                          remitente="logismart@logismart.example", simulacion=True):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = remitente, destinatario, asunto
    msg.set_content(cuerpo)
    if simulacion:
        return {"enviado": True, "modo": "simulacion", "destinatario": destinatario, "error": None}
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
        return {"enviado": True, "modo": "smtp", "destinatario": destinatario, "error": None}
    except (KeyError, OSError, smtplib.SMTPException) as e:
        return {"enviado": False, "modo": "smtp", "destinatario": destinatario, "error": f"{type(e).__name__}: {e}"}
