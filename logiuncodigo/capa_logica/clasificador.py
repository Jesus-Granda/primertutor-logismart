"""CLASIFICADOR HÍBRIDO de incidentes (reglas + LLM).

1. Clasificador por reglas: el del script original (palabras clave + escalamiento por urgencia)
   y el extractor de datos con expresiones regulares (nunca inventa: si no encuentra, None).
2. Clasificador LLM: devuelve JSON con el esquema exacto, validado con pydantic.
   Si el JSON es inválido se reintenta; si sigue fallando, se usa el de reglas.
3. Fusión: si discrepan, prevalece la prioridad más alta (ante empate, la categoría de
   seguridad) y se marca requiere_revision_humana.
"""
import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

import configuracion
from capa_datos import basedatos as bd
from capa_logica import llm

# ------------------------------------------------------------ catálogos
CATEGORIAS = {
    "materiales_peligrosos": ["peligroso", "derrame", "fuga", "quimico", "inflamable", "toxico", "corrosivo"],
    "sobrepeso": ["sobrepeso", "excede", "bascula", "exceso de peso", "sobrecarga"],
    "acceso_no_autorizado": ["sin autorizacion", "no autorizado", "acceso denegado", "barrera", "intruso"],
    "falla_hardware": ["camara", "sensor", "lector", "rfid", "no enciende", "apagado", "danado", "falla electrica"],
    "falla_software": ["sistema", "error", "pantalla", "caido", "no carga", "lento", "software", "aplicacion"],
    "somnolencia_conductor": ["somnolencia", "dormido", "cansancio", "fatiga", "sueno"],
}
LISTA_CATEGORIAS = list(CATEGORIAS) + ["otro"]
PALABRAS_URGENTES = ["urgente", "emergencia", "accidente", "incendio", "herido", "critico", "inmediato"]
PRIORIDAD_BASE = {
    "materiales_peligrosos": "critica", "somnolencia_conductor": "alta", "acceso_no_autorizado": "alta",
    "sobrepeso": "media", "falla_hardware": "media", "falla_software": "baja", "otro": "baja",
}
ORDEN_PRIORIDAD = ["baja", "media", "alta", "critica"]
CATEGORIAS_SEGURIDAD = ["materiales_peligrosos", "somnolencia_conductor", "acceso_no_autorizado"]

CategoriaT = Literal["materiales_peligrosos", "sobrepeso", "acceso_no_autorizado", "falla_hardware",
                     "falla_software", "somnolencia_conductor", "otro"]
PrioridadT = Literal["baja", "media", "alta", "critica"]


def normalizar(texto):
    return texto.lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))


# ------------------------------------------------------------ esquema pydantic
class Entidades(BaseModel):
    """Las cuatro claves son obligatorias (pueden valer null) y no se aceptan claves extra."""
    model_config = ConfigDict(extra="forbid")
    placa: Optional[str]
    camion_id: Optional[str]
    peso_reportado_kg: Optional[float]
    ubicacion: Optional[str]

    @field_validator("placa", "camion_id", mode="before")
    @classmethod
    def _mayus(cls, v):
        return str(v).strip().upper() if v not in (None, "", "null") else None

    @field_validator("ubicacion", mode="before")
    @classmethod
    def _min(cls, v):
        return str(v).strip().lower() if v not in (None, "", "null") else None

    @field_validator("peso_reportado_kg", mode="before")
    @classmethod
    def _peso(cls, v):
        if v in (None, "", "null"):
            return None
        if isinstance(v, str):
            v = re.sub(r"[^\d.,]", "", v)
            if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", v):      # 52,000 o 48,500.5 (miles con coma)
                v = v.replace(",", "")
            elif re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", v):    # 52.000 o 48.500,5 (miles con punto)
                v = v.replace(".", "").replace(",", ".")
            else:                                                  # 48,5 o 48.5
                v = v.replace(",", ".")
        return float(v)


class Clasificacion(BaseModel):
    """Esquema EXACTO que debe devolver el LLM: categoria, prioridad, entidades y resumen, nada más."""
    model_config = ConfigDict(extra="forbid")
    categoria: CategoriaT
    prioridad: PrioridadT
    entidades: Entidades
    resumen: str = Field(min_length=3, max_length=300)

    @field_validator("categoria", "prioridad", mode="before")
    @classmethod
    def _norm(cls, v):
        return normalizar(str(v)).strip().replace(" ", "_") if v is not None else v


# ------------------------------------------------------------ reglas (original)
def clasificar_reglas(asunto, cuerpo):
    texto = normalizar(f"{asunto} {cuerpo}")
    puntajes = {cat: [kw for kw in kws if kw in texto] for cat, kws in CATEGORIAS.items()}
    mejor = max(puntajes, key=lambda c: len(puntajes[c]))  # empate: gana la primera (seguridad)
    coincidencias = puntajes[mejor]
    if not coincidencias:
        mejor = "otro"
    prioridad = PRIORIDAD_BASE[mejor]
    urgentes = [p for p in PALABRAS_URGENTES if p in texto]
    if urgentes:
        prioridad = ORDEN_PRIORIDAD[min(ORDEN_PRIORIDAD.index(prioridad) + 1, 3)]
    resumen = (asunto.strip() or cuerpo.strip()[:120] or "sin texto")[:300]
    return Clasificacion(categoria=mejor, prioridad=prioridad, entidades=extraer_datos(asunto, cuerpo),
                         resumen=resumen), coincidencias + urgentes


def extraer_datos(asunto, cuerpo):
    """Extrae entidades con expresiones regulares (no inventa: lo no encontrado queda en None)."""
    texto = f"{asunto}\n{cuerpo}"
    m_placa = re.search(r"\b[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}\b", texto.upper())
    m_camion = re.search(r"\bCAM-\d+\b", texto.upper())
    m_peso = re.search(r"(\d+(?:[.,]\d+)?)\s*(toneladas|tonelada|ton|t|kg)\b", texto.lower())
    peso = None
    if m_peso:
        valor = float(m_peso.group(1).replace(",", "."))
        peso = valor if m_peso.group(2) == "kg" else valor * 1000
    m_ubic = re.search(r"\b(and[eé]n|puerta|muelle|caseta|dock)\s+([A-Za-z0-9]+)", texto, re.IGNORECASE)
    return Entidades(placa=m_placa.group(0) if m_placa else None,
                     camion_id=m_camion.group(0) if m_camion else None,
                     peso_reportado_kg=peso,
                     ubicacion=f"{m_ubic.group(1)} {m_ubic.group(2)}" if m_ubic else None)


# ------------------------------------------------------------ LLM
PROMPT_CLASIFICADOR = """Eres el clasificador de incidentes del centro logístico LogiSmart.
Lee el correo y responde SOLO con un objeto JSON con exactamente estas claves:
{
  "categoria": una de ["materiales_peligrosos", "sobrepeso", "acceso_no_autorizado", "falla_hardware",
                       "falla_software", "somnolencia_conductor", "otro"],
  "prioridad": una de ["baja", "media", "alta", "critica"],
  "entidades": {"placa": texto o null, "camion_id": texto o null,
                "peso_reportado_kg": número o null, "ubicacion": texto o null},
  "resumen": "resumen de máximo 25 palabras"
}
Reglas:
- materiales_peligrosos (derrames, fugas, químicos) siempre es "critica".
- somnolencia_conductor y acceso_no_autorizado son al menos "alta".
- Si hay palabras como urgente, emergencia, accidente, herido o incendio, sube la prioridad.
- Copia placa (formato ABC-123-D) y camion_id (formato CAM-###) EXACTAMENTE como aparecen; si no aparecen, usa null.
- Convierte toneladas a kilogramos. NO inventes datos que no estén en el correo.
- El correo puede tener faltas de ortografía. Ante la duda, elige la prioridad más alta."""


def _verificar_entidades(c, asunto, cuerpo):
    """Anti-alucinación: descarta placas o IDs que el LLM devolvió pero no aparecen en el texto."""
    texto = f"{asunto} {cuerpo}".upper()
    avisos = []
    e = c.entidades
    for campo in ("placa", "camion_id"):
        valor = getattr(e, campo)
        if valor and valor not in texto:
            avisos.append(f"El LLM devolvió {campo}={valor} que no aparece en el correo (descartado).")
            setattr(e, campo, None)
    return avisos


def clasificar_llm(asunto, cuerpo, modelo=None, reintentos=None):
    """Devuelve (Clasificacion | None, latencia_total, respuesta_cruda, intentos, error)."""
    reintentos = configuracion.cargar_ajustes()["reintentos"] if reintentos is None else reintentos
    msgs = [{"role": "system", "content": PROMPT_CLASIFICADOR},
            {"role": "user", "content": f"ASUNTO: {asunto}\nCUERPO: {cuerpo}"}]
    total, crudo, error = 0.0, "", None
    for intento in range(1, reintentos + 2):
        crudo, lat = llm.chat(msgs, modelo, json_mode=True)
        total += lat
        try:
            return Clasificacion(**json.loads(crudo)), total, crudo, intento, None
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            error = f"JSON inválido en el intento {intento}: {str(e)[:200]}"
            msgs.append({"role": "assistant", "content": crudo})
            msgs.append({"role": "user", "content": "Tu respuesta no cumple el esquema. Responde SOLO el JSON válido."})
    return None, total, crudo, reintentos + 1, error


# ------------------------------------------------------------ fusión
def fusionar(reg, llm_c):
    """Devuelve (final, metodo, requiere_revision_humana, motivo)."""
    if llm_c is None:
        return reg, "reglas (respaldo)", False, "El LLM no devolvió un JSON válido: se usó el clasificador por reglas."
    if llm_c.categoria == reg.categoria and llm_c.prioridad == reg.prioridad:
        return _completar(llm_c, reg), "híbrido (coinciden)", False, "LLM y reglas coinciden."
    n_llm, n_reg = ORDEN_PRIORIDAD.index(llm_c.prioridad), ORDEN_PRIORIDAD.index(reg.prioridad)
    if n_llm > n_reg:
        final, motivo = llm_c, "prevalece el LLM por tener prioridad más alta"
    elif n_reg > n_llm:
        final, motivo = reg, "prevalecen las reglas por tener prioridad más alta"
    else:  # misma prioridad, distinta categoría: ante la duda, seguridad
        if reg.categoria in CATEGORIAS_SEGURIDAD and llm_c.categoria not in CATEGORIAS_SEGURIDAD:
            final, motivo = reg, "misma prioridad; se elige la categoría de seguridad (reglas)"
        else:
            final, motivo = llm_c, "misma prioridad; se conserva la categoría del LLM"
    return _completar(final, reg if final is llm_c else llm_c), "híbrido (discrepan)", True, \
        f"LLM: {llm_c.categoria}/{llm_c.prioridad} vs reglas: {reg.categoria}/{reg.prioridad}; {motivo}."


def _completar(final, otro):
    """Rellena entidades vacías con las del otro clasificador (regex nunca inventa)."""
    datos = final.model_copy(deep=True)
    for campo in Entidades.model_fields:
        if getattr(datos.entidades, campo) is None:
            setattr(datos.entidades, campo, getattr(otro.entidades, campo))
    return datos


def hibrido(asunto, cuerpo, modelo=None, reintentos=None, guardar=True, origen="bandeja"):
    reg, palabras = clasificar_reglas(asunto, cuerpo)
    llm_c, lat, crudo, intentos, error = None, 0.0, "", 0, None
    avisos = []
    try:
        llm_c, lat, crudo, intentos, error = clasificar_llm(asunto, cuerpo, modelo, reintentos)
        if llm_c:
            avisos = _verificar_entidades(llm_c, asunto, cuerpo)
    except llm.ErrorLLM as e:
        error = str(e)
    final, metodo, revision, motivo = fusionar(reg, llm_c)
    modelo_usado = modelo or configuracion.cargar_ajustes()["modelo"]
    resultado = {**final.model_dump(), "metodo": metodo, "requiere_revision_humana": revision,
                 "motivo_fusion": motivo, "palabras_clave": palabras, "avisos": avisos,
                 "llm": llm_c.model_dump() if llm_c else None, "reglas": reg.model_dump(),
                 "latencia_llm_s": round(lat, 2), "intentos_llm": intentos, "error_llm": error}
    if guardar:
        try:
            bd.insertar("evaluaciones_llm", {
                "origen": origen, "prompt": PROMPT_CLASIFICADOR,
                "entrada": f"ASUNTO: {asunto}\nCUERPO: {cuerpo}", "respuesta": crudo, "modelo": modelo_usado,
                "latencia_s": round(lat, 3), "intentos": intentos, "json_valido": llm_c is not None,
                "coincidio_reglas": None if llm_c is None else (llm_c.categoria == reg.categoria
                                                                and llm_c.prioridad == reg.prioridad),
                "categoria_llm": llm_c.categoria if llm_c else None, "categoria_reglas": reg.categoria,
                "error": error})
        except bd.ErrorBD:
            pass  # la clasificación no debe fallar si la bitácora no se puede escribir
    return resultado


def documento_incidente(asunto, cuerpo, clasificacion, metodo, revision, palabras, estado="nuevo",
                        historial=None, marca_tiempo=None):
    """Arma el documento de la colección 'incidentes': correo original, clasificación,
    datos extraídos, estado e historial."""
    from datetime import datetime
    return {"correo_original": {"asunto": asunto, "cuerpo": cuerpo},
            "clasificacion": {"categoria": clasificacion.categoria, "prioridad": clasificacion.prioridad,
                              "resumen": clasificacion.resumen, "metodo": metodo,
                              "requiere_revision_humana": revision, "palabras_clave": palabras},
            "datos_extraidos": clasificacion.entidades.model_dump(),
            "estado": estado, "historial": historial or [], "marca_tiempo": marca_tiempo or datetime.now()}
