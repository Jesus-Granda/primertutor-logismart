"""Carga datos de demostración en MongoDB.

Uso:  python datos_demo.py           (solo llena las colecciones vacías)
      python datos_demo.py --reset   (BORRA las 5 colecciones y las vuelve a llenar)
"""
import random
import sys
from datetime import datetime, timedelta

import configuracion
from capa_datos import basedatos as bd
from capa_logica import clasificador as clf
from capa_logica import reglas, riesgos
from experimento import DATASET

# camion_id, placa, empresa, autorizado, días para que venza la certificación, tipo de carga
CAMIONES = [
    ("CAM-101", "ABC-101-A", "Transportes del Valle", True, 240, "general"),
    ("CAM-102", "ABC-123-D", "QuimiLog", True, 180, "peligrosa"),
    ("CAM-103", "DEF-789-A", "Fletes Toluca", True, 90, "general"),
    ("CAM-104", "JKL-321-C", "Carga Pesada MX", True, 300, "general"),
    ("CAM-105", "XYZ-456-B", "Transportes Rápidos", False, 120, "general"),
    ("CAM-106", "MNO-654-E", "LogiNorte", True, -15, "general"),
    ("CAM-108", "PQR-208-F", "GasExpress", True, 60, "peligrosa"),
    ("CAM-110", "STU-310-G", "QuimiLog", True, 200, "peligrosa"),
    ("CAM-115", "VWX-515-H", "Desconocida", False, 30, "general"),
]
OPERADORES = ["operador.norte", "operador.sur", "supervisor.turno2"]


def documento_acceso(camion, peso, R, H, F, operador, marca_tiempo, limite):
    """Evalúa las reglas para un camión y arma el documento de la bitácora de accesos."""
    P = bool(camion["autorizacion"]["autorizado"])
    S = camion["certificacion_conductor"]["vigente_hasta"] >= marca_tiempo
    Q = peso > limite
    r = reglas.evaluar(P, Q, R, S, H, F)
    return reglas.documento_bitacora(r, camion["camion_id"], camion["placa"], operador, peso, limite, marca_tiempo)


def cargar(reset=False, semilla=7):
    random.seed(semilla)
    if reset:
        for c in bd.COLECCIONES:
            bd.vaciar(c)
    ahora = datetime.now()
    limite = configuracion.cargar_ajustes()["peso_max_kg"]

    if bd.contar("camiones") == 0:
        bd.insertar_varios("camiones", [{
            "camion_id": cid, "placa": placa, "empresa": empresa, "tipo_carga": carga,
            "autorizacion": {"autorizado": aut, "folio": f"AUT-{cid[-3:]}" if aut else None},
            "certificacion_conductor": {"folio": f"CERT-{cid[-3:]}", "vigente_hasta": ahora + timedelta(days=dias)},
        } for cid, placa, empresa, aut, dias, carga in CAMIONES])

    if bd.contar("accesos") == 0:
        camiones = {c["camion_id"]: c for c in bd.listar("camiones")}
        docs = []
        for _ in range(42):
            cam = random.choice(list(camiones.values()))
            cuando = ahora - timedelta(days=random.randint(1, 34), hours=random.randint(0, 12))
            peso = random.choice([28000, 33000, 38000, 41000, 44000, 46500, 51000])
            docs.append(documento_acceso(cam, peso, cam["tipo_carga"] == "peligrosa", 6 <= cuando.hour < 18,
                                         random.random() < 0.08, random.choice(OPERADORES), cuando, limite))
        # casos fijos para demostrar el asistente («¿por qué CAM-102 fue enviado a inspección?»)
        docs.append(documento_acceso(camiones["CAM-102"], 48500, True, True, False, "operador.norte",
                                     ahora - timedelta(hours=3), limite))
        docs.append(documento_acceso(camiones["CAM-101"], 31000, False, True, False, "operador.sur",
                                     ahora - timedelta(hours=2), limite))
        docs.append(documento_acceso(camiones["CAM-106"], 30000, False, True, False, "operador.sur",
                                     ahora - timedelta(hours=1), limite))
        bd.insertar_varios("accesos", docs)

    if bd.contar("incidentes") == 0:
        docs = []
        for asunto, cuerpo, *_ in random.sample(DATASET, 15):
            c, palabras = clf.clasificar_reglas(asunto, cuerpo)
            estado = random.choice(["nuevo", "en_atencion", "cerrado"])
            cuando = ahora - timedelta(days=random.randint(0, 34), hours=random.randint(0, 20))
            historial = [{"fecha": cuando, "usuario": "datos_demo",
                          "evento": "alta desde la bandeja (clasificación por reglas)"}]
            if estado != "nuevo":
                historial.append({"fecha": cuando + timedelta(hours=2), "usuario": random.choice(OPERADORES),
                                  "evento": f"estado: nuevo → {estado}"})
            docs.append(clf.documento_incidente(asunto, cuerpo, c, "reglas", False, palabras, estado,
                                                historial, cuando))
        bd.insertar_varios("incidentes", docs)

    if bd.contar("riesgos_eticos") == 0:
        bd.insertar_varios("riesgos_eticos", [riesgos.documento(*r) for r in riesgos.RIESGOS_DEMO])


if __name__ == "__main__":
    cargar("--reset" in sys.argv)
    print(f"Datos de demostración cargados en '{configuracion.MONGO_DB}' ({bd.modo()}):")
    for c in bd.COLECCIONES:
        print(f"  {c:18} {bd.contar(c)} documentos")
