"""EXPERIMENTO: reglas vs LLM vs híbrido sobre 30 correos etiquetados a mano.

Mide exactitud (categoría y prioridad), matriz de confusión, latencia, JSON válido y
compara correos formales vs. con ortografía informal (evidencia para el riesgo de sesgo).

Ejecutar:   python experimento.py          (tarda unos minutos; usa Ollama)
Resultado:  resultados_experimento.json  + filas en la colección evaluaciones_llm
"""
import json
import sys
import time
from datetime import datetime

import pandas as pd

import configuracion
from capa_logica import clasificador as clf
from capa_logica import llm

# (asunto, cuerpo, categoria_real, prioridad_real, informal)
DATASET = [
    # materiales peligrosos
    ("URGENTE: derrame en andén 3", "El camión CAM-102 con placas ABC-123-D presenta una fuga de químico inflamable. "
     "La báscula marcó 48.5 toneladas. Se requiere apoyo inmediato.", "materiales_peligrosos", "critica", False),
    ("Fuga en pipa", "La pipa CAM-108 tiene una fuga de gas en la puerta 2, ya acordonamos la zona.",
     "materiales_peligrosos", "critica", False),
    ("Olor raro en muelle 4", "Hay un olor muy fuerte a quimico cerca del muelle 4 y unos tambos se ven corroidos.",
     "materiales_peligrosos", "critica", False),
    ("derrame!!", "se tiro algo toxico del camion de placas XYZ-456-B en la caseta norte, huele feo y pica la garganta",
     "materiales_peligrosos", "critica", True),
    ("Carga corrosiva mal etiquetada", "El CAM-110 trae bidones de material corrosivo sin la etiqueta NOM correspondiente.",
     "materiales_peligrosos", "critica", False),
    # sobrepeso
    ("Exceso de peso en báscula", "El camión CAM-104 marcó 52 toneladas en la báscula, el límite es 45.",
     "sobrepeso", "media", False),
    ("Sobrecarga detectada", "Unidad con placas JKL-321-C viene con sobrecarga, la báscula marca 47000 kg.",
     "sobrepeso", "media", False),
    ("pesa de mas", "el trailer de la caseta sur pesa demaciado segun la bascula, ke ago lo dejo pasar?",
     "sobrepeso", "media", True),
    ("Accidente por sobrepeso", "Urgente: un camión con sobrepeso rompió el eje en el andén 1, hay un herido leve.",
     "sobrepeso", "alta", False),
    # acceso no autorizado
    ("Intruso en patio", "Vimos a una persona no autorizada brincando la barda junto al andén 5.",
     "acceso_no_autorizado", "alta", False),
    ("Camión sin autorización", "El CAM-115 intentó entrar sin autorización previa y forzó la barrera de la puerta B.",
     "acceso_no_autorizado", "alta", False),
    ("se metio un carro", "un carro particular se metio atras de un trailer sin autorizacion, urgente mandar a alguien",
     "acceso_no_autorizado", "critica", True),
    ("QR clonado", "Detectamos un QR de acceso duplicado; dos unidades distintas entraron con el mismo pase.",
     "acceso_no_autorizado", "alta", False),
    # falla de hardware
    ("Cámara LPR apagada", "La cámara del lector de placas de la caseta norte no enciende desde la mañana.",
     "falla_hardware", "media", False),
    ("Sensor RFID dañado", "El lector RFID de la puerta 2 está dañado y no lee las tarjetas.",
     "falla_hardware", "media", False),
    ("la camara no sirve", "la camara de somnolencia de la caseta 3 se apago y no prende, ya la desconecte y nada",
     "falla_hardware", "media", True),
    ("Falla eléctrica en báscula", "Hubo una falla eléctrica y el sensor de la báscula quedó apagado.",
     "falla_hardware", "media", False),
    # falla de software
    ("Sistema lento", "La aplicación de control de accesos está muy lenta al registrar camiones.",
     "falla_software", "baja", False),
    ("Error al guardar", "El sistema muestra un error al guardar la bitácora y la pantalla se congela.",
     "falla_software", "baja", False),
    ("se cayo el sistema", "no carga nada en la pantalla de la caseta, el sistema esta caido desde hace rato",
     "falla_software", "baja", True),
    ("Sistema caído en hora pico", "Urgente: el software de accesos está caído y hay fila de 20 camiones.",
     "falla_software", "media", False),
    # somnolencia
    ("Conductor con fatiga", "El conductor del CAM-103 muestra signos de fatiga según la cámara.",
     "somnolencia_conductor", "alta", False),
    ("Chofer dormido", "Encontramos al chofer de la unidad DEF-789-A dormido al volante en la fila del andén 2.",
     "somnolencia_conductor", "alta", False),
    ("se esta durmiendo", "el operador del trailer se ve con mucho sueño, cabecea y casi choca con la barrera",
     "somnolencia_conductor", "alta", True),
    ("Alerta de somnolencia", "Accidente evitado: la alerta de somnolencia detuvo al CAM-109 antes de impactar.",
     "somnolencia_conductor", "critica", False),
    # otro
    ("Horario de comedor", "¿Alguien sabe a qué hora abre el comedor para los operadores?",
     "otro", "baja", False),
    ("Solicitud de capacitación", "Quisiera inscribirme al curso de manejo defensivo del próximo mes.",
     "otro", "baja", False),
    ("Gracias", "Gracias al equipo de la caseta norte por el apoyo de ayer.",
     "otro", "baja", False),
    ("estacionamiento", "oigan donde me estaciono mientras me asignan anden, no ay lugar",
     "otro", "baja", True),
    ("Cambio de turno", "Les informo que a partir del lunes cambio al turno nocturno.",
     "otro", "baja", False),
]


def _exactitud(real, pred):
    return round(sum(a == b for a, b in zip(real, pred)) / len(real), 3)


def _matriz(real, pred):
    etiquetas = clf.LISTA_CATEGORIAS
    m = pd.crosstab(pd.Series(real, name="real"), pd.Series(pred, name="predicha"))
    m = m.reindex(index=etiquetas, columns=etiquetas + ["invalido"], fill_value=0)
    return {r: {c: int(m.loc[r, c]) for c in m.columns} for r in m.index}


def correr(modelo=None, progreso=print, avance=None):
    """Corre el experimento. `progreso(texto)` recibe una línea por correo; `avance(i, n)` sirve para
    barras de progreso (la interfaz gráfica lo usa)."""
    if not llm.modelos_disponibles():
        raise llm.ErrorLLM("Ollama no responde. Ábrelo y vuelve a correr el experimento.")
    filas = []
    for i, (asunto, cuerpo, cat, pri, informal) in enumerate(DATASET, 1):
        t0 = time.perf_counter()
        reg, _ = clf.clasificar_reglas(asunto, cuerpo)
        lat_reg = time.perf_counter() - t0
        r = clf.hibrido(asunto, cuerpo, modelo, guardar=True, origen="experimento")
        lm = r["llm"]
        filas.append({
            "asunto": asunto, "informal": informal, "real_cat": cat, "real_pri": pri,
            "reglas_cat": reg.categoria, "reglas_pri": reg.prioridad,
            "llm_cat": lm["categoria"] if lm else "invalido", "llm_pri": lm["prioridad"] if lm else "invalido",
            "hib_cat": r["categoria"], "hib_pri": r["prioridad"], "revision_humana": r["requiere_revision_humana"],
            "lat_reglas_s": lat_reg, "lat_llm_s": r["latencia_llm_s"], "intentos": r["intentos_llm"],
            "json_valido": lm is not None})
        f = filas[-1]
        if avance:
            avance(i, len(DATASET))
        progreso(f"[{i:02}/{len(DATASET)}] real={cat:22} reglas={f['reglas_cat']:22} "
                 f"llm={f['llm_cat']:22} híbrido={f['hib_cat']}")

    df = pd.DataFrame(filas)
    metodos = {}
    pref = {"reglas": "reglas", "llm": "llm", "hibrido": "hib"}
    for m, p in pref.items():
        lat = df.lat_reglas_s if m == "reglas" else df.lat_llm_s if m == "llm" else df.lat_reglas_s + df.lat_llm_s
        formales, informales = df[~df.informal], df[df.informal]
        metodos[m] = {
            "exactitud_categoria": _exactitud(df.real_cat, df[f"{p}_cat"]),
            "exactitud_prioridad": _exactitud(df.real_pri, df[f"{p}_pri"]),
            "exactitud_cat_formales": _exactitud(formales.real_cat, formales[f"{p}_cat"]),
            "exactitud_cat_informales": _exactitud(informales.real_cat, informales[f"{p}_cat"]),
            "latencia_media_s": round(float(lat.mean()), 3),
            "latencia_p95_s": round(float(lat.quantile(0.95)), 3),
            "matriz_confusion": _matriz(df.real_cat, df[f"{p}_cat"]),
        }
    res = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": modelo or configuracion.cargar_ajustes()["modelo"],
        "n_correos": len(df), "n_informales": int(df.informal.sum()),
        "json_valido_pct": round(100 * df.json_valido.mean(), 1),
        "revision_humana_pct": round(100 * df.revision_humana.mean(), 1),
        "metodos": metodos,
        "filas": df.round(3).to_dict(orient="records"),
    }
    with open("resultados_experimento.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return res


if __name__ == "__main__":
    modelo = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        r = correr(modelo)
    except llm.ErrorLLM as e:
        raise SystemExit(str(e))
    print(f"\nModelo: {r['modelo']} | JSON válido: {r['json_valido_pct']}% | revisión humana: {r['revision_humana_pct']}%")
    print(f"{'método':10}{'cat':>8}{'prio':>8}{'formal':>9}{'informal':>10}{'lat (s)':>10}")
    for k, v in r["metodos"].items():
        print(f"{k:10}{v['exactitud_categoria']:>8.0%}{v['exactitud_prioridad']:>8.0%}"
              f"{v['exactitud_cat_formales']:>9.0%}{v['exactitud_cat_informales']:>10.0%}{v['latencia_media_s']:>10.2f}")
    print("Resultados guardados en resultados_experimento.json")
