"""MOTOR DE REGLAS (lógica proposicional) con explicación paso a paso.

Premisas originales (script LogiSmart):
  P: Vehículo con autorización previa
  Q: El peso excede el límite
  R: Carga con materiales peligrosos
  S: Conductor con certificación vigente

Reglas originales (se conservan sin cambios):
  R1  A (acceso estándar)      = P ∧ S ∧ ¬Q
  R2  E (inspección especial)  = P ∧ (R ∨ Q)

Premisas nuevas:
  H: Llega dentro del horario permitido para materiales peligrosos
  F: La cámara detecta fatiga / somnolencia del conductor

Reglas nuevas:
  R3  Horario restringido para materiales peligrosos
        B = R ∧ ¬H            (carga peligrosa fuera de horario)
        A ← A ∧ ¬B
      Justificación: el manejo de materiales peligrosos requiere personal y brigada de
      emergencia disponibles; fuera de horario el camión no entra al flujo estándar y
      queda en inspección especial (E ya es verdadera por R2 cuando P ∧ R) para reprogramarse.

  R4  Conductor con signos de fatiga
        A ← A ∧ ¬F
        E ← E ∨ (P ∧ F)
      Justificación: el PEAS original incluye la cámara de somnolencia; un conductor con
      fatiga no debe maniobrar en patio. Si el camión es autorizado se envía a inspección
      especial (revisión del conductor / relevo) en lugar de rechazarlo sin más.
"""
from itertools import product

VARIABLES = {
    "P": "Vehículo con autorización previa",
    "Q": "El peso excede el límite",
    "R": "Carga con materiales peligrosos",
    "S": "Conductor con certificación vigente",
    "H": "Dentro del horario para materiales peligrosos",
    "F": "Fatiga o somnolencia detectada en el conductor",
}
ORDEN = "PQRSHF"
REGLAS = ("R1", "R2", "R3", "R4")


def _v(b):
    return "V" if b else "F"


def calcular(P, Q, R, S, H=True, F=False, activas=REGLAS):
    """Cálculo puro (sin explicación). Devuelve (A, E)."""
    A = P and S and not Q if "R1" in activas else False
    E = P and (R or Q) if "R2" in activas else False
    if "R3" in activas:
        A = A and not (R and not H)
    if "R4" in activas:
        A = A and not F
        E = E or (P and F)
    return bool(A), bool(E)


def evaluar(P, Q, R, S, H=True, F=False):
    """Evalúa un camión y explica qué premisas causaron la decisión."""
    valores = dict(zip(ORDEN, (P, Q, R, S, H, F)))
    for k, v in valores.items():
        if not isinstance(v, bool):
            raise TypeError(f"La premisa {k} debe ser bool, se recibió {type(v).__name__}")

    pasos = []
    A1 = P and S and not Q
    pasos.append(f"R1: A = P ∧ S ∧ ¬Q = {_v(P)} ∧ {_v(S)} ∧ {_v(not Q)} = {_v(A1)}")
    E2 = P and (R or Q)
    pasos.append(f"R2: E = P ∧ (R ∨ Q) = {_v(P)} ∧ ({_v(R)} ∨ {_v(Q)}) = {_v(E2)}")
    B = R and not H
    A3 = A1 and not B
    pasos.append(f"R3: B = R ∧ ¬H = {_v(R)} ∧ {_v(not H)} = {_v(B)}  →  A = A ∧ ¬B = {_v(A3)}")
    A4 = A3 and not F
    E4 = E2 or (P and F)
    pasos.append(f"R4: A = A ∧ ¬F = {_v(A4)} ;  E = E ∨ (P ∧ F) = {_v(E2)} ∨ {_v(P and F)} = {_v(E4)}")

    causas = []
    if not P:
        causas.append("P = F: el vehículo no tiene autorización previa (bloquea A y E).")
    if P and not S:
        causas.append("S = F: la certificación del conductor no está vigente (bloquea el acceso estándar).")
    if Q:
        causas.append("Q = V: el peso excede el límite (bloquea A" + (" y activa inspección especial)." if P else ")."))
    if R and P:
        causas.append("R = V: lleva materiales peligrosos (activa inspección especial).")
    if B:
        causas.append("R3: materiales peligrosos fuera del horario permitido (no hay acceso estándar; reprogramar).")
    if F:
        causas.append("R4: se detectó fatiga en el conductor (sin acceso estándar"
                      + ("; pasa a revisión del conductor)." if P else ")."))

    if A4 and not E4:
        decision, semaforo = "ACCESO ESTÁNDAR", "verde"
    elif A4 and E4:
        decision, semaforo = "ACCESO CON INSPECCIÓN ESPECIAL", "amarillo"
    elif E4:
        decision, semaforo = "ENVIAR A INSPECCIÓN ESPECIAL", "amarillo"
    else:
        decision, semaforo = "ACCESO DENEGADO", "rojo"
    if not causas:
        causas.append("Todas las premisas favorables: autorizado, certificado, peso correcto, sin carga peligrosa.")
    return {"A": bool(A4), "E": bool(E4), "decision": decision, "semaforo": semaforo,
            "premisas": valores, "pasos": pasos, "causas": causas}


# ----------------------------------------------------------------- tablas
def _tabla(nombres, fn, salida, intermedias=()):
    filas = []
    for vals in product([True, False], repeat=len(nombres)):
        d = dict(zip(nombres, vals))
        for etiqueta, f in intermedias:
            d[etiqueta] = f(**d)
        d[salida] = fn(**d)
        filas.append({k: _v(v) for k, v in d.items()})
    return filas


def tablas_verdad():
    """Tabla de verdad de cada regla (con columnas intermedias)."""
    return {
        "R1: A = P ∧ S ∧ ¬Q": _tabla("PQS", lambda P, Q, S, **_: P and S and not Q, "A",
                                    (("¬Q", lambda Q, **_: not Q), ("P∧S", lambda P, S, **_: P and S))),
        "R2: E = P ∧ (R ∨ Q)": _tabla("PQR", lambda P, Q, R, **_: P and (R or Q), "E",
                                     (("R∨Q", lambda Q, R, **_: R or Q),)),
        "R3: B = R ∧ ¬H ;  A' = A ∧ ¬B": _tabla(("A", "R", "H"), lambda A, R, H, **_: A and not (R and not H), "A'",
                                               (("B", lambda R, H, **_: R and not H),)),
        "R4: A' = A ∧ ¬F ;  E' = E ∨ (P ∧ F)": _tabla(("A", "E", "P", "F"),
                                                     lambda A, F, **_: A and not F, "A'",
                                                     (("E'", lambda E, P, F, **_: E or (P and F)),)),
    }


def tabla_completa():
    """Las 64 combinaciones de P, Q, R, S, H, F con A y E finales."""
    filas = []
    for vals in product([True, False], repeat=6):
        A, E = calcular(*vals)
        filas.append({**{k: _v(v) for k, v in zip(ORDEN, vals)}, "A": _v(A), "E": _v(E)})
    return filas


def analizar():
    """Reto opcional: detecta contradicciones y reglas redundantes.

    Contradicción: A verdadera cuando alguna premisa debería impedirla (¬P, Q, ¬S, R∧¬H o F).
    Redundancia: una regla que, al quitarla, no cambia ningún resultado en las 64 combinaciones.
    """
    contradicciones, efecto = [], {r: {"A": 0, "E": 0} for r in REGLAS}
    ambos = 0
    for vals in product([True, False], repeat=6):
        P, Q, R, S, H, F = vals
        A, E = calcular(*vals)
        ambos += A and E
        if A and (not P or Q or not S or (R and not H) or F):
            contradicciones.append(dict(zip(ORDEN, vals)))
        for r in REGLAS:
            sin = tuple(x for x in REGLAS if x != r)
            A2, E2 = calcular(*vals, activas=sin)
            efecto[r]["A"] += A2 != A
            efecto[r]["E"] += E2 != E
    redundantes = [r for r, e in efecto.items() if e["A"] == 0 and e["E"] == 0]
    observaciones = [
        f"A y E son verdaderas a la vez en {ambos} de 64 combinaciones (P∧S∧¬Q∧R con horario y sin fatiga): "
        "no es contradicción, significa 'entra pero pasa por inspección especial'.",
        "R3 solo modifica A: la parte de inspección ya la cubre R2 (P ∧ R ⇒ E), por eso R3 no agrega nada a E. "
        "Es una redundancia parcial que se evitó a propósito al no repetir E en R3.",
        "Sin P (autorización previa) A y E siempre son F: el camión se rechaza en caseta.",
    ]
    return {"combinaciones": 64, "contradicciones": contradicciones, "efecto_por_regla": efecto,
            "redundantes": redundantes, "observaciones": observaciones}


def documento_bitacora(resultado, camion_id, placa, operador, peso_kg=None, limite_kg=None, marca_tiempo=None):
    """Arma el documento que se guarda en la colección 'accesos' (bitácora).

    Incluye P, Q, R, S (y H, F), los resultados A y E, la marca de tiempo, el operador y la
    explicación paso a paso con las premisas que causaron la decisión.
    """
    from datetime import datetime
    doc = {"camion_id": camion_id, "placa": placa, "peso_kg": peso_kg, "limite_kg": limite_kg,
           **resultado["premisas"], "A": resultado["A"], "E": resultado["E"],
           "decision": resultado["decision"], "semaforo": resultado["semaforo"],
           "explicacion": {"causas": resultado["causas"], "pasos": resultado["pasos"]},
           "operador": operador, "marca_tiempo": marca_tiempo or datetime.now()}
    return doc
