"""Armador rápido de PCs: catálogo de componentes + optimizador de builds (sin LLM, instantáneo).

Los precios son REFERENCIAS APROXIMADAS en USD (calle, EE. UU., octubre 2026) y cambian
mucho: la escasez de memoria de 2026 encareció bastante la RAM DDR5 y los SSD.
Actualiza el catálogo cuando quieras; el resto del programa se ajusta solo.
"""
import itertools
import math
import re
import unicodedata

ACTUALIZADO = "octubre 2026"

# ----------------------------------------------------------------------------- CPUs
# juego / multi: puntajes relativos (100 = referencia alta). pico: consumo máximo aprox (W).
CPUS = [
    dict(nombre="AMD Ryzen 5 5600", marca="AMD", socket="AM4", mem="DDR4", nucleos="6C/12H",
         precio=110, pico=88, juego=55, multi=40, cooler_incluido=True, igpu=False),
    dict(nombre="Intel Core i5-14400F", marca="Intel", socket="LGA1700", mem="DDR4", nucleos="10C/16H",
         precio=140, pico=148, juego=62, multi=58, cooler_incluido=True, igpu=False),
    dict(nombre="AMD Ryzen 5 8600G", marca="AMD", socket="AM5", mem="DDR5", nucleos="6C/12H",
         precio=170, pico=88, juego=58, multi=46, cooler_incluido=True, igpu=True),
    dict(nombre="AMD Ryzen 5 7600", marca="AMD", socket="AM5", mem="DDR5", nucleos="6C/12H",
         precio=180, pico=88, juego=70, multi=47, cooler_incluido=True, igpu=True),
    dict(nombre="AMD Ryzen 5 9600X", marca="AMD", socket="AM5", mem="DDR5", nucleos="6C/12H",
         precio=190, pico=88, juego=74, multi=52, cooler_incluido=False, igpu=True),
    dict(nombre="Intel Core Ultra 5 250K Plus", marca="Intel", socket="LGA1851", mem="DDR5", nucleos="18C (6P+12E)",
         precio=199, pico=159, juego=73, multi=72, cooler_incluido=False, igpu=True),
    dict(nombre="AMD Ryzen 7 9700X", marca="AMD", socket="AM5", mem="DDR5", nucleos="8C/16H",
         precio=300, pico=88, juego=78, multi=62, cooler_incluido=False, igpu=True),
    dict(nombre="Intel Core Ultra 7 270K Plus", marca="Intel", socket="LGA1851", mem="DDR5", nucleos="24C (8P+16E)",
         precio=299, pico=250, juego=80, multi=95, cooler_incluido=False, igpu=True),
    dict(nombre="AMD Ryzen 7 9800X3D", marca="AMD", socket="AM5", mem="DDR5", nucleos="8C/16H + 3D V-Cache",
         precio=450, pico=162, juego=95, multi=62, cooler_incluido=False, igpu=True),
    dict(nombre="AMD Ryzen 7 9850X3D", marca="AMD", socket="AM5", mem="DDR5", nucleos="8C/16H + 3D V-Cache",
         precio=499, pico=162, juego=98, multi=64, cooler_incluido=False, igpu=True),
    dict(nombre="AMD Ryzen 9 9950X", marca="AMD", socket="AM5", mem="DDR5", nucleos="16C/32H",
         precio=520, pico=230, juego=83, multi=100, cooler_incluido=False, igpu=True),
    dict(nombre="AMD Ryzen 9 9950X3D", marca="AMD", socket="AM5", mem="DDR5", nucleos="16C/32H + 3D V-Cache",
         precio=650, pico=230, juego=97, multi=103, cooler_incluido=False, igpu=True),
]

# ----------------------------------------------------------------------------- GPUs
# rend: rendimiento relativo (RTX 5080 = 100). largo: True si suele medir más de 320 mm.
GPUS = [
    dict(nombre="Gráficos integrados del CPU", marca="Integrada", vram=0, precio=0, tgp=0, rend=8,
         largo=False, conector="-"),
    dict(nombre="Intel Arc B580 12 GB", marca="Intel", vram=12, precio=270, tgp=190, rend=40,
         largo=False, conector="8 pines"),
    dict(nombre="NVIDIA GeForce RTX 5060 8 GB", marca="NVIDIA", vram=8, precio=310, tgp=145, rend=42,
         largo=False, conector="8 pines"),
    dict(nombre="AMD Radeon RX 9060 XT 16 GB", marca="AMD", vram=16, precio=380, tgp=160, rend=50,
         largo=False, conector="8 pines"),
    dict(nombre="NVIDIA GeForce RTX 5060 Ti 16 GB", marca="NVIDIA", vram=16, precio=460, tgp=180, rend=55,
         largo=False, conector="8 pines"),
    dict(nombre="NVIDIA GeForce RTX 5070 12 GB", marca="NVIDIA", vram=12, precio=600, tgp=250, rend=70,
         largo=False, conector="12V-2x6 u 8 pines (según modelo)"),
    dict(nombre="AMD Radeon RX 9070 16 GB", marca="AMD", vram=16, precio=600, tgp=220, rend=72,
         largo=False, conector="2x 8 pines"),
    dict(nombre="AMD Radeon RX 9070 XT 16 GB", marca="AMD", vram=16, precio=700, tgp=304, rend=82,
         largo=True, conector="2-3x 8 pines"),
    dict(nombre="NVIDIA GeForce RTX 5070 Ti 16 GB", marca="NVIDIA", vram=16, precio=850, tgp=300, rend=85,
         largo=True, conector="12V-2x6"),
    dict(nombre="NVIDIA GeForce RTX 5080 16 GB", marca="NVIDIA", vram=16, precio=1200, tgp=360, rend=100,
         largo=True, conector="12V-2x6"),
    dict(nombre="NVIDIA GeForce RTX 5090 32 GB", marca="NVIDIA", vram=32, precio=2800, tgp=575, rend=140,
         largo=True, conector="12V-2x6"),
]

RAM = {  # (GB, tipo): (descripción, precio)
    (16, "DDR4"): ("16 GB (2x8) DDR4-3200", 89),
    (32, "DDR4"): ("32 GB (2x16) DDR4-3200", 198),
    (16, "DDR5"): ("16 GB (2x8) DDR5-6000", 215),
    (32, "DDR5"): ("32 GB (2x16) DDR5-6000", 405),
    (64, "DDR5"): ("64 GB (2x32) DDR5-6000", 790),
}

PLACAS = {  # socket: [(nivel, nombre, precio)]  nivel 0 = básica, 1 = media, 2 = alta
    "AM4": [(0, "B550 (DDR4)", 100), (1, "B550 (DDR4)", 100), (2, "B550 (DDR4) gama alta", 140)],
    "LGA1700": [(0, "B760 DDR4", 110), (1, "B760 DDR4", 110), (2, "B760 DDR4", 110)],
    "AM5": [(0, "A620", 100), (1, "B650", 150), (2, "B850", 190)],
    "LGA1851": [(0, "B860", 150), (1, "B860", 150), (2, "Z890", 240)],
}

ALMACENAMIENTO = [(1, "SSD NVMe 1 TB PCIe 4.0", 110), (2, "SSD NVMe 2 TB PCIe 4.0", 190), (4, "SSD NVMe 4 TB PCIe 4.0", 380)]

FUENTES = [
    (550, "550 W 80 Plus Bronze", 60),
    (650, "650 W 80 Plus Gold", 85),
    (750, "750 W 80 Plus Gold ATX 3.1", 105),
    (850, "850 W 80 Plus Gold ATX 3.1", 130),
    (1000, "1000 W 80 Plus Gold ATX 3.1", 180),
    (1200, "1200 W 80 Plus Platinum ATX 3.1", 280),
]

GABINETES = [("compacto", "Gabinete ATX con buen flujo de aire", 70),
             ("medio", "Gabinete mid-tower airflow (GPU de hasta ~400 mm)", 100),
             ("grande", "Gabinete full-tower airflow", 150)]

USOS = {
    "gaming_1080": "Gaming 1080p",
    "gaming_1440": "Gaming 1440p",
    "gaming_4k": "Gaming 4K",
    "streaming": "Gaming + streaming",
    "edicion": "Edición y diseño",
    "ia": "IA local",
    "oficina": "Oficina / escuela",
}


# ----------------------------------------------------------------------- reglas
def _cooler(cpu):
    if cpu["cooler_incluido"] and cpu["pico"] <= 150:
        return "Disipador incluido con el procesador", 0
    if cpu["pico"] <= 120:
        return "Disipador de torre sencillo (120 mm)", 30
    if cpu["pico"] <= 170:
        return "Disipador de torre de buena calidad", 45
    return "Enfriamiento líquido AIO 360 mm o torre doble", 100


def _placa(cpu, nivel):
    nivel = max(0, min(2, nivel))
    if cpu["juego"] >= 90 or cpu["multi"] >= 95:
        nivel = max(nivel, 1 if cpu["socket"] == "LGA1851" else 2)
    _, nombre, precio = PLACAS[cpu["socket"]][nivel]
    return f"Tarjeta madre {nombre} ({cpu['socket']})", precio


def consumo(cpu, gpu):
    return cpu["pico"] + gpu["tgp"] + 75  # +75 W para placa, RAM, SSD y ventiladores


def fuente(watts_estimados):
    necesarios = watts_estimados * 1.3  # margen del 30%
    for w, nombre, precio in FUENTES:
        if w >= necesarios:
            return w, nombre, precio
    return FUENTES[-1]


def _gabinete(gpu):
    if gpu["tgp"] >= 500:
        return GABINETES[2]
    return GABINETES[1] if gpu["largo"] else GABINETES[0]


def _efectivo(rend, tope):
    return min(rend, tope) + 0.25 * max(0, rend - tope)


def _puntaje(uso, cpu, gpu, ram_gb):
    g, cj, cm = gpu["rend"], cpu["juego"], cpu["multi"]
    if uso == "gaming_1080":
        s = 1.0 * _efectivo(g, 75) + 0.55 * cj - 0.6 * max(0, g - cj * 1.1)
    elif uso == "gaming_1440":
        s = 1.0 * _efectivo(g, 100) + 0.4 * cj - 0.5 * max(0, g - cj * 1.3)
    elif uso == "gaming_4k":
        s = 1.0 * g + 0.25 * cj + (6 if gpu["vram"] >= 16 else 0)
    elif uso == "streaming":
        s = 0.85 * _efectivo(g, 90) + 0.3 * cj + 0.45 * cm - 0.5 * max(0, g - cj * 1.3)
    elif uso == "edicion":
        s = 0.6 * cm + 0.35 * g + 0.15 * cj
    elif uso == "ia":
        s = 4.0 * gpu["vram"] + 0.5 * g + 0.1 * cm
    else:
        s = 0.5 * cm + 0.5 * cj
    if uso.startswith("gaming") or uso == "streaming":
        s += {16: 0, 32: 7, 64: 7}[ram_gb]
        if gpu["vram"] < 12 and uso != "gaming_1080":
            s -= 8
    else:
        s += {16: 0, 32: 6, 64: 12}[ram_gb]
    return s


def _opciones_ram(uso, mem):
    if uso == "oficina":
        return [16]
    if uso in ("edicion", "ia"):
        return [32, 64] if mem == "DDR5" else [32]
    return [16, 32]


def armar(presupuesto_usd, uso="gaming_1080", plataforma="cualquiera", marca_gpu="cualquiera"):
    """Busca la combinación con mejor puntaje que quepa en el presupuesto (en USD)."""
    if uso not in USOS:
        raise ValueError(f"Uso no válido: {uso}")
    cpus = [c for c in CPUS if plataforma == "cualquiera" or c["marca"].lower() == plataforma]
    gpus = [g for g in GPUS if marca_gpu == "cualquiera" or g["marca"].lower() == marca_gpu or g["vram"] == 0]
    if uso == "oficina":
        gpus = [g for g in GPUS if g["vram"] == 0]
    elif uso == "ia":
        gpus = [g for g in gpus if g["vram"] >= 12]
    else:
        gpus = [g for g in gpus if g["vram"] > 0]
    if not gpus:  # p. ej. IA local con filtro de marca sin opciones
        gpus = [g for g in GPUS if g["vram"] >= 12]

    candidatos = []
    for cpu, gpu in itertools.product(cpus, gpus):
        if gpu["vram"] == 0 and not cpu["igpu"]:
            continue
        for ram_gb in _opciones_ram(uso, cpu["mem"]):
            if (ram_gb, cpu["mem"]) not in RAM:
                continue
            ssd = ALMACENAMIENTO[1] if uso in ("edicion", "ia") else ALMACENAMIENTO[0]
            nivel_placa = 0 if uso == "oficina" else 1
            b = _componer(cpu, gpu, ram_gb, ssd, nivel_placa)
            candidatos.append((b, _puntaje(uso, cpu, gpu, ram_gb)))
    if not candidatos:
        raise ValueError("No hay combinaciones con esos filtros.")

    dentro = [c for c in candidatos if c[0]["total"] <= presupuesto_usd]
    if not dentro:
        b = min(candidatos, key=lambda c: c[0]["total"])[0]
        b["advertencia"] = (f"Tu presupuesto no alcanza para este uso con esos filtros. "
                            f"Lo mínimo razonable ronda {b['total']:,.0f} USD.")
    elif uso == "oficina":
        b = min(dentro, key=lambda c: c[0]["total"])[0]
    else:
        b = max(dentro, key=lambda c: (round(c[1], 1), -c[0]["total"]))[0]

    # mejoras con lo que sobra
    sobra = presupuesto_usd - b["total"]
    if dentro and uso != "oficina":
        if b["ssd_tb"] == 1 and sobra >= ALMACENAMIENTO[1][2] - ALMACENAMIENTO[0][2] + 40:
            b = _componer(b["_cpu"], b["_gpu"], b["ram_gb"], ALMACENAMIENTO[1], b["_nivel"])
    b["presupuesto"] = presupuesto_usd
    b["uso"] = uso
    b["sobra"] = presupuesto_usd - b["total"]
    b["notas"] = _notas(b)
    return b


def _ssd(tb):
    return next(s for s in ALMACENAMIENTO if s[0] == tb)


def _componer(cpu, gpu, ram_gb, ssd, nivel_placa):
    cooler, p_cooler = _cooler(cpu)
    placa, p_placa = _placa(cpu, nivel_placa)
    ram_desc, p_ram = RAM[(ram_gb, cpu["mem"])]
    watts = consumo(cpu, gpu)
    w_psu, psu, p_psu = fuente(watts)
    _, gab, p_gab = _gabinete(gpu)
    piezas = [
        ("Procesador", f"{cpu['nombre']} ({cpu['nucleos']})", cpu["precio"]),
        ("Tarjeta madre", placa, p_placa),
        ("Memoria RAM", ram_desc, p_ram),
        ("Tarjeta de video", gpu["nombre"], gpu["precio"]),
        ("Almacenamiento", ssd[1], ssd[2]),
        ("Fuente de poder", psu, p_psu),
        ("Enfriamiento", cooler, p_cooler),
        ("Gabinete", gab, p_gab),
    ]
    return {"piezas": piezas, "total": sum(p for _, _, p in piezas), "watts": watts, "psu_w": w_psu,
            "ram_gb": ram_gb, "ssd_tb": ssd[0], "_cpu": cpu, "_gpu": gpu, "_nivel": nivel_placa}


def _notas(b):
    cpu, gpu = b["_cpu"], b["_gpu"]
    n = [f"Compatibilidad: socket {cpu['socket']} en procesador y tarjeta madre; memoria {cpu['mem']}.",
         f"Consumo estimado {b['watts']} W; con 30% de margen se recomienda fuente de {b['psu_w']} W."]
    if gpu["vram"]:
        n.append(f"Conector de la GPU: {gpu['conector']}. Verifica que la fuente lo incluya.")
    if gpu["largo"]:
        n.append("La GPU es larga (más de 320 mm): revisa el espacio libre del gabinete.")
    if cpu["mem"] == "DDR4":
        n.append("Plataforma DDR4: más barata ahora que la DDR5 está cara, pero sin ruta de mejora a futuro.")
    if cpu["socket"] == "AM5":
        n.append("AM5 tiene soporte de AMD hasta 2027 o más: puedes cambiar solo el procesador después.")
    if cpu["nombre"].endswith("Plus") or "9850X3D" in cpu["nombre"]:
        n.append("Procesador reciente: la tarjeta madre puede necesitar actualización de BIOS.")
    if gpu["vram"] and gpu["vram"] < 12:
        n.append("8 GB de VRAM se quedan cortos en juegos nuevos a altas texturas; bien para 1080p y esports.")
    if b["ram_gb"] == 16 and b["uso"] != "oficina":
        n.append("16 GB alcanzan, pero 32 GB es lo ideal; podrás agregar otro kit después.")
    return n


# ------------------------------------------------------------- texto y lenguaje
def formato(b, moneda="MXN", tipo_cambio=18.5):
    f = (lambda usd: f"${usd * tipo_cambio:,.0f} MXN") if moneda == "MXN" else (lambda usd: f"${usd:,.0f} USD")
    lineas = [f"BUILD SUGERIDO · {USOS[b['uso']]} · presupuesto {f(b['presupuesto'])}", ""]
    ancho = max(len(c) for c, _, _ in b["piezas"])
    for cat, desc, precio in b["piezas"]:
        lineas.append(f"{cat:<{ancho}}  {desc}  ·  {f(precio) if precio else 'incluido'}")
    lineas += ["", f"Total aproximado: {f(b['total'])}" + (f"   (te sobran {f(b['sobra'])})" if b["sobra"] > 0 else "")]
    if b.get("advertencia"):
        lineas.append("Aviso: " + b["advertencia"])
    lineas += [""] + [f"- {x}" for x in b["notas"]]
    lineas.append(f"- Precios de referencia ({ACTUALIZADO}); cambian seguido, compara en tiendas.")
    return "\n".join(lineas)


def _sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


PIDE_BUILD = re.compile(r"\b(pc|computadora|compu|build|equipo|arma|armar|armame|armarme|cotiza|cotizame|cotizacion)\b")
_NO_DINERO = re.compile(r"\b(rtx|gtx|rx|arc|ryzen\s*\d|core\s*ultra\s*\d|core\s*i\d|i[3579]|[abxz])\s*-?\s*\d+\w*")
_NUM = re.compile(r"(\$)?\s*(\d[\d,\.]*)\s*(k|mil)?\b(\s*(?:pesos|mxn|usd|dolares|dlls))?(?!\s*(?:w|gb|tb|hz|mm|p|fps|nm)\b)")


def _monto(t):
    t = re.sub(r"\b[2-8]k\b", " ", t)  # resoluciones (4k, 2k)
    t = _NO_DINERO.sub(" ", t)          # modelos de componentes (rtx 5070, ryzen 7 ...)
    mejores = []
    for m in _NUM.finditer(t):
        crudo = m.group(2).strip(".,")
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", crudo):
            valor = float(re.sub(r"[.,]", "", crudo))
        else:
            try:
                valor = float(crudo.replace(",", ""))
            except ValueError:
                continue
        if m.group(3):
            valor *= 1000
        pistas = bool(m.group(1) or m.group(3) or m.group(4))
        if valor >= 300:
            mejores.append((pistas, valor))
    if not mejores:
        return None
    return max(mejores)[1]  # prefiere el que tiene pistas de dinero ($, mil, k, pesos)


def interpretar(texto, moneda_def="MXN"):
    """Detecta si el mensaje pide un build con presupuesto. Devuelve dict o None."""
    t = _sin_acentos(texto)
    if not PIDE_BUILD.search(t):
        return None
    num = _monto(t)
    if num is None:
        return None
    moneda = "USD" if re.search(r"\b(usd|dolar|dolares|dlls)\b|us\$", t) else (
        "MXN" if re.search(r"\b(mxn|pesos)\b", t) else moneda_def)
    if re.search(r"\b4k\b", t):
        uso = "gaming_4k"
    elif re.search(r"1440|\b2k\b|qhd", t):
        uso = "gaming_1440"
    elif re.search(r"stream", t):
        uso = "streaming"
    elif re.search(r"edici|render|premiere|davinci|blender|diseno|after effects|\b3d\b|arquitectura", t):
        uso = "edicion"
    elif re.search(r"\bia\b|inteligencia artificial|llm|ollama|stable diffusion|machine learning|\bml\b", t):
        uso = "ia"
    elif re.search(r"oficina|escuela|tarea|ofimatica|word|excel|navegar|clases", t):
        uso = "oficina"
    else:
        uso = "gaming_1080"
    plataforma = "amd" if re.search(r"\b(amd|ryzen)\b", t) else "intel" if re.search(r"\bintel\b|core ultra", t) else "cualquiera"
    gpu = "nvidia" if re.search(r"nvidia|\brtx\b|geforce", t) else "cualquiera"
    return {"monto": num, "moneda": moneda, "uso": uso, "plataforma": plataforma, "marca_gpu": gpu}


def resumen_catalogo():
    """Texto compacto del catálogo para darle contexto actual al LLM."""
    c = ", ".join(x["nombre"].replace("AMD ", "").replace("Intel ", "") for x in CPUS)
    g = ", ".join(x["nombre"].replace("NVIDIA GeForce ", "").replace("AMD Radeon ", "").replace("Intel ", "")
                  for x in GPUS[1:])
    return (f"Catálogo de referencia ({ACTUALIZADO}):\n- CPUs: {c}.\n- GPUs: {g}.\n"
            "- RAM: DDR5 muy cara por escasez de memoria (32 GB ~400 USD); DDR4 mucho más barata.\n"
            "- NVIDIA canceló las RTX 50 Super; la siguiente generación (RTX 60) se espera hasta finales de 2027.\n"
            "- Zen 6 (AMD) y Nova Lake (Intel, socket LGA1954) se esperan en 2027; AM5 sigue vigente.")
