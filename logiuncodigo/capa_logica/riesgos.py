"""MATRIZ DE RIESGOS ÉTICOS: puntaje = probabilidad x impacto (1-25), antes y después de mitigar.

Niveles (los del script original): 1-4 bajo | 5-9 medio | 10-16 alto | 17-25 crítico.
"""
from datetime import datetime

from capa_datos import basedatos as bd

CATEGORIAS = ["sesgo", "privacidad", "transparencia", "seguridad", "responsabilidad",
              "alucinacion", "automatizacion", "otro"]


def nivel(puntaje, umbral_critico=17):
    if puntaje >= umbral_critico:
        return "crítico"
    if puntaje >= 10:
        return "alto"
    return "medio" if puntaje >= 5 else "bajo"


def validar(prob, imp, prob_r, imp_r):
    for nombre, v in (("probabilidad", prob), ("impacto", imp),
                      ("probabilidad residual", prob_r), ("impacto residual", imp_r)):
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            raise ValueError(f"{nombre} debe ser un entero entre 1 y 5")
    if prob_r * imp_r > prob * imp:
        raise ValueError("El riesgo residual no puede ser mayor que el inherente: revisa la mitigación.")


def documento(modulo, descripcion, categoria, prob, imp, mitigacion, prob_r, imp_r):
    if not modulo.strip() or not descripcion.strip():
        raise ValueError("Módulo y descripción son obligatorios.")
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoría inválida. Usa una de: {', '.join(CATEGORIAS)}")
    validar(prob, imp, prob_r, imp_r)
    pi, pr = prob * imp, prob_r * imp_r
    return {"modulo": modulo.strip(), "descripcion": descripcion.strip(), "categoria": categoria,
            "probabilidad": prob, "impacto": imp, "puntaje_inherente": pi, "nivel_inherente": nivel(pi),
            "mitigacion": mitigacion.strip(), "probabilidad_residual": prob_r, "impacto_residual": imp_r,
            "puntaje_residual": pr, "nivel_residual": nivel(pr),
            "reduccion_pct": round(100 * (pi - pr) / pi, 1),
            "historico": [{"fecha": datetime.now(), "evento": "alta", "inherente": pi, "residual": pr}]}


def editar(_id, usuario="operador", **cambios):
    actual = bd.obtener("riesgos_eticos", _id)
    if not actual:
        raise ValueError("El riesgo ya no existe.")
    actual.update(cambios)
    nuevo = documento(actual["modulo"], actual["descripcion"], actual["categoria"], actual["probabilidad"],
                      actual["impacto"], actual["mitigacion"], actual["probabilidad_residual"],
                      actual["impacto_residual"])
    nuevo["historico"] = actual.get("historico", []) + [
        {"fecha": datetime.now(), "evento": f"edición por {usuario}",
         "inherente": nuevo["puntaje_inherente"], "residual": nuevo["puntaje_residual"]}]
    nuevo["marca_tiempo"] = actual.get("marca_tiempo", datetime.now())
    bd.reemplazar("riesgos_eticos", _id, nuevo)


# (módulo, descripción, categoría, P, I, mitigación, P residual, I residual)
RIESGOS_DEMO = [
    # --- del script original ---
    ("Cámara de Detección de Somnolencia", "Sesgo en visión nocturna (falsos positivos por tono de piel o poca luz)",
     "sesgo", 4, 4, "Entrenar y auditar con datos nocturnos y diversos; umbral ajustable; revisión humana", 2, 4),
    ("Cámara de Detección de Somnolencia", "Violación de privacidad por video continuo del conductor",
     "privacidad", 4, 5, "Procesar en el borde, no almacenar video, aviso y consentimiento", 2, 4),
    ("Lector de Placas (LPR)", "Lectura errónea que niega el acceso injustificadamente",
     "responsabilidad", 3, 3, "Revisión humana y canal de apelación", 2, 2),
    ("Lector de Placas (LPR)", "Conservación indebida de datos de placas",
     "privacidad", 2, 4, "Política de retención y cifrado", 1, 4),
    # --- riesgos de la nueva implementación (obligatorios) ---
    ("Clasificador LLM", "Alucinaciones: el LLM inventa categorías, placas o pesos que no están en el correo",
     "alucinacion", 4, 4, "JSON validado con pydantic, reintentos, verificación de entidades contra el texto, "
     "respaldo por reglas y revisión humana cuando discrepan", 2, 3),
    ("Clasificador LLM", "Sesgo con correos de ortografía informal: se clasifican peor que los formales",
     "sesgo", 3, 4, "Normalizar texto, medir exactitud separada en correos informales del experimento, "
     "ante la duda elegir la prioridad más alta", 2, 3),
    ("Datos del conductor", "Privacidad de datos del conductor (certificación, identidad, historial)",
     "privacidad", 3, 5, "Guardar solo folio y vigencia, sin nombre ni documentos; credenciales en .env; "
     "acceso restringido al clúster", 2, 3),
    ("Motor de decisión", "Dependencia excesiva de la automatización: el operador acepta la decisión sin revisar",
     "automatizacion", 4, 4, "Mostrar siempre la explicación paso a paso, marcar revisión humana, "
     "permitir editar el resultado y registrar quién decide", 3, 3),
    ("Asistente RAG", "El asistente responde con información no respaldada por la base de datos",
     "alucinacion", 3, 4, "Solo responde con registros recuperados, cita la fuente y contesta "
     "'no tengo información' sin consultar al LLM cuando no hay datos", 1, 3),
    ("Clasificador de Incidentes", "Priorizar mal un incidente crítico (falso negativo)",
     "seguridad", 2, 5, "Palabras críticas siempre escalan; en discrepancia gana la prioridad más alta", 1, 5),
]
