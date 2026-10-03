"""ASISTENTE EXPLICATIVO con RAG sencillo: primero consulta MongoDB, después da el contexto al LLM.

- El LLM solo puede responder con los registros recuperados y debe citarlos.
- Si no hay datos, la respuesta es fija ("No tengo información...") SIN llamar al modelo.
- Si Ollama no responde, se muestra lo que dicen los registros (plan de respaldo).
- Cada llamada al LLM queda registrada en la colección evaluaciones_llm.
"""
import json
import re

import configuracion
from capa_datos import basedatos as bd
from capa_logica import llm

SIN_INFO = "No tengo información sobre eso en la base de datos."

SISTEMA = f"""Eres el asistente del centro de control LogiSmart. Respondes preguntas del operador
usando ÚNICAMENTE los registros del CONTEXTO (vienen de MongoDB).
Reglas:
1. Cita la fuente de cada dato entre corchetes, por ejemplo [accesos/66f1a2...].
2. Para explicar una decisión de acceso usa el campo 'explicacion' (causas y pasos) del registro.
3. Si el contexto no contiene la respuesta, responde exactamente: "{SIN_INFO}"
4. No inventes placas, fechas, pesos ni decisiones. Responde en español, en pocas líneas.
Significado de premisas: P autorización previa, Q peso excede el límite, R materiales peligrosos,
S certificación vigente, H dentro de horario para peligrosos, F fatiga del conductor."""

CAMPOS = {
    "camiones": ("camion_id", "placa", "empresa", "autorizacion", "certificacion_conductor"),
    "accesos": ("camion_id", "placa", "P", "Q", "R", "S", "H", "F", "A", "E", "decision", "explicacion",
                "peso_kg", "limite_kg", "operador", "marca_tiempo"),
    "incidentes": ("correo_original", "clasificacion", "datos_extraidos", "estado", "marca_tiempo"),
    "riesgos_eticos": ("modulo", "descripcion", "categoria", "puntaje_inherente", "puntaje_residual", "mitigacion"),
}


def _ids(pregunta):
    t = pregunta.upper()
    return (set(re.findall(r"\bCAM-\d+\b", t)), set(re.findall(r"\b[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}\b", t)))


def _filtro_accesos(q):
    """Filtro de accesos según lo que se pregunta (denegados, inspección, estándar)."""
    if "denegad" in q or "rechaz" in q:
        return {"decision": "ACCESO DENEGADO"}
    if "inspecci" in q:
        return {"E": True}
    if "estándar" in q or "estandar" in q or "permitid" in q:
        return {"A": True}
    return {}


def recuperar(pregunta, limite=4):
    """Paso 1 del RAG: consulta MongoDB. Devuelve [(fuente, documento_reducido)]."""
    camiones, placas = _ids(pregunta)
    q = pregunta.lower()
    docs = []

    def agregar(col, filtro, n=limite):
        for d in bd.listar(col, filtro, limite=n):
            docs.append((f"{col}/{d['_id']}", {k: d[k] for k in CAMPOS[col] if k in d}))

    filtro_acc = _filtro_accesos(q)
    for cid in camiones:
        agregar("camiones", {"camion_id": cid}, 1)
        agregar("accesos", {"camion_id": cid, **filtro_acc})
        agregar("incidentes", {"datos_extraidos.camion_id": cid}, 3)
    for pl in placas:
        agregar("camiones", {"placa": pl}, 1)
        agregar("accesos", {"placa": pl, **filtro_acc})
        agregar("incidentes", {"datos_extraidos.placa": pl}, 3)
    if not (camiones or placas):
        if "riesgo" in q:
            filtro = {"puntaje_residual": {"$gte": configuracion.cargar_ajustes()["umbral_critico"]}} \
                if "crític" in q or "critic" in q else {}
            agregar("riesgos_eticos", filtro, 10)
        if "incidente" in q or "correo" in q:
            filtro = {"estado": {"$ne": "cerrado"}} if ("abierto" in q or "pendiente" in q) else {}
            agregar("incidentes", filtro, 8)
        if "acceso" in q or "camion" in q or "camión" in q or filtro_acc:
            agregar("accesos", filtro_acc, 8)
    vistos, unicos = set(), []
    for f, d in docs:
        if f not in vistos:
            vistos.add(f)
            unicos.append((f, d))
    return unicos


def _respaldo(docs):
    """Plan de respaldo si Ollama no responde: lo que dicen los registros, sin redactar."""
    lineas = ["El modelo no está disponible; esto es lo que dicen los registros:"]
    for f, d in docs:
        if f.startswith("accesos/"):
            causas = " ".join(d.get("explicacion", {}).get("causas", []))
            lineas.append(f"- {d.get('camion_id') or d.get('placa')}: {d.get('decision')}. {causas} [{f}]")
        elif f.startswith("incidentes/"):
            cl = d.get("clasificacion", {})
            lineas.append(f"- Incidente «{d.get('correo_original', {}).get('asunto', '')}»: {cl.get('categoria')}, "
                          f"prioridad {cl.get('prioridad')}, estado {d.get('estado')} [{f}]")
        elif f.startswith("camiones/"):
            lineas.append(f"- {d.get('camion_id')} ({d.get('placa')}), {d.get('empresa')} [{f}]")
        elif f.startswith("riesgos_eticos/"):
            lineas.append(f"- {d.get('modulo')}: {d.get('descripcion')} (residual {d.get('puntaje_residual')}) [{f}]")
    return "\n".join(lineas)


def responder(pregunta, historial=None, modelo=None):
    """Devuelve (respuesta, fuentes, latencia_s)."""
    docs = recuperar(pregunta)
    if not docs:
        return SIN_INFO, [], 0.0
    contexto = "\n".join(f"[{f}] {json.dumps(bd.limpiar(d), ensure_ascii=False)}" for f, d in docs)
    msgs = [{"role": "system", "content": SISTEMA}]
    for h in (historial or [])[-4:]:
        msgs.append({"role": h["rol"], "content": h["texto"]})
    msgs.append({"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"})
    fuentes = [f for f, _ in docs]
    modelo_usado = modelo or configuracion.cargar_ajustes()["modelo"]
    try:
        texto, lat = llm.chat(msgs, modelo)
        error = None
    except llm.ErrorLLM as e:
        texto, lat, error = _respaldo(docs), 0.0, str(e)
    try:
        bd.insertar("evaluaciones_llm", {
            "origen": "asistente", "prompt": SISTEMA, "entrada": msgs[-1]["content"], "respuesta": texto,
            "modelo": modelo_usado, "latencia_s": round(lat, 3), "json_valido": None, "coincidio_reglas": None,
            "fuentes": fuentes, "error": error})
    except bd.ErrorBD:
        pass
    return texto.strip(), fuentes, lat
