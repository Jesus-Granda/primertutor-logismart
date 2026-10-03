import math
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont

import ollama

import armador_pc as armador

MODELO = "llama3.2"
KEEP_ALIVE = "30m"          # mantiene el modelo cargado en memoria: respuestas más rápidas
OPCIONES_LLM = {"num_ctx": 4096, "num_predict": 700, "temperature": 0.4}
MAX_HISTORIAL = 12          # mensajes recientes que se envían al modelo (menos = más rápido)

# 1) Configuración del sistema (tema distinto al del ejemplo: armado de PCs)
MENSAJE_SISTEMA = f"""Eres PC Master, un técnico experto en armado de computadoras que enseña a
estudiantes y principiantes. Responde siempre en español, claro y directo.

Estilo:
- Respuestas breves: máximo unas 150 palabras, salvo que te pidan detalle o un paso a paso.
- Usa viñetas cortas. Explica el porqué de cada recomendación.

Sabes y debes cuidar:
1. Si falta información para recomendar, pregunta: presupuesto, uso, resolución del monitor y si ya tiene piezas.
2. Compatibilidad: socket y chipset, DDR4 vs DDR5, formato de placa y gabinete, largo de la GPU,
   altura del disipador, conectores de la fuente (8 pines, 12V-2x6), ranuras M.2.
3. Fuente de poder: consumo estimado de CPU + GPU + 75 W, más 20-30% de margen, 80 Plus Bronze o mejor.
4. Evitar cuellos de botella: CPU y GPU balanceados según la resolución.
5. Armado paso a paso: antiestática, CPU, RAM, M.2, disipador y pasta, placa al gabinete, fuente,
   GPU, cables, primer encendido, BIOS (XMP/EXPO) y drivers.
6. Si en la conversación aparece un "BUILD SUGERIDO", úsalo como referencia y no inventes otras piezas.

{armador.resumen_catalogo()}

Honestidad: los precios cambian mucho; no inventes modelos ni especificaciones. Si no estás
seguro de algo, dilo y recomienda verificar en tiendas y reseñas actuales."""

mensajes = [{"role": "system", "content": MENSAJE_SISTEMA}]

SUGERENCIAS = [
    ("¿Qué fuente necesito?", "¿Cómo calculo qué fuente de poder necesito para mi PC?"),
    ("Revisar compatibilidad", "¿Qué debo revisar para que todas las piezas sean compatibles?"),
    ("Pasos de armado", "Explícame paso a paso cómo armar una PC por primera vez."),
    ("¿DDR4 o DDR5 hoy?", "Con los precios actuales de la memoria, ¿me conviene DDR4 o DDR5?"),
    ("Aire o líquida", "¿Cómo elijo entre enfriamiento por aire y líquido?"),
]
USOS = list(armador.USOS.items())

# ------------------------------------------------------------------ temas
FUENTE = "Segoe UI"
MONO = "Consolas"
OSCURO = dict(
    g0=(15, 19, 25), g1=(22, 28, 36), blob1=(94, 170, 160), blob2=(122, 112, 178), blob_a=0.16,
    glass=(255, 255, 255), glass_a=0.045, btn_a=0.045, border_c=(255, 255, 255), border_a=0.10,
    shadow=(0, 0, 0), shadow_a=0.30, accent=(111, 184, 173), warn=(216, 178, 106), bad=(217, 123, 123),
    text="#e4e7ec", muted="#8b93a1", primary_fg="#0f1a19",
    chat_bg="#121820", input_bg="#161d26", user_bg="#22383a", user_fg="#e2f1ee", bot_bg="#1a222c",
    bot_fg="#dde2ea", nota_bg="#1c2430", nota_fg="#a9b2bf", code_bg="#0e1319", code_fg="#8fd1c6",
    build_bg="#162229", build_fg="#d6e6e3", n_user="#8fd1c6", n_bot="#9aa7b8")
CLARO = dict(
    g0=(245, 247, 250), g1=(229, 234, 240), blob1=(94, 170, 160), blob2=(150, 140, 200), blob_a=0.18,
    glass=(255, 255, 255), glass_a=0.60, btn_a=0.18, border_c=(40, 50, 70), border_a=0.11,
    shadow=(60, 70, 90), shadow_a=0.12, accent=(47, 133, 121), warn=(184, 134, 40), bad=(190, 80, 80),
    text="#1f2733", muted="#6b7483", primary_fg="#ffffff",
    chat_bg="#fbfcfd", input_bg="#ffffff", user_bg="#dcefeb", user_fg="#1c3a35", bot_bg="#f0f3f7",
    bot_fg="#1f2733", nota_bg="#eceff4", nota_fg="#4d5665", code_bg="#e6ebf1", code_fg="#226b61",
    build_bg="#edf5f3", build_fg="#1f3330", n_user="#2f8579", n_bot="#5d6878")


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def hx(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mezcla_tema(a, b, p):
    out = {}
    for k, vb in b.items():
        va = a[k]
        if isinstance(vb, str):
            out[k] = hx(mix(rgb(va), rgb(vb), p))
        elif isinstance(vb, tuple):
            out[k] = mix(va, vb, p)
        else:
            out[k] = va + (vb - va) * p
    return out


def rr(x1, y1, x2, y2, r):
    """Puntos de un rectángulo redondeado (polígono suavizado)."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
            x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


INLINE = re.compile(r"(\*\*.+?\*\*|`[^`\n]+`)")


# ----------------------------------------------------------- componentes
class Vidrio:
    """Panel 'glass': tinte translúcido calculado sobre el fondo, borde fino, brillo y sombra suave."""

    def __init__(self, app, radio=18):
        c = app.c
        self.app, self.r, self.box = app, radio, (0, 0, 1, 1)
        self.sombra = c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
        self.cuerpo = c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True)
        self.brillo = c.create_line(0, 0, 0, 0)

    def colocar(self, x1, y1, x2, y2):
        self.box = (x1, y1, x2, y2)
        c, r = self.app.c, self.r
        c.coords(self.sombra, rr(x1, y1 + 4, x2, y2 + 4, r))
        c.coords(self.cuerpo, rr(x1, y1, x2, y2, r))
        c.coords(self.brillo, x1 + r, y1 + 1.5, x2 - r, y1 + 1.5)

    def relleno(self):
        a = self.app
        x1, y1, x2, y2 = self.box
        return mix(a.bg_at((y1 + y2) / 2 / max(a.H, 1)), a.T["glass"], a.T["glass_a"])

    def pintar(self, enfoque=0.0):
        a, T, c = self.app, self.app.T, self.app.c
        x1, y1, x2, y2 = self.box
        bg = a.bg_at((y1 + y2) / 2 / max(a.H, 1))
        fill = self.relleno()
        borde = mix(mix(fill, T["border_c"], T["border_a"] * 1.4), T["accent"], 0.55 * enfoque)
        c.itemconfigure(self.sombra, fill=hx(mix(bg, T["shadow"], T["shadow_a"] * 0.5)))
        c.itemconfigure(self.cuerpo, fill=hx(fill), outline=hx(borde), width=1)
        c.itemconfigure(self.brillo, fill=hx(mix(fill, (255, 255, 255), 0.18)))


class Boton:
    """Botón dibujado en el canvas: normal, primario, seleccionable (segmentado) o casilla."""

    def __init__(self, app, texto, cmd, primario=False, tam=9, casilla=False, alinear="center"):
        c = app.c
        self.app, self.cmd, self.primario, self.casilla, self.alinear = app, cmd, primario, casilla, alinear
        self.hover = self.meta = 0.0
        self.activo, self.seleccionado = True, False
        self.box = (0, 0, 10, 10)
        self.cuerpo = c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True)
        self.caja = c.create_rectangle(0, 0, 0, 0, state="normal" if casilla else "hidden")
        self.palomita = c.create_line(0, 0, 0, 0, width=2, state="hidden", capstyle="round", joinstyle="round")
        self.txt = c.create_text(0, 0, text=texto, font=(FUENTE, tam, "bold" if primario else "normal"),
                                 anchor="w" if (alinear == "w" or casilla) else "center")
        for it in (self.cuerpo, self.txt, self.caja, self.palomita):
            c.tag_bind(it, "<Enter>", self._entra)
            c.tag_bind(it, "<Leave>", self._sale)
            c.tag_bind(it, "<Button-1>", self._clic)
        app.botones.append(self)

    def _entra(self, _):
        if self.activo:
            self.meta = 1.0
            self.app.c.config(cursor="hand2")

    def _sale(self, _):
        self.meta = 0.0
        self.app.c.config(cursor="")

    def _clic(self, e):
        if self.activo and self.cmd:
            self.cmd()

    def colocar(self, x, y, w, h):
        self.box = (x, y, w, h)
        c = self.app.c
        c.coords(self.cuerpo, rr(x, y, x + w, y + h, min(10, h / 2)))
        if self.casilla:
            cy = y + h / 2
            c.coords(self.caja, x + 10, cy - 7, x + 24, cy + 7)
            c.coords(self.palomita, x + 13, cy, x + 16, cy + 3.5, x + 21.5, cy - 3.5)
            c.coords(self.txt, x + 34, cy)
        elif self.alinear == "w":
            c.coords(self.txt, x + 12, y + h / 2)
        else:
            c.coords(self.txt, x + w / 2, y + h / 2)

    def texto(self, t):
        self.app.c.itemconfigure(self.txt, text=t)
        self.app.sucio = True

    def set_activo(self, si):
        self.activo = si
        if not si:
            self.meta = 0.0
        self.app.sucio = True

    def set_sel(self, si):
        self.seleccionado = si
        self.app.sucio = True

    def avanzar(self, dt, anim):
        antes = self.hover
        self.hover = self.hover + (self.meta - self.hover) * min(1.0, dt * 12) if anim else self.meta
        if abs(self.meta - self.hover) < 0.01:
            self.hover = self.meta
        return antes != self.hover

    def pintar(self):
        a, T, c = self.app, self.app.T, self.app.c
        x, y, w, h = self.box
        hv = self.hover
        bg = a.bg_at((y + h / 2) / max(a.H, 1))
        acc = T["accent"]
        txt_col = rgb(T["text"])
        if self.primario:
            fill = mix(acc, (255, 255, 255), 0.12 * hv)
            borde = fill
            col = rgb(T["primary_fg"])
        else:
            fill = mix(bg, T["glass"], T["glass_a"] + T["btn_a"])
            fill = mix(fill, acc, 0.07 * hv)
            borde = mix(mix(fill, T["border_c"], T["border_a"] * 1.6), acc, 0.45 * hv)
            col = mix(txt_col, acc, 0.35 * hv)
            if self.seleccionado and not self.casilla:
                fill = mix(fill, acc, 0.20)
                borde = mix(fill, acc, 0.75)
                col = mix(txt_col, acc, 0.65)
        if not self.activo:
            fill, borde, col = mix(fill, bg, 0.5), mix(borde, bg, 0.5), rgb(T["muted"])
        c.itemconfigure(self.cuerpo, fill=hx(fill), outline=hx(borde), width=1)
        c.itemconfigure(self.txt, fill=hx(col))
        if self.casilla:
            on = self.seleccionado
            c.itemconfigure(self.caja, fill=hx(acc if on else mix(fill, bg, 0.3)),
                            outline=hx(acc if on else mix(borde, txt_col, 0.25)))
            c.itemconfigure(self.palomita, fill=T["primary_fg"], state="normal" if on else "hidden")


# ------------------------------------------------------------ aplicación
class PCMaster:
    M = 16
    SIDEBAR = 300
    ANILLOS = 16

    def __init__(self, root):
        self.root = root
        self.T = dict(OSCURO)
        self.tema = "oscuro"
        self.desde = self.destino = None
        self.tp = 1.0
        self.anim = True
        self.t = 0.0
        self.sucio = True
        self.ultimo = time.perf_counter()
        self.cola = queue.Queue()
        self.ocupado = self.streaming = self.cancelar = False
        self.foco = 0.0
        self.foco_meta = 0.0
        self.modo, self.etiqueta = "cargando", "cargando modelo"
        self.modelo = MODELO
        self.modelos = [MODELO]
        self.botones = []
        self.ultimo_build = None
        self.uso, self.moneda, self.plataforma, self.marca_gpu = "gaming_1080", "MXN", "cualquiera", "cualquiera"
        self.explicar = True
        self.W, self.H = 1100, 760
        self.ct, self.chat_h = 200, 300
        self.chat_yview = (0.0, 1.0)
        root.title("PC Master  ·  Tutor de armado de PCs")
        root.geometry("1100x760")
        root.minsize(1040, 700)

        c = self.c = tk.Canvas(root, highlightthickness=0, bd=0)
        c.pack(fill="both", expand=True)
        self.fondo = [c.create_rectangle(0, 0, 1, 1, width=0) for _ in range(32)]
        self.blobs = [[c.create_oval(0, 0, 1, 1, width=0) for _ in range(self.ANILLOS)] for _ in range(2)]

        # ---------- cabecera
        self.v_cab = Vidrio(self, 16)
        self.logo = c.create_oval(0, 0, 1, 1, width=0)
        self.titulo = c.create_text(0, 0, anchor="w", text="PC Master", font=(FUENTE, 16, "bold"))
        self.sub = c.create_text(0, 0, anchor="w", text="Tutor de armado de PCs y componentes", font=(FUENTE, 9))
        self.dot = c.create_oval(0, 0, 1, 1, width=0)
        self.lbl_estado = c.create_text(0, 0, anchor="w", font=(FUENTE, 9))
        self.b_modelo = Boton(self, f"Modelo: {self.modelo}", self.menu_modelos)
        self.b_tema = Boton(self, "Tema claro", self.cambiar_tema)
        self.b_anim = Boton(self, "Animación: sí", self.alternar_anim)

        # ---------- barra lateral: armador rápido
        self.v_side = Vidrio(self, 18)
        self.s_titulo = c.create_text(0, 0, anchor="w", text="Armador rápido", font=(FUENTE, 12, "bold"))
        self.s_sub = c.create_text(0, 0, anchor="w", text="Un build al instante, sin esperar al modelo", font=(FUENTE, 8))
        self.etqs = {k: c.create_text(0, 0, anchor="w", text=t, font=(FUENTE, 8, "bold")) for k, t in (
            ("pres", "PRESUPUESTO"), ("uso", "USO PRINCIPAL"), ("cpu", "PROCESADOR"), ("gpu", "TARJETA DE VIDEO"))}
        self.lbl_tc = c.create_text(0, 0, anchor="w", text="Tipo de cambio (MXN por USD)", font=(FUENTE, 8))
        self.e_pres = tk.Entry(c, font=(FUENTE, 11), relief="flat", bd=0, highlightthickness=1)
        self.e_pres.insert(0, "25000")
        self.e_tc = tk.Entry(c, font=(FUENTE, 10), relief="flat", bd=0, highlightthickness=1, justify="center")
        self.e_tc.insert(0, "18.5")
        self.w_pres = c.create_window(0, 0, window=self.e_pres, anchor="nw")
        self.w_tc = c.create_window(0, 0, window=self.e_tc, anchor="nw")
        self.e_pres.bind("<Return>", lambda e: self.armar_desde_panel())
        self.b_mon = {m: Boton(self, m, lambda m=m: self._sel("moneda", m)) for m in ("MXN", "USD")}
        self.b_uso = {k: Boton(self, t, lambda k=k: self._sel("uso", k), tam=8) for k, t in USOS}
        self.b_cpu = {k: Boton(self, t, lambda k=k: self._sel("plataforma", k), tam=8)
                      for k, t in (("cualquiera", "Cualquiera"), ("amd", "AMD"), ("intel", "Intel"))}
        self.b_gpu = {k: Boton(self, t, lambda k=k: self._sel("marca_gpu", k), tam=8)
                      for k, t in (("cualquiera", "Cualquiera"), ("nvidia", "NVIDIA"), ("amd", "AMD"), ("intel", "Intel"))}
        self.b_explicar = Boton(self, "Explicar el build con el tutor (IA)", self._toggle_explicar, casilla=True, tam=8)
        self.b_armar = Boton(self, "Armar al instante", self.armar_desde_panel, primario=True, tam=10)
        self.s_error = c.create_text(0, 0, anchor="w", text="", font=(FUENTE, 8), width=self.SIDEBAR - 32)
        self.s_nota = c.create_text(0, 0, anchor="sw", font=(FUENTE, 8), width=self.SIDEBAR - 32,
                                    text=f"Precios de referencia en USD ({armador.ACTUALIZADO}). "
                                         "Cambian seguido: compara antes de comprar.")

        # ---------- sugerencias
        self.chips = [Boton(self, t, lambda p=p: self.enviar_texto(p), tam=8) for t, p in SUGERENCIAS]

        # ---------- chat
        self.v_chat = Vidrio(self, 18)
        self.chat = tk.Text(c, wrap="word", font=(FUENTE, 11), relief="flat", bd=0, highlightthickness=0,
                            padx=8, pady=8, cursor="arrow", state="disabled", yscrollcommand=self._scroll)
        self.win_chat = c.create_window(0, 0, window=self.chat, anchor="nw")
        self.thumb = c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
        self.progreso = c.create_rectangle(0, 0, 1, 1, width=0, state="hidden")

        # ---------- entrada
        self.v_in = Vidrio(self, 16)
        self.entrada = tk.Text(c, wrap="word", font=(FUENTE, 11), relief="flat", bd=0, highlightthickness=0,
                               padx=8, pady=6)
        self.win_in = c.create_window(0, 0, window=self.entrada, anchor="nw")
        self.entrada.bind("<Return>", self._enter)
        self.entrada.bind("<FocusIn>", lambda e: self._set_foco(1.0))
        self.entrada.bind("<FocusOut>", lambda e: self._set_foco(0.0))
        self.b_enviar = Boton(self, "Enviar", self.enviar_o_detener, primario=True, tam=10)

        # ---------- pie
        self.b_res = Boton(self, "Resumen del historial", self.resumen)
        self.b_copiar = Boton(self, "Copiar último build", self.copiar_build)
        self.b_exp = Boton(self, "Exportar chat", self.exportar)
        self.b_nuevo = Boton(self, "Nueva conversación", self.limpiar)
        self.hint = c.create_text(0, 0, anchor="e", text="Enter envía  ·  Shift+Enter nueva línea", font=(FUENTE, 8))

        self._sel("uso", self.uso)
        self._sel("moneda", self.moneda)
        self._sel("plataforma", self.plataforma)
        self._sel("marca_gpu", self.marca_gpu)
        self.b_explicar.set_sel(self.explicar)
        self._aplicar_tema()
        c.bind("<Configure>", self._layout)
        self._nota("Hola, soy PC Master.\n"
                   "Usa el Armador rápido de la izquierda para tener un build al instante, o escríbeme algo como "
                   "«ármame una PC gamer de 25 mil» o «PC para edición con 1500 dólares».\n"
                   "También te explico compatibilidad, fuentes de poder, enfriamiento y el armado paso a paso.")
        self.entrada.focus_set()
        threading.Thread(target=self._precargar, daemon=True).start()
        self._frame()

    # ------------------------------------------------------------ colores
    def bg_at(self, yf):
        yf = max(0.0, min(1.0, yf))
        return mix(self.T["g0"], self.T["g1"], yf)

    # ------------------------------------------------------------ layout
    def _layout(self, _=None):
        W, H, M, c = self.c.winfo_width(), self.c.winfo_height(), self.M, self.c
        if W < 200 or H < 200:
            return
        self.W, self.H = W, H
        n = len(self.fondo)
        for i, b in enumerate(self.fondo):
            c.coords(b, 0, i * H / n, W, (i + 1) * H / n + 1)
        self._pintar_fondo()

        # cabecera
        self.v_cab.colocar(M, M, W - M, M + 56)
        cy = M + 28
        c.coords(self.logo, M + 20, cy - 6, M + 32, cy + 6)
        c.coords(self.titulo, M + 42, cy)
        c.coords(self.sub, M + 42 + tkfont.Font(family=FUENTE, size=16, weight="bold").measure("PC Master") + 14, cy + 1)
        x = W - M - 14
        for b, w in ((self.b_anim, 118), (self.b_tema, 100), (self.b_modelo, 170)):
            x -= w
            b.colocar(x, cy - 15, w, 30)
            x -= 8
        c.coords(self.dot, x - 150, cy - 4, x - 142, cy + 4)
        c.coords(self.lbl_estado, x - 134, cy)

        # barra lateral
        top = M + 72
        sx, sw = M, self.SIDEBAR
        self.v_side.colocar(sx, top, sx + sw, H - M)
        x0, iw = sx + 16, sw - 32
        y = top + 18
        c.coords(self.s_titulo, x0, y + 4)
        c.coords(self.s_sub, x0, y + 24)
        y += 48
        c.coords(self.etqs["pres"], x0, y)
        y += 12
        c.coords(self.w_pres, x0, y)
        c.itemconfigure(self.w_pres, width=iw - 110, height=34)
        self.b_mon["MXN"].colocar(x0 + iw - 102, y, 50, 34)
        self.b_mon["USD"].colocar(x0 + iw - 50, y, 50, 34)
        y += 44
        c.coords(self.lbl_tc, x0, y + 13)
        c.coords(self.w_tc, x0 + iw - 70, y)
        c.itemconfigure(self.w_tc, width=70, height=26)
        y += 42
        c.coords(self.etqs["uso"], x0, y)
        y += 12
        cw = (iw - 6) / 2
        for i, (k, _) in enumerate(USOS):
            self.b_uso[k].colocar(x0 + (i % 2) * (cw + 6), y + (i // 2) * 36, cw, 30)
        y += ((len(USOS) + 1) // 2) * 36 + 10
        c.coords(self.etqs["cpu"], x0, y)
        y += 12
        self._fila(self.b_cpu.values(), x0, y, iw, 30)
        y += 44
        c.coords(self.etqs["gpu"], x0, y)
        y += 12
        self._fila(self.b_gpu.values(), x0, y, iw, 30)
        y += 42
        self.b_explicar.colocar(x0, y, iw, 30)
        y += 40
        self.b_armar.colocar(x0, y, iw, 40)
        y += 48
        c.coords(self.s_error, x0, y + 6)
        c.coords(self.s_nota, x0, H - M - 14)

        # zona principal
        mx1, mx2 = sx + sw + M, W - M
        chip_w = (mx2 - mx1 - 8 * (len(self.chips) - 1)) / len(self.chips)
        for i, b in enumerate(self.chips):
            b.colocar(mx1 + i * (chip_w + 8), top, chip_w, 32)
        fy = H - M - 34
        ib = fy - 12
        it_ = ib - 70
        cb = it_ - 14
        ct = top + 44
        self.ct, self.chat_h = ct, cb - ct
        self.v_chat.colocar(mx1, ct, mx2, cb)
        c.coords(self.win_chat, mx1 + 10, ct + 10)
        c.itemconfigure(self.win_chat, width=mx2 - mx1 - 30, height=cb - ct - 20)
        self.prog_box = (mx1 + 24, cb + 5, mx2 - 24)
        self.v_in.colocar(mx1, it_, mx2, ib)
        c.coords(self.win_in, mx1 + 10, it_ + 10)
        c.itemconfigure(self.win_in, width=mx2 - mx1 - 20 - 118, height=50)
        self.b_enviar.colocar(mx2 - 10 - 100, it_ + 14, 100, 42)
        x = mx1
        for b, w in ((self.b_res, 160), (self.b_copiar, 150), (self.b_exp, 115), (self.b_nuevo, 150)):
            b.colocar(x, fy, w, 34)
            x += w + 8
        c.coords(self.hint, mx2, fy + 17)
        c.itemconfigure(self.hint, state="normal" if mx2 - x > 230 else "hidden")
        self._thumb()
        self.sucio = True

    def _fila(self, botones, x, y, w, h):
        botones = list(botones)
        bw = (w - 6 * (len(botones) - 1)) / len(botones)
        for i, b in enumerate(botones):
            b.colocar(x + i * (bw + 6), y, bw, h)

    def _scroll(self, a, b):
        self.chat_yview = (float(a), float(b))
        self._thumb()

    def _thumb(self):
        f, l = self.chat_yview
        if f <= 0.001 and l >= 0.999:
            self.c.itemconfigure(self.thumb, state="hidden")
            return
        top, hgt = self.ct + 14, self.chat_h - 28
        y1 = top + f * hgt
        y2 = max(top + l * hgt, y1 + 24)
        x = self.v_chat.box[2] - 10
        self.c.coords(self.thumb, rr(x, y1, x + 4, y2, 2))
        self.c.itemconfigure(self.thumb, state="normal")

    # -------------------------------------------------------------- tema
    def _aplicar_tema(self):
        T, t = self.T, self.chat
        sel = hx(mix(rgb(T["chat_bg"]), T["accent"], 0.45))
        t.configure(bg=T["chat_bg"], fg=T["text"], selectbackground=sel, selectforeground=T["text"])
        borde = hx(mix(rgb(T["input_bg"]), T["border_c"], T["border_a"] * 2))
        for w in (self.entrada, self.e_pres, self.e_tc):
            w.configure(bg=T["input_bg"], fg=T["text"], insertbackground=hx(T["accent"]),
                        selectbackground=sel, selectforeground=T["text"])
        for w in (self.e_pres, self.e_tc):
            w.configure(highlightbackground=borde, highlightcolor=hx(T["accent"]))
        t.tag_config("nombre_u", foreground=T["n_user"], lmargin1=170, lmargin2=170, font=(FUENTE, 8, "bold"), spacing1=12)
        t.tag_config("nombre_b", foreground=T["n_bot"], lmargin1=4, lmargin2=4, font=(FUENTE, 8, "bold"), spacing1=12)
        t.tag_config("usuario", background=T["user_bg"], foreground=T["user_fg"],
                     lmargin1=170, lmargin2=170, rmargin=20, spacing1=1, spacing3=1)
        t.tag_config("bot", background=T["bot_bg"], foreground=T["bot_fg"], lmargin1=18, lmargin2=18,
                     rmargin=60, spacing1=1, spacing3=1)
        t.tag_config("build", background=T["build_bg"], foreground=T["build_fg"], font=(MONO, 10),
                     lmargin1=18, lmargin2=18, rmargin=20, spacing1=1, spacing3=1)
        t.tag_config("stream", foreground=T["muted"], lmargin1=18, lmargin2=18, rmargin=60)
        t.tag_config("nota", background=T["nota_bg"], foreground=T["nota_fg"], lmargin1=18, lmargin2=18,
                     rmargin=20, spacing1=1, spacing3=1)
        for tag, fondo in (("bot", T["bot_bg"]), ("build", T["build_bg"]), ("nota", T["nota_bg"])):
            try:  # colorea el margen izquierdo para que la tarjeta no tenga huecos (Tk 8.6.6+)
                t.tag_config(tag, lmargincolor=fondo)
            except tk.TclError:
                pass
        t.tag_config("negrita", font=(FUENTE, 11, "bold"))
        t.tag_config("titulo_build", font=(MONO, 10, "bold"), foreground=hx(T["accent"]))
        t.tag_config("codigo", font=(MONO, 10), foreground=T["code_fg"], background=T["code_bg"])

    def cambiar_tema(self):
        self.desde = dict(self.T)
        self.destino = dict(CLARO if self.tema == "oscuro" else OSCURO)
        self.tema = "claro" if self.tema == "oscuro" else "oscuro"
        self.b_tema.texto("Tema oscuro" if self.tema == "claro" else "Tema claro")
        self.tp = 0.0 if self.anim else 1.0
        if not self.anim:
            self.T = dict(self.destino)
            self._aplicar_tema()
            self._pintar_fondo()
        self.sucio = True

    def alternar_anim(self):
        self.anim = not self.anim
        self.b_anim.texto("Animación: " + ("sí" if self.anim else "no"))
        self.sucio = True

    def _set_foco(self, v):
        self.foco_meta = v

    def _sel(self, campo, valor):
        setattr(self, campo, valor)
        grupo = {"uso": self.b_uso, "moneda": self.b_mon, "plataforma": self.b_cpu, "marca_gpu": self.b_gpu}[campo]
        for k, b in grupo.items():
            b.set_sel(k == valor)
        if campo == "moneda":
            self.e_tc.configure(state="normal" if valor == "MXN" else "disabled")

    def _toggle_explicar(self):
        self.explicar = not self.explicar
        self.b_explicar.set_sel(self.explicar)

    # ------------------------------------------------------ animación
    def _frame(self):
        ahora = time.perf_counter()
        dt = min(ahora - self.ultimo, 0.1)
        self.ultimo = ahora
        self._cola()
        if self.anim:
            self.t += dt
        if self.tp < 1.0:
            self.tp = min(1.0, self.tp + dt / 0.4)
            p = self.tp * self.tp * (3 - 2 * self.tp)
            self.T = mezcla_tema(self.desde, self.destino, p)
            self._aplicar_tema()
            self._pintar_fondo()
            self.sucio = True
        f0 = self.foco
        self.foco += (self.foco_meta - self.foco) * (min(1.0, dt * 10) if self.anim else 1.0)
        if abs(self.foco - self.foco_meta) < 0.01:
            self.foco = self.foco_meta
        mov = f0 != self.foco
        for b in self.botones:
            mov |= b.avanzar(dt, self.anim)
        if self.anim:
            self._mover_blobs()
        if self.sucio or mov or self.ocupado or self.modo == "cargando":
            self._pintar()
            self.sucio = False
        self.root.after(33, self._frame)

    def _pintar_fondo(self):
        n = len(self.fondo)
        for i, b in enumerate(self.fondo):
            self.c.itemconfigure(b, fill=hx(self.bg_at((i + 0.5) / n)))
        for k, anillos in enumerate(self.blobs):
            col = self.T["blob1" if k == 0 else "blob2"]
            base = self.bg_at(0.5)
            for j, o in enumerate(anillos):
                a = self.T["blob_a"] * ((j + 1) / len(anillos)) ** 1.6
                self.c.itemconfigure(o, fill=hx(mix(base, col, a)))
        self._mover_blobs()

    def _mover_blobs(self):
        W, H, t = self.W, self.H, self.t
        R = max(W, H) * 0.42
        for k, anillos in enumerate(self.blobs):
            ph = k * 2.6
            cx = W * (0.30 + 0.45 * k + 0.08 * math.sin(t * 0.05 + ph))
            cy = H * (0.30 + 0.40 * k + 0.08 * math.cos(t * 0.04 + ph))
            for j, o in enumerate(anillos):
                r = R * (1 - j / len(anillos) * 0.9)
                self.c.coords(o, cx - r, cy - r, cx + r, cy + r)

    def _pintar(self):
        T, c, t = self.T, self.c, self.t
        self.v_cab.pintar()
        self.v_side.pintar()
        self.v_chat.pintar()
        self.v_in.pintar(self.foco)
        for it in (self.titulo, self.s_titulo):
            c.itemconfigure(it, fill=T["text"])
        for it in (self.sub, self.s_sub, self.hint, self.lbl_tc, self.s_nota):
            c.itemconfigure(it, fill=T["muted"])
        for it in self.etqs.values():
            c.itemconfigure(it, fill=hx(mix(rgb(T["muted"]), T["accent"], 0.35)))
        c.itemconfigure(self.s_error, fill=hx(T["bad"]))
        c.itemconfigure(self.logo, fill=hx(T["accent"]))
        col = {"ok": T["accent"], "busy": T["warn"], "cargando": T["warn"], "error": T["bad"]}[self.modo]
        if self.modo in ("busy", "cargando"):
            col = mix(col, self.bg_at(0.05), 0.35 * (1 + math.sin(t * 5)) / 2)
            texto = self.etiqueta + "." * (int(t * 2.5) % 4)
        else:
            texto = self.etiqueta
        c.itemconfigure(self.dot, fill=hx(col))
        c.itemconfigure(self.lbl_estado, text=texto, fill=hx(mix(rgb(T["muted"]), col, 0.5)))
        if self.ocupado and self.anim:
            x0, y, x1 = self.prog_box
            p = (math.sin(t * 2.0) + 1) / 2
            w = 120
            xx = x0 + (x1 - x0 - w) * p
            c.coords(self.progreso, xx, y, xx + w, y + 2)
            c.itemconfigure(self.progreso, fill=hx(mix(self.bg_at(0.9), T["accent"], 0.7)), state="normal")
        else:
            c.itemconfigure(self.progreso, state="hidden")
        c.itemconfigure(self.thumb, fill=hx(mix(rgb(T["chat_bg"]), rgb(T["muted"]), 0.5)))
        for b in self.botones:
            b.pintar()

    # ------------------------------------------------- render de mensajes
    @staticmethod
    def _pref(base):
        return "  " if base == "usuario" else ""

    def _linea(self, texto, base, extra=()):
        self.chat.insert("end", self._pref(base) + texto + "  \n", (base,) + extra)

    def _render(self, texto, base):
        self.chat.insert("end", " \n", (base,))
        en_codigo = False
        for linea in texto.strip().split("\n"):
            if linea.strip().startswith("```"):
                en_codigo = not en_codigo
                continue
            if en_codigo:
                self._linea(linea or " ", base, ("codigo",))
                continue
            m = re.match(r"^#{1,6}\s+(.*)", linea)
            if m:
                self._linea(m.group(1).replace("**", ""), base, ("negrita",))
                continue
            linea = re.sub(r"^(\s*)[-*]\s+", r"\1• ", linea)
            if not linea.strip():
                self.chat.insert("end", " \n", (base,))
                continue
            self.chat.insert("end", self._pref(base), (base,))
            for parte in INLINE.split(linea):
                if len(parte) > 4 and parte.startswith("**") and parte.endswith("**"):
                    self.chat.insert("end", parte[2:-2], (base, "negrita"))
                elif len(parte) > 2 and parte.startswith("`") and parte.endswith("`"):
                    self.chat.insert("end", parte[1:-1], (base, "codigo"))
                else:
                    self.chat.insert("end", parte, (base,))
            self.chat.insert("end", "  \n", (base,))
        self.chat.insert("end", " \n", (base,))

    def _render_build(self, texto):
        self.chat.insert("end", " \n", ("build",))
        for i, linea in enumerate(texto.split("\n")):
            self._linea(linea, "build", ("titulo_build",) if i == 0 else ())
        self.chat.insert("end", " \n", ("build",))

    def _editar(self, fn):
        self.chat.config(state="normal")
        fn()
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _mensaje(self, texto, es_usuario):
        def f():
            self.chat.insert("end", "Tú\n" if es_usuario else "PC Master\n", "nombre_u" if es_usuario else "nombre_b")
            self._render(texto, "usuario" if es_usuario else "bot")
        self._editar(f)

    def _build_chat(self, texto):
        def f():
            self.chat.insert("end", "PC Master  ·  armador rápido\n", "nombre_b")
            self._render_build(texto)
        self._editar(f)

    def _nota(self, texto):
        self._editar(lambda: (self.chat.insert("end", "\n"), self._render(texto, "nota")))

    # ------------------------------------------------------ estado / cola
    def _estado(self, modo, etiqueta):
        self.modo, self.etiqueta = modo, etiqueta
        self.sucio = True

    def _set_busy(self, si, etiqueta="pensando"):
        self.ocupado = si
        if si:
            self._estado("busy", etiqueta)
        elif self.modo != "error":
            self._estado("ok", f"listo  ·  {self.modelo}")
        self.b_enviar.texto("Detener" if si else "Enviar")
        self.b_res.set_activo(not si)
        for b in self.chips:
            b.set_activo(not si)

    def _cola(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "token":
                    self._token(dato)
                elif tipo == "fin":
                    self._fin(*dato)
                elif tipo == "error":
                    self._error(dato)
                elif tipo == "resumen":
                    self._nota("Resumen del tutor:\n" + dato)
                    self._set_busy(False)
                elif tipo == "precarga":
                    ok, info, modelos = dato
                    if modelos:
                        self.modelos = modelos
                    if not self.ocupado:
                        self._estado("ok", f"listo  ·  {self.modelo}") if ok else self._estado("error", info)
        except queue.Empty:
            pass

    # ------------------------------------------------------ modelo / LLM
    def _precargar(self):
        """Carga el modelo en memoria al abrir el programa: la primera respuesta ya no tarda."""
        modelos = []
        try:
            modelos = sorted(m.model for m in ollama.list().models)
        except Exception:
            pass
        try:
            ollama.generate(model=self.modelo, prompt="", keep_alive=KEEP_ALIVE)
            self.cola.put(("precarga", (True, "", modelos)))
        except Exception as e:
            msg = "Ollama sin conexión" if "connect" in str(e).lower() else "modelo no disponible"
            self.cola.put(("precarga", (False, f"{msg} (el armador sí funciona)", modelos)))

    def menu_modelos(self):
        T = self.T
        menu = tk.Menu(self.root, tearoff=0, bg=T["chat_bg"], fg=T["text"], activebackground=hx(T["accent"]),
                       activeforeground=T["primary_fg"], bd=0, font=(FUENTE, 9))
        for m in self.modelos or [self.modelo]:
            actual = m in (self.modelo, self.modelo + ":latest")
            menu.add_command(label=("•  " if actual else "    ") + m,
                             command=lambda m=m: self._usar_modelo(m))
        menu.add_separator()
        menu.add_command(label="    Más rápido: ollama pull llama3.2:1b", state="disabled")
        x, y, w, h = self.b_modelo.box
        menu.tk_popup(self.root.winfo_rootx() + int(x), self.root.winfo_rooty() + int(y + h + 4))

    def _usar_modelo(self, m):
        if self.ocupado:
            return
        self.modelo = m
        self.b_modelo.texto(f"Modelo: {m.replace(':latest', '')}")
        self._estado("cargando", "cargando modelo")
        threading.Thread(target=self._precargar, daemon=True).start()

    def _historial(self, extra=None):
        recientes = mensajes[1:][-MAX_HISTORIAL:]
        return [mensajes[0]] + recientes + (extra or [])

    def _lanzar(self, pedido, guardar=True):
        self.streaming = self.cancelar = False
        self._set_busy(True)
        threading.Thread(target=self._worker, args=(pedido, guardar), daemon=True).start()

    def _worker(self, pedido, guardar):
        texto = ""
        try:
            for ch in ollama.chat(model=self.modelo, messages=pedido, stream=True,
                                  options=OPCIONES_LLM, keep_alive=KEEP_ALIVE):
                if self.cancelar:
                    texto += "\n\n_(respuesta detenida)_"
                    break
                t = ch["message"]["content"]
                texto += t
                self.cola.put(("token", t))
            self.cola.put(("fin", (texto, guardar)))
        except Exception as e:
            self.cola.put(("error", str(e)))

    def _token(self, t):
        def f():
            if not self.streaming:
                self.streaming = True
                self.chat.insert("end", "PC Master\n", "nombre_b")
                self.chat.mark_set("ini", "end-1c")
                self.chat.mark_gravity("ini", "left")
            self.chat.insert("end", t, "stream")
        self._editar(f)

    def _fin(self, texto, guardar):
        def f():
            if self.streaming:
                self.chat.delete("ini", "end-1c")
            else:
                self.chat.insert("end", "PC Master\n", "nombre_b")
            self._render(texto or "(sin respuesta)", "bot")
        self._editar(f)
        if guardar and texto:
            mensajes.append({"role": "assistant", "content": texto})
        self.streaming = False
        self._set_busy(False)

    def _error(self, msg):
        if self.streaming:
            self._editar(lambda: self.chat.delete("ini", "end-1c"))
            self.streaming = False
        if mensajes[-1]["role"] == "user":
            mensajes.pop()  # la pregunta no se pudo procesar
        self._nota("No pude conectar con el modelo de lenguaje.\n"
                   f"Revisa que Ollama esté abierto y que exista el modelo ({self.modelo}).\n"
                   "El Armador rápido sí funciona sin Ollama.\n"
                   f"Detalle: {msg}")
        self._set_busy(False)
        self._estado("error", "Ollama sin conexión")

    # ------------------------------------------------------------ chat
    def _enter(self, e):
        if e.state & 0x1:  # Shift: salto de línea normal
            return None
        self.enviar_o_detener()
        return "break"

    def enviar_o_detener(self):
        if self.ocupado:
            self.cancelar = True
            return
        self.enviar_texto(self.entrada.get("1.0", "end").strip())

    def enviar_texto(self, pregunta):
        if self.ocupado or not pregunta:
            return
        self.entrada.delete("1.0", "end")
        self._mensaje(pregunta, True)
        pedido_build = armador.interpretar(pregunta, self.moneda)
        if pedido_build:
            self._armar(pedido_build, pregunta)
            return
        mensajes.append({"role": "user", "content": pregunta})
        self._lanzar(self._historial())

    # ------------------------------------------------- armador rápido
    def _tipo_cambio(self):
        try:
            tc = float(self.e_tc.get().replace(",", "."))
            return tc if 1 <= tc <= 100 else None
        except ValueError:
            return None

    def armar_desde_panel(self):
        if self.ocupado:
            return
        crudo = self.e_pres.get().strip().replace("$", "").replace(" ", "")
        crudo = re.sub(r"[,](?=\d{3}\b)", "", crudo)
        try:
            monto = float(crudo)
        except ValueError:
            return self._error_panel("Escribe el presupuesto solo con números, por ejemplo 25000.")
        if monto <= 0:
            return self._error_panel("El presupuesto debe ser mayor a cero.")
        if self.moneda == "MXN" and self._tipo_cambio() is None:
            return self._error_panel("Tipo de cambio inválido: usa un número como 18.5.")
        self._error_panel("")
        texto_usuario = (f"Arma una PC para {armador.USOS[self.uso].lower()} con presupuesto de "
                         f"{monto:,.0f} {self.moneda}")
        self._mensaje(texto_usuario, True)
        self._armar({"monto": monto, "moneda": self.moneda, "uso": self.uso,
                     "plataforma": self.plataforma, "marca_gpu": self.marca_gpu}, texto_usuario)

    def _error_panel(self, texto):
        self.c.itemconfigure(self.s_error, text=texto)

    def _armar(self, p, pregunta):
        tc = self._tipo_cambio() or 18.5
        usd = p["monto"] / tc if p["moneda"] == "MXN" else p["monto"]
        try:
            b = armador.armar(usd, p["uso"], p["plataforma"], p["marca_gpu"])
        except ValueError as e:
            self._nota(f"No pude armar ese build: {e}")
            return
        texto = armador.formato(b, p["moneda"], tc)
        self.ultimo_build = texto
        self._build_chat(texto)
        mensajes.append({"role": "user", "content": pregunta})
        mensajes.append({"role": "assistant", "content": texto})
        if self.explicar and self.modo != "error":
            extra = [{"role": "user", "content": "Explica este build en 4 o 5 viñetas breves: por qué cada pieza "
                                                 "clave tiene sentido para ese uso y qué cambiarías si quisiera "
                                                 "gastar un poco menos o un poco más. No repitas la lista de precios."}]
            self._lanzar(self._historial(extra))

    def copiar_build(self):
        if not self.ultimo_build:
            self._nota("Aún no hay un build para copiar. Usa el Armador rápido primero.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ultimo_build)
        self._estado(self.modo, "build copiado al portapapeles")
        self.root.after(1800, lambda: self._estado(self.modo, f"listo  ·  {self.modelo}") if not self.ocupado and self.modo == "ok" else None)

    # ------------------------------------------- resumen / exportar / limpiar
    def resumen(self):
        """3) Breve resumen del historial para el usuario."""
        preguntas = [m["content"] for m in mensajes if m["role"] == "user"]
        builds = sum(1 for m in mensajes if m["role"] == "assistant" and m["content"].startswith("BUILD SUGERIDO"))
        if not preguntas:
            self._nota("Aún no hay historial para resumir.")
            return
        self._nota(f"Preguntas realizadas: {len(preguntas)}  ·  builds generados: {builds}\n" +
                   "\n".join(f"- {p[:80]}" for p in preguntas))
        if self.modo == "error":
            return
        self._set_busy(True, "resumiendo")
        pedido = self._historial([{"role": "user", "content": "Resume en 3 o 4 viñetas breves lo que hemos "
                                                              "visto en esta conversación."}])

        def w():
            try:
                r = ollama.chat(model=self.modelo, messages=pedido, options=OPCIONES_LLM, keep_alive=KEEP_ALIVE)
                self.cola.put(("resumen", r["message"]["content"]))
            except Exception as e:
                self.cola.put(("resumen", f"No pude generar el resumen con el modelo: {e}"))
        threading.Thread(target=w, daemon=True).start()

    def exportar(self):
        if len(mensajes) < 2:
            messagebox.showinfo("Exportar", "Todavía no hay conversación para exportar.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="conversacion_pc_master.txt",
                                            filetypes=[("Texto", "*.txt")])
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                for m in mensajes[1:]:
                    f.write(("TÚ: " if m["role"] == "user" else "PC MASTER: ") + m["content"] + "\n\n")
            self._nota(f"Conversación exportada a {ruta}")

    def limpiar(self):
        if self.ocupado:
            return
        del mensajes[1:]
        self.ultimo_build = None
        self._editar(lambda: self.chat.delete("1.0", "end"))
        self._nota("Conversación reiniciada. ¿Qué PC vamos a armar?")


if __name__ == "__main__":
    ventana = tk.Tk()
    PCMaster(ventana)
    ventana.mainloop()
