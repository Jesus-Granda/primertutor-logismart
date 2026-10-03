"""Configuración global: credenciales (.env) y ajustes editables desde la GUI (ajustes.json)."""
import json
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()
RUTA_AJUSTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ajustes.json")

AJUSTES_DEF = {
    "modelo": os.getenv("OLLAMA_MODEL", "llama3.2"),
    "umbral_critico": 17,          # puntaje residual >= umbral -> riesgo crítico (matriz original 17-25)
    "reintentos": 2,               # reintentos del LLM si el JSON es inválido
    "peso_max_kg": 45000,          # límite de la báscula para Q (exceso de peso)
    "horario_peligrosos": [6, 18], # horario permitido para materiales peligrosos (hora inicio, hora fin)
    "simulacion_correo": True,     # notificaciones a soporte simuladas (sin SMTP real)
}


def mongo_uri():
    if os.getenv("MONGO_URI"):
        return os.getenv("MONGO_URI")
    u, p, c = os.getenv("MONGO_USER"), os.getenv("MONGO_PASSWORD"), os.getenv("MONGO_CLUSTER")
    if not (u and p and c):
        return None
    return f"mongodb+srv://{quote_plus(u)}:{quote_plus(p)}@{c}/?retryWrites=true&w=majority&appName=logismart"


MONGO_DB = os.getenv("MONGO_DB", "logismart")


def cargar_ajustes():
    datos = dict(AJUSTES_DEF)
    try:
        with open(RUTA_AJUSTES, encoding="utf-8") as f:
            datos.update(json.load(f))
    except (OSError, ValueError):
        pass
    return datos


def guardar_ajustes(datos):
    with open(RUTA_AJUSTES, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
