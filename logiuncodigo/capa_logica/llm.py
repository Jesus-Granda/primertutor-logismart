"""Servicio LLM: acceso a Ollama con medición de latencia y errores amigables."""
import time

import ollama

import configuracion

KEEP_ALIVE = "30m"


class ErrorLLM(Exception):
    """Error amigable al usar Ollama; `detalle` guarda el error técnico original."""

    def __init__(self, mensaje, detalle=""):
        super().__init__(mensaje)
        self.detalle = detalle


def chat(mensajes, modelo=None, json_mode=False, temperatura=None):
    """Envía mensajes a Ollama. Devuelve (texto, latencia_en_segundos)."""
    modelo = modelo or configuracion.cargar_ajustes()["modelo"]
    t0 = time.perf_counter()
    try:
        r = ollama.chat(model=modelo, messages=mensajes, format="json" if json_mode else None,
                        keep_alive=KEEP_ALIVE,
                        options={"temperature": 0 if json_mode else (temperatura or 0.2), "num_ctx": 4096})
    except Exception as e:
        texto = str(e)
        if "not found" in texto.lower():
            raise ErrorLLM(f"El modelo '{modelo}' no está descargado. En una terminal ejecuta: ollama pull {modelo}", texto)
        raise ErrorLLM("No se pudo conectar con Ollama. Abre la aplicación de Ollama y vuelve a intentar.", texto)
    return r["message"]["content"], time.perf_counter() - t0


def modelos_disponibles():
    try:
        return sorted(m.model for m in ollama.list().models)
    except Exception:
        return []
