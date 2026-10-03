"""CAPA DE DATOS: conexión a MongoDB, CRUD genérico y agregaciones.

Colecciones: camiones, accesos, incidentes, riesgos_eticos, evaluaciones_llm.
Todos los errores de PyMongo se convierten en ErrorBD con un mensaje entendible.
"""
import functools
import re
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

import configuracion

COLECCIONES = ["camiones", "accesos", "incidentes", "riesgos_eticos", "evaluaciones_llm"]
_client = None
_db_prueba = None  # las pruebas pueden inyectar una BD falsa (mongomock)


class ErrorBD(Exception):
    """Error amigable de base de datos (conexión, permisos, duplicados...).

    El mensaje es para el usuario; `detalle` guarda el error técnico original."""

    def __init__(self, mensaje, detalle=""):
        super().__init__(mensaje)
        self.detalle = detalle


def usar_bd(db):
    """Inyecta una base de datos (para pruebas)."""
    global _db_prueba
    _db_prueba = db


def _bd_en_memoria():
    """MONGO_URI=memoria: base de datos simulada en RAM (mongomock) con datos de demostración.
    No se conecta a ningún servidor; los datos se pierden al cerrar la aplicación."""
    global _db_prueba
    import mongomock
    _db_prueba = mongomock.MongoClient()[configuracion.MONGO_DB]
    _indices(_db_prueba)
    import datos_demo  # import tardío para evitar import circular
    datos_demo.cargar()
    return _db_prueba


def modo():
    uri = (configuracion.mongo_uri() or "").strip()
    if uri.lower() == "memoria":
        return "memoria (sin servidor)"
    if "localhost" in uri or "127.0.0.1" in uri:
        return "MongoDB local"
    return "MongoDB Atlas" if uri else "sin configurar"


def get_db():
    global _client
    if _db_prueba is not None:
        return _db_prueba
    uri = configuracion.mongo_uri()
    if uri and uri.strip().lower() == "memoria":
        return _bd_en_memoria()
    if not uri:
        raise ErrorBD("Faltan las credenciales de MongoDB. Crea el archivo .env a partir de .env.example.")
    try:
        if _client is None:
            _client = MongoClient(uri, serverSelectionTimeoutMS=6000)
            _client.admin.command("ping")
            _indices(_client[configuracion.MONGO_DB])
        return _client[configuracion.MONGO_DB]
    except PyMongoError as e:
        _client = None
        texto = str(e)
        if "auth" in texto.lower():
            raise ErrorBD("MongoDB rechazó el usuario o la contraseña. Revisa tu archivo .env.", texto)
        raise ErrorBD("No se pudo conectar a MongoDB. Revisa tu conexión a internet y que tu IP esté "
                      "permitida en Atlas (Network Access).", texto)


def _indices(db):
    db.camiones.create_index([("placa", ASCENDING)], unique=True)
    db.camiones.create_index([("camion_id", ASCENDING)], unique=True)
    db.accesos.create_index([("marca_tiempo", ASCENDING)])
    db.incidentes.create_index([("marca_tiempo", ASCENDING)])


def seguro(fn):
    @functools.wraps(fn)
    def envoltura(*a, **k):
        try:
            return fn(*a, **k)
        except DuplicateKeyError as e:
            raise ErrorBD("Ya existe un registro con ese valor (la placa y el ID del camión no se pueden repetir).",
                          str(e))
        except InvalidId:
            raise ErrorBD("Identificador de documento inválido.")
        except PyMongoError as e:
            raise ErrorBD("La base de datos no respondió como se esperaba. Intenta de nuevo en unos segundos.", str(e))
    return envoltura


_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def reparar_fechas(o):
    """Convierte cadenas ISO a datetime (útil al editar JSON desde la GUI)."""
    if isinstance(o, dict):
        return {k: reparar_fechas(v) for k, v in o.items()}
    if isinstance(o, list):
        return [reparar_fechas(v) for v in o]
    if isinstance(o, str) and _FECHA.match(o):
        try:
            return datetime.fromisoformat(o)
        except ValueError:
            return o
    return o


def limpiar(o):
    """Hace un documento serializable (ObjectId -> str, datetime -> ISO)."""
    if isinstance(o, ObjectId):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat(timespec="seconds")
    if isinstance(o, dict):
        return {k: limpiar(v) for k, v in o.items()}
    if isinstance(o, list):
        return [limpiar(v) for v in o]
    return o


@seguro
def insertar(col, doc):
    doc = reparar_fechas(dict(doc))
    doc.pop("_id", None)
    doc.setdefault("marca_tiempo", datetime.now())
    return str(get_db()[col].insert_one(doc).inserted_id)


@seguro
def insertar_varios(col, docs):
    ahora = datetime.now()
    docs = [{**reparar_fechas(d), "marca_tiempo": d.get("marca_tiempo", ahora)} for d in docs]
    if docs:
        get_db()[col].insert_many(docs)


@seguro
def listar(col, filtro=None, limite=500, orden=("marca_tiempo", -1)):
    return list(get_db()[col].find(filtro or {}).sort(*orden).limit(limite))


@seguro
def obtener(col, _id):
    return get_db()[col].find_one({"_id": ObjectId(str(_id))})


@seguro
def buscar_uno(col, filtro):
    return get_db()[col].find_one(filtro)


@seguro
def actualizar(col, _id, cambios):
    cambios = reparar_fechas(dict(cambios))
    cambios.pop("_id", None)
    get_db()[col].update_one({"_id": ObjectId(str(_id))}, {"$set": cambios})


@seguro
def reemplazar(col, _id, doc):
    doc = reparar_fechas(dict(doc))
    doc.pop("_id", None)
    get_db()[col].replace_one({"_id": ObjectId(str(_id))}, doc)


@seguro
def agregar_historial(col, _id, evento, usuario="operador"):
    get_db()[col].update_one({"_id": ObjectId(str(_id))},
                             {"$push": {"historial": {"fecha": datetime.now(), "evento": evento, "usuario": usuario}}})


@seguro
def eliminar(col, _id):
    get_db()[col].delete_one({"_id": ObjectId(str(_id))})


@seguro
def contar(col, filtro=None):
    return get_db()[col].count_documents(filtro or {})


@seguro
def vaciar(col):
    get_db()[col].delete_many({})


@seguro
def incidentes_por_categoria_semana(desde=None, hasta=None):
    """AGREGACIÓN: número de incidentes por categoría y semana ISO."""
    match = {}
    if desde or hasta:
        match["marca_tiempo"] = {k: v for k, v in (("$gte", desde), ("$lte", hasta)) if v}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"anio": {"$isoWeekYear": "$marca_tiempo"}, "semana": {"$isoWeek": "$marca_tiempo"},
                            "categoria": "$clasificacion.categoria"},
                    "total": {"$sum": 1}}},
        {"$sort": {"_id.anio": 1, "_id.semana": 1, "_id.categoria": 1}},
    ]
    try:
        return list(get_db()["incidentes"].aggregate(pipeline))
    except NotImplementedError:
        # Solo ocurre con la BD simulada de las pruebas (mongomock no implementa $isoWeek)
        conteo = {}
        for d in get_db()["incidentes"].find(match):
            anio, semana, _ = d["marca_tiempo"].isocalendar()
            clave = (anio, semana, d.get("clasificacion", {}).get("categoria"))
            conteo[clave] = conteo.get(clave, 0) + 1
        return [{"_id": {"anio": a, "semana": s, "categoria": c}, "total": n}
                for (a, s, c), n in sorted(conteo.items(), key=lambda x: (x[0][0], x[0][1], str(x[0][2])))]


@seguro
def accesos_por_decision(desde=None, hasta=None):
    """AGREGACIÓN: accesos por decisión (semáforo)."""
    match = {}
    if desde or hasta:
        match["marca_tiempo"] = {k: v for k, v in (("$gte", desde), ("$lte", hasta)) if v}
    return list(get_db()["accesos"].aggregate([
        {"$match": match}, {"$group": {"_id": "$decision", "total": {"$sum": 1}}}, {"$sort": {"total": -1}}]))
