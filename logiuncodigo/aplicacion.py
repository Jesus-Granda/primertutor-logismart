"""CAPA DE PRESENTACIÓN: interfaz gráfica de LogiSmart (Streamlit).

Ejecutar:  streamlit run aplicacion.py

Páginas: Panel de control · Control de acceso · Simulador lógico · Incidentes · Asistente ·
Riesgos éticos · Datos (CRUD) · Reportes · Configuración · Acerca de.
"""
import json
import os
import random
import re
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import configuracion
from capa_datos import basedatos as bd
from capa_logica import asistente, clasificador as clf, llm, notificaciones, reglas, reportes, riesgos
from capa_logica.peas import PEAS_LOGISMART
from experimento import DATASET

st.set_page_config(page_title="LogiSmart", page_icon=":material/local_shipping:", layout="wide")

ARCE, CALABAZA, MOSTAZA, OLIVO, CAFE, CIRUELA, ARENA = (
    "#b5452f", "#d9822b", "#d4a537", "#7d8a4a", "#8c5a3c", "#8e5572", "#b9a58a")
TINTA, TINTA_SUAVE, PAPEL, LINEA = "#3a2a1e", "#7a6553", "#fffaf3", "#ead9c4"
COLOR_SEMAFORO = {"verde": "#6f8f3a", "amarillo": "#e0a12e", "rojo": "#b83f2b"}
COLOR_CATEGORIA = {"materiales_peligrosos": ARCE, "somnolencia_conductor": CIRUELA, "acceso_no_autorizado": CALABAZA,
                   "sobrepeso": CAFE, "falla_hardware": OLIVO, "falla_software": MOSTAZA, "otro": ARENA}
COLOR_DECISION = {"ACCESO ESTÁNDAR": "#6f8f3a", "ACCESO CON INSPECCIÓN ESPECIAL": MOSTAZA,
                  "ENVIAR A INSPECCIÓN ESPECIAL": CALABAZA, "ACCESO DENEGADO": ARCE}
ESTADOS = ["nuevo", "en_atencion", "cerrado"]
FORMATO_PLACA = r"[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}"

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&display=swap');
  .block-container {{padding-top: 1.4rem; max-width: 1200px;}}
  h1, h2, h3 {{font-family: 'Fraunces', Georgia, serif !important; color: {TINTA}; letter-spacing: -0.01em;}}
  h1 {{font-size: 2.1rem !important;}}
  div[data-testid="stMetric"] {{background: {PAPEL}; border: 1px solid {LINEA}; border-radius: 16px;
      padding: 14px 18px; box-shadow: 0 1px 0 rgba(90,60,30,0.05);}}
  div[data-testid="stMetricValue"] {{color: {CALABAZA};}}
  div[data-testid="stElementToolbar"] {{display: none;}}
  .tarjeta {{background: {PAPEL}; border: 1px solid {LINEA}; border-radius: 16px; padding: 16px 20px; margin-bottom: 12px;}}
  .semaforo {{display:flex; align-items:center; gap:18px;}}
  .luz {{width:54px; height:54px; border-radius:50%; background: var(--c); box-shadow: 0 0 0 6px color-mix(in srgb, var(--c) 18%, transparent);}}
  .decision {{font-family: 'Fraunces', Georgia, serif; font-size: 1.35rem; margin: 0; color: {TINTA};}}
  .sub {{color: {TINTA_SUAVE}; font-size: 0.85rem;}}
  .intro {{color: {TINTA_SUAVE}; font-size: 0.95rem; margin: -0.6rem 0 1.1rem 0;}}
  section[data-testid="stSidebar"] {{border-right: 1px solid {LINEA};}}
</style>""", unsafe_allow_html=True)

def ajustes():
    return configuracion.cargar_ajustes()


def encabezado(titulo, intro):
    """Título de la página y una línea que explica para qué sirve."""
    st.title(titulo)
    st.markdown(f"<p class='intro'>{intro}</p>", unsafe_allow_html=True)


def grafica(fig, alto=340):
    fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=alto, margin=dict(l=10, r=10, t=44, b=10), font=dict(color=TINTA),
                      title_font=dict(family="Fraunces, Georgia, serif", size=16),
                      legend=dict(orientation="h", y=-0.22), separators=".,")
    fig.update_xaxes(gridcolor=LINEA, zerolinecolor=LINEA)
    fig.update_yaxes(gridcolor=LINEA, zerolinecolor=LINEA)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def tabla(df, alto=None):
    st.dataframe(df, hide_index=True, width="stretch", **({"height": alto} if alto else {}))


def fecha(d):
    return d.strftime("%d/%m/%Y %H:%M") if isinstance(d, datetime) else str(d or "")


def semaforo(color, decision, detalle=""):
    st.markdown(f"<div class='tarjeta semaforo'><div class='luz' style='--c:{COLOR_SEMAFORO[color]}'></div>"
                f"<div><p class='decision'>{decision}</p><span class='sub'>{detalle}</span></div></div>",
                unsafe_allow_html=True)


def mostrar_decision(r):
    semaforo(r["semaforo"], r["decision"], f"A (acceso estándar) = {'V' if r['A'] else 'F'}   ·   "
                                           f"E (inspección especial) = {'V' if r['E'] else 'F'}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**¿Por qué?**")
        for c in r["causas"]:
            st.markdown(f"- {c}")
    with c2:
        st.markdown("**Evaluación paso a paso**")
        st.code("\n".join(r["pasos"]), language=None)


def rango_fechas(clave, dias=35):
    hoy = date.today()
    r = st.date_input("Periodo", (hoy - timedelta(days=dias), hoy), key=clave, format="DD/MM/YYYY")
    if not isinstance(r, (tuple, list)) or len(r) != 2:
        st.info("Selecciona la fecha inicial y la fecha final.")
        st.stop()
    return datetime.combine(r[0], dtime.min), datetime.combine(r[1], dtime.max)


def pagina_panel():
    encabezado("Panel de control", "Resumen del centro logístico. Elige el periodo y usa los accesos rápidos "
                                   "para las tareas más comunes.")
    a, b, c = st.columns(3)
    a.page_link(PAG_ACCESO, label="Registrar un acceso", icon=":material/traffic:")
    b.page_link(PAG_INCIDENTES, label="Clasificar un correo", icon=":material/inbox:")
    c.page_link(PAG_ASISTENTE, label="Preguntar al asistente", icon=":material/forum:")
    st.write("")
    desde, hasta = rango_fechas("panel")
    rango = {"marca_tiempo": {"$gte": desde, "$lte": hasta}}
    cfg = ajustes()
    c1, c2, c3 = st.columns(3)
    c1.metric("Camiones atendidos", bd.contar("accesos", rango),
              help=f"De ellos, {bd.contar('accesos', {**rango, 'E': True})} pasaron a inspección especial.")
    c2.metric("Incidentes abiertos", bd.contar("incidentes", {**rango, "estado": {"$ne": "cerrado"}}))
    criticos_antes = bd.contar("riesgos_eticos", {**rango, "puntaje_inherente": {"$gte": cfg["umbral_critico"]}})
    c3.metric("Riesgos críticos", bd.contar("riesgos_eticos", {**rango, "puntaje_residual": {"$gte": cfg["umbral_critico"]}}),
              help=f"Riesgos registrados en el periodo con puntaje residual ≥ {cfg['umbral_critico']} (umbral editable "
                   f"en Configuración). Antes de mitigar eran {criticos_antes}.")
    izq, der = st.columns([3, 2])
    with izq:
        datos = bd.incidentes_por_categoria_semana(desde, hasta)
        if datos:
            df = pd.DataFrame([{"semana": f"S{d['_id']['semana']:02d}",
                                "categoría": (d["_id"].get("categoria") or "sin clasificar").replace("_", " "),
                                "incidentes": d["total"]} for d in datos])
            grafica(px.bar(df, x="semana", y="incidentes", color="categoría",
                           color_discrete_map={k.replace("_", " "): v for k, v in COLOR_CATEGORIA.items()},
                           category_orders={"semana": sorted(df["semana"].unique())},
                           title="Incidentes por categoría y semana"))
        else:
            st.info("No hay incidentes en ese periodo.")
    with der:
        dec = bd.accesos_por_decision(desde, hasta)
        if dec:
            df = pd.DataFrame([{"decisión": d["_id"].capitalize(), "total": d["total"]} for d in dec])
            grafica(px.pie(df, names="decisión", values="total", hole=0.6, title="Decisiones de acceso",
                           color="decisión", color_discrete_map={k.capitalize(): v for k, v in COLOR_DECISION.items()}))

def pagina_acceso():
    encabezado("Control de acceso", "Busca el camión por su placa, captura el peso de la báscula y el sistema decide si entra, va a inspección o se rechaza.")
    cfg = ajustes()
    t1, t2 = st.tabs(["Camión registrado", "Captura manual P / Q / R / S"])
    with t1:
        camiones = bd.listar("camiones", limite=500, orden=("camion_id", 1))
        opciones = {f"{c['placa']}  ·  {c['camion_id']}  ·  {c.get('empresa', '')}": c for c in camiones}
        if not opciones:
            st.warning("No hay camiones registrados. Agrégalos en Datos o carga la demostración en Configuración.")
        else:
            sel = st.selectbox("Placa o ID del camión", list(opciones), index=None,
                               placeholder="Escribe para buscar, por ejemplo ABC-123-D o CAM-102")
            if sel:
                _evaluar_camion(opciones[sel], cfg)
    with t2:
        st.caption("Captura las premisas a mano (útil cuando el camión no está registrado).")
        with st.form("acceso_manual"):
            a, b = st.columns(2)
            placa = a.text_input("Placa", placeholder="ABC-123-D").strip().upper()
            operador = b.text_input("Operador", placeholder="Tu nombre o usuario", key="op_manual")
            cols = st.columns(3)
            v = {k: cols[i % 3].toggle(f"{k}: {reglas.VARIABLES[k]}", value=k in "PSH")
                 for i, k in enumerate(reglas.ORDEN)}
            enviar = st.form_submit_button("Evaluar y registrar", type="primary")
        if enviar:
            if not re.fullmatch(FORMATO_PLACA, placa):
                st.error("La placa no tiene un formato válido. Ejemplo: ABC-123-D.")
            elif not operador.strip():
                st.error("Escribe el nombre del operador; se guarda en la bitácora.")
            else:
                r = reglas.evaluar(**v)
                cam = bd.buscar_uno("camiones", {"placa": placa})
                bd.insertar("accesos", reglas.documento_bitacora(r, cam["camion_id"] if cam else None, placa,
                                                                 operador.strip()))
                st.toast("Decisión guardada en la bitácora de accesos.")
                mostrar_decision(r)


def _evaluar_camion(cam, cfg):
    ahora = datetime.now()
    P = bool(cam.get("autorizacion", {}).get("autorizado"))
    vence = cam.get("certificacion_conductor", {}).get("vigente_hasta")
    S = bool(vence and vence >= ahora)
    h0, h1 = cfg["horario_peligrosos"]
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**P · autorización previa:** {'sí' if P else 'no'}")
    c2.markdown(f"**S · certificación:** {'vigente' if S else 'vencida o sin registro'}"
                + (f" (hasta {vence:%d/%m/%Y})" if vence else ""))
    c3.markdown(f"**Tipo de carga:** {cam.get('tipo_carga', 'general')}")
    with st.form(f"acceso_{cam['_id']}"):
        a, b, c = st.columns(3)
        peso = a.number_input("Peso en báscula (kg)", min_value=0, max_value=120000, step=100, value=30000)
        R = b.toggle("R: materiales peligrosos", value=cam.get("tipo_carga") == "peligrosa")
        F = c.toggle("F: fatiga detectada por la cámara")
        operador = st.text_input("Operador", placeholder="Tu nombre o usuario")
        enviar = st.form_submit_button("Evaluar y registrar", type="primary")
    if enviar:
        if not operador.strip():
            st.error("Escribe el nombre del operador; se guarda en la bitácora.")
        elif peso <= 0:
            st.error("El peso debe ser mayor a cero.")
        else:
            Q = peso > cfg["peso_max_kg"]
            H = h0 <= ahora.hour < h1
            r = reglas.evaluar(P, Q, R, S, H, F)
            bd.insertar("accesos", reglas.documento_bitacora(r, cam["camion_id"], cam["placa"], operador.strip(),
                                                             peso, cfg["peso_max_kg"]))
            st.toast("Decisión guardada en la bitácora de accesos.")
            st.caption(f"Q se calculó con la báscula: {peso:,} kg contra un límite de {cfg['peso_max_kg']:,} kg.  "
                       f"H se calculó con la hora actual ({ahora:%H:%M}) y el horario {h0}:00 a {h1}:00.")
            mostrar_decision(r)
    hist = bd.listar("accesos", {"placa": cam["placa"]}, limite=10)
    if hist:
        st.markdown("**Historial de esta placa**")
        tabla(pd.DataFrame([{"fecha y hora": fecha(h["marca_tiempo"]), "peso (kg)": h.get("peso_kg"),
                             "decisión": h["decision"], "operador": h.get("operador")} for h in hist]))

def pagina_simulador():
    encabezado("Simulador lógico", "Enciende o apaga cada premisa y mira cómo cambian A (acceso) y E (inspección) en vivo.")
    cols = st.columns(6)
    v = {k: cols[i].toggle(k, value=k in "PSH", help=reglas.VARIABLES[k], key=f"sim_{k}")
         for i, k in enumerate(reglas.ORDEN)}
    st.caption("  ·  ".join(f"{k}: {reglas.VARIABLES[k]}" for k in reglas.ORDEN))
    mostrar_decision(reglas.evaluar(**v))
    st.subheader("Tabla de verdad de cada regla")
    cols = st.columns(2)
    for i, (nombre, filas) in enumerate(reglas.tablas_verdad().items()):
        with cols[i % 2]:
            st.markdown(f"**{nombre}**")
            tabla(pd.DataFrame(filas))
    with st.expander("Tabla completa: 64 combinaciones de P, Q, R, S, H y F"):
        df = pd.DataFrame(reglas.tabla_completa())
        filtro = st.radio("Mostrar", ["todas", "solo A = V", "solo E = V"], horizontal=True)
        if filtro != "todas":
            df = df[df[filtro[5]] == "V"]
        tabla(df, 320)
    with st.expander("Contradicciones y reglas redundantes (reto opcional)"):
        a = reglas.analizar()
        c1, c2 = st.columns(2)
        c1.metric("Contradicciones encontradas", len(a["contradicciones"]))
        c2.metric("Reglas redundantes", len(a["redundantes"]))
        st.markdown("**Combinaciones en las que cada regla cambia el resultado** (si las dos son 0, la regla sobra)")
        efecto = pd.DataFrame(a["efecto_por_regla"]).T.reset_index()
        efecto.columns = ["regla", "cambia A", "cambia E"]
        tabla(efecto)
        for o in a["observaciones"]:
            st.markdown(f"- {o}")

def pagina_incidentes():
    encabezado("Incidentes", "Pega un correo de incidente: las reglas y el LLM lo clasifican, tú lo revisas y le das seguimiento.")
    cfg = ajustes()
    abiertos = bd.contar("incidentes", {"estado": {"$ne": "cerrado"}})
    t1, t2 = st.tabs(["Nuevo correo", f"Bandeja ({abiertos} abiertos)"])
    with t1:
        if cfg["simulacion_correo"] and st.button("Usar un correo de ejemplo", icon=":material/mail:"):
            a, c, *_ = random.choice(DATASET)
            st.session_state.inc_asunto, st.session_state.inc_cuerpo = a, c
        asunto = st.text_input("Asunto del correo", key="inc_asunto")
        cuerpo = st.text_area("Cuerpo del correo", key="inc_cuerpo", height=120,
                              placeholder="Pega aquí el texto del correo")
        if st.button("Clasificar", type="primary", icon=":material/auto_awesome:"):
            if len((asunto + cuerpo).strip()) < 10:
                st.error("El correo está vacío o es muy corto: pega el asunto y el cuerpo completos.")
            else:
                with st.spinner("Clasificando con reglas y con el LLM..."):
                    st.session_state.clas = clf.hibrido(asunto, cuerpo, cfg["modelo"], cfg["reintentos"])
                    st.session_state.clas_correo = (asunto, cuerpo)
                    st.session_state.n_clas = st.session_state.get("n_clas", 0) + 1
        c = st.session_state.get("clas")
        if c:
            _resultado_clasificacion(c, cfg)
    with t2:
        _lista_incidentes()


def _resultado_clasificacion(c, cfg):
    if c["error_llm"]:
        if c["intentos_llm"]:
            st.warning(f"El LLM no devolvió un JSON válido en {c['intentos_llm']} intentos; se usó el clasificador "
                       "por reglas (plan de respaldo).")
        else:
            st.warning(f"{c['error_llm']} Mientras tanto se usó el clasificador por reglas (plan de respaldo).")
    if c["requiere_revision_humana"]:
        st.warning(f"Requiere revisión humana. {c['motivo_fusion']}")
    for aviso in c["avisos"]:
        st.info(aviso)
    st.caption(f"Método: {c['metodo']}  ·  latencia del LLM: {c['latencia_llm_s']} s  ·  intentos: {c['intentos_llm']}")
    tabla(pd.DataFrame([
        {"fuente": "Reglas", "categoría": c["reglas"]["categoria"], "prioridad": c["reglas"]["prioridad"]},
        {"fuente": "LLM", "categoría": c["llm"]["categoria"] if c["llm"] else "(JSON inválido)",
         "prioridad": c["llm"]["prioridad"] if c["llm"] else "-"},
        {"fuente": "Resultado final", "categoría": c["categoria"], "prioridad": c["prioridad"]}]))
    with st.form(f"guardar_{st.session_state.n_clas}"):
        st.markdown("**Revisa y edita el resultado antes de guardarlo**")
        a, b = st.columns(2)
        cat = a.selectbox("Categoría", clf.LISTA_CATEGORIAS, index=clf.LISTA_CATEGORIAS.index(c["categoria"]))
        pri = b.selectbox("Prioridad", clf.ORDEN_PRIORIDAD, index=clf.ORDEN_PRIORIDAD.index(c["prioridad"]))
        res = st.text_input("Resumen", value=c["resumen"])
        e = c["entidades"]
        a, b, d, f = st.columns(4)
        placa = a.text_input("Placa", value=e["placa"] or "")
        cid = b.text_input("ID del camión", value=e["camion_id"] or "")
        peso = d.text_input("Peso reportado (kg)", value="" if e["peso_reportado_kg"] is None else str(e["peso_reportado_kg"]))
        ubic = f.text_input("Ubicación", value=e["ubicacion"] or "")
        guardar = st.form_submit_button("Guardar incidente", type="primary")
    if guardar:
        try:
            entidades = clf.Entidades(placa=placa or None, camion_id=cid or None,
                                      peso_reportado_kg=peso or None, ubicacion=ubic or None)
            final = clf.Clasificacion(categoria=cat, prioridad=pri, resumen=res, entidades=entidades)
        except Exception:
            st.error("Revisa los datos: el peso debe ser un número (por ejemplo 48500) y el resumen no puede ir vacío.")
            return
        editado = cat != c["categoria"] or pri != c["prioridad"]
        asunto, cuerpo = st.session_state.clas_correo
        historial = [{"fecha": datetime.now(), "usuario": "operador",
                      "evento": f"alta ({c['metodo']})" + (" con edición manual" if editado else "")}]
        if pri in ("alta", "critica"):
            envio = notificaciones.enviar_correo_soporte(f"[{pri.upper()}] {cat} - {asunto}", cuerpo,
                                                         simulacion=cfg["simulacion_correo"])
            historial.append({"fecha": datetime.now(), "usuario": "sistema",
                              "evento": f"aviso a soporte ({envio['modo']}): "
                                        + ("enviado" if envio["enviado"] else f"falló: {envio['error']}")})
        bd.insertar("incidentes", clf.documento_incidente(asunto, cuerpo, final, c["metodo"],
                                                          c["requiere_revision_humana"] or editado,
                                                          c["palabras_clave"], "nuevo", historial))
        st.session_state.clas = None
        st.toast("Incidente guardado.")
        st.rerun()


def _lista_incidentes():
    f1, f2 = st.columns(2)
    est = f1.multiselect("Estado", ESTADOS, default=["nuevo", "en_atencion"], placeholder="Todos")
    cats = f2.multiselect("Categoría", clf.LISTA_CATEGORIAS, placeholder="Todas")
    filtro = {"estado": {"$in": est or ESTADOS}}
    if cats:
        filtro["clasificacion.categoria"] = {"$in": cats}
    incidentes = bd.listar("incidentes", filtro, limite=60)
    if not incidentes:
        st.info("No hay incidentes con esos filtros.")
    for i in incidentes:
        cl, correo, k = i.get("clasificacion", {}), i.get("correo_original", {}), str(i["_id"])
        marca = "  ·  revisión humana" if cl.get("requiere_revision_humana") else ""
        with st.expander(f"[{i['estado']}]  {cl.get('prioridad', '?').upper()}  ·  {cl.get('categoria', '?')}  ·  "
                         f"{correo.get('asunto', '')[:60]}{marca}"):
            st.markdown(f"**Correo original:** {correo.get('cuerpo', '')}")
            st.markdown(f"**Resumen:** {cl.get('resumen', '')}")
            datos = {k2: v for k2, v in i.get("datos_extraidos", {}).items() if v is not None}
            st.markdown("**Datos extraídos:** " + (", ".join(f"{k2} = {v}" for k2, v in datos.items()) or "ninguno"))
            a, b, d = st.columns(3)
            nuevo = a.selectbox("Estado", ESTADOS, index=ESTADOS.index(i["estado"]), key=f"e{k}")
            ncat = b.selectbox("Categoría", clf.LISTA_CATEGORIAS,
                               index=clf.LISTA_CATEGORIAS.index(cl.get("categoria", "otro")), key=f"c{k}")
            npri = d.selectbox("Prioridad", clf.ORDEN_PRIORIDAD,
                               index=clf.ORDEN_PRIORIDAD.index(cl.get("prioridad", "baja")), key=f"p{k}")
            x, y, _ = st.columns([1, 1, 3])
            if x.button("Guardar cambios", key=f"g{k}"):
                cambios = [f"{n}: {v0} → {v1}" for n, v0, v1 in (
                    ("estado", i["estado"], nuevo), ("categoría", cl.get("categoria"), ncat),
                    ("prioridad", cl.get("prioridad"), npri)) if v0 != v1]
                if cambios:
                    bd.actualizar("incidentes", k, {"estado": nuevo, "clasificacion.categoria": ncat,
                                                    "clasificacion.prioridad": npri})
                    bd.agregar_historial("incidentes", k, "; ".join(cambios))
                    st.rerun()
                else:
                    st.info("No hay cambios que guardar.")
            if y.button("Eliminar", key=f"d{k}"):
                bd.eliminar("incidentes", k)
                st.rerun()
            st.markdown("**Historial**")
            for h in i.get("historial", []):
                st.markdown(f"- {fecha(h['fecha'])} · {h.get('usuario', '')}: {h['evento']}")


def pagina_asistente():
    encabezado("Asistente", "Pregunta sobre camiones, accesos, incidentes o riesgos. Responde solo con datos guardados y te dice de dónde los sacó.")
    if not st.session_state.get("chat"):
        st.markdown("**Prueba con:** «¿Por qué CAM-102 fue enviado a inspección?» · «¿Qué incidentes siguen abiertos?»")
    hist = st.session_state.setdefault("chat", [])
    if hist and st.button("Borrar conversación", icon=":material/delete:"):
        st.session_state.chat = []
        st.rerun()
    for h in hist:
        with st.chat_message(h["rol"]):
            st.markdown(h["texto"])
            if h.get("fuentes"):
                st.caption("Fuentes consultadas: " + ", ".join(h["fuentes"]))
    pregunta = st.chat_input("Pregunta sobre un camión, un acceso, un incidente o un riesgo")
    if pregunta:
        hist.append({"rol": "user", "texto": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.chat_message("assistant"):
            with st.spinner("Consultando MongoDB y redactando la respuesta..."):
                texto, fuentes, lat = asistente.responder(pregunta, hist[:-1], ajustes()["modelo"])
            st.markdown(texto)
            if fuentes:
                st.caption(f"Fuentes consultadas: {', '.join(fuentes)}" + (f"  ·  {lat:.1f} s" if lat else ""))
        hist.append({"rol": "assistant", "texto": texto, "fuentes": fuentes})


def pagina_riesgos():
    encabezado("Riesgos éticos", "Riesgos del sistema antes y después de mitigarlos (probabilidad × impacto, de 1 a 25).")
    cfg = ajustes()
    docs = bd.listar("riesgos_eticos", limite=300)
    tg, t1, t2, t3 = st.tabs(["Gráficas", "Agregar", "Editar", "Eliminar"])
    with tg:
        _graficas_riesgos(docs, cfg)
    with t1:
        _form_riesgo("alta_riesgo", None)
    if not docs:
        return
    nombres = {f"{d['modulo']}: {d['descripcion'][:55]}": d for d in docs}
    with t2:
        d = nombres[st.selectbox("Riesgo a editar", list(nombres))]
        _form_riesgo(f"ed_{d['_id']}", d)
        st.markdown("**Histórico de cambios**")
        tabla(pd.DataFrame([{"fecha": fecha(h["fecha"]), "evento": h["evento"], "inherente": h["inherente"],
                             "residual": h["residual"]} for h in d.get("historico", [])]))
    with t3:
        k = st.selectbox("Riesgo a eliminar", list(nombres), key="baja_riesgo")
        ok = st.checkbox("Confirmo que quiero eliminar este riesgo")
        if st.button("Eliminar riesgo", disabled=not ok):
            bd.eliminar("riesgos_eticos", nombres[k]["_id"])
            st.toast("Riesgo eliminado.")
            st.rerun()


def _graficas_riesgos(docs, cfg):
    if docs:
        df = pd.DataFrame(bd.limpiar(docs))
        df["riesgo"] = df["modulo"] + " — " + df["descripcion"].str.slice(0, 38)
        df = df.sort_values("puntaje_inherente")
        fig = go.Figure()
        fig.add_bar(y=df["riesgo"], x=df["puntaje_inherente"], name="Antes de mitigar", orientation="h", marker_color=ARCE)
        fig.add_bar(y=df["riesgo"], x=df["puntaje_residual"], name="Después de mitigar (residual)", orientation="h",
                    marker_color=OLIVO)
        fig.add_vline(x=cfg["umbral_critico"], line_dash="dot", line_color=CAFE,
                      annotation_text="umbral crítico", annotation_font_color=CAFE)
        fig.update_layout(barmode="group", title="Riesgo antes y después de la mitigación (probabilidad × impacto)")
        grafica(fig, 120 + 38 * len(df))
        izq, der = st.columns([2, 3])
        with izq:
            mapa = [[0] * 5 for _ in range(5)]
            for _, r in df.iterrows():
                mapa[5 - r["impacto"]][r["probabilidad"] - 1] += 1
            fig = go.Figure(go.Heatmap(z=[[(5 - i) * (j + 1) for j in range(5)] for i in range(5)],
                                       x=[1, 2, 3, 4, 5], y=[5, 4, 3, 2, 1],
                                       text=[[str(v) if v else "" for v in fila] for fila in mapa],
                                       texttemplate="%{text}", hoverinfo="skip", showscale=False,
                                       colorscale=[[0, "#eef0dc"], [0.5, "#f2d18b"], [1, "#d98a6a"]]))
            fig.update_layout(title="Mapa de calor: riesgos por celda", xaxis_title="Probabilidad",
                              yaxis_title="Impacto")
            grafica(fig, 330)
        with der:
            vista = df[["modulo", "categoria", "puntaje_inherente", "nivel_inherente", "puntaje_residual",
                        "nivel_residual", "reduccion_pct"]].sort_values("puntaje_residual", ascending=False)
            vista.columns = ["módulo", "categoría", "inherente", "nivel", "residual", "nivel residual", "% reducción"]
            tabla(vista, 330)
    else:
        st.info("No hay riesgos registrados. Agrégalos en la pestaña Agregar o carga la demostración en Configuración.")


def _form_riesgo(clave, d):
    d = d or {}
    with st.form(clave):
        a, b = st.columns([2, 1])
        mod = a.text_input("Módulo", d.get("modulo", ""))
        cat = b.selectbox("Categoría", riesgos.CATEGORIAS,
                          index=riesgos.CATEGORIAS.index(d["categoria"]) if d.get("categoria") in riesgos.CATEGORIAS else 0)
        desc = st.text_area("Descripción", d.get("descripcion", ""), height=70)
        a, b, c, e = st.columns(4)
        p = a.slider("Probabilidad", 1, 5, d.get("probabilidad", 3))
        i = b.slider("Impacto", 1, 5, d.get("impacto", 3))
        pr = c.slider("Probabilidad residual", 1, 5, d.get("probabilidad_residual", 2))
        ir = e.slider("Impacto residual", 1, 5, d.get("impacto_residual", 2))
        mit = st.text_area("Mitigación", d.get("mitigacion", ""), height=70)
        if st.form_submit_button("Guardar riesgo", type="primary"):
            try:
                if not mit.strip():
                    raise ValueError("Describe la mitigación: sin ella no se puede calcular el riesgo residual.")
                if d:
                    riesgos.editar(d["_id"], modulo=mod, categoria=cat, descripcion=desc, probabilidad=p,
                                   impacto=i, probabilidad_residual=pr, impacto_residual=ir, mitigacion=mit)
                else:
                    bd.insertar("riesgos_eticos", riesgos.documento(mod, desc, cat, p, i, mit, pr, ir))
                st.toast(f"Riesgo guardado: inherente {p * i} ({riesgos.nivel(p * i)}) → "
                         f"residual {pr * ir} ({riesgos.nivel(pr * ir)}).")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def pagina_datos():
    encabezado("Datos", "Consulta, agrega, edita o elimina registros de cualquier colección de MongoDB.")
    col = st.selectbox("Colección", bd.COLECCIONES)
    docs = bd.listar(col, limite=300)
    st.caption(f"{bd.contar(col)} documentos en total (se muestran los 300 más recientes).")
    if docs:
        tabla(reportes.a_df(docs).drop(columns=["historial", "historico", "prompt", "explicacion.pasos"],
                                       errors="ignore"), 300)
    if col == "camiones":
        _crud_camiones(docs)
        return
    ta, te, tb = st.tabs(["Agregar", "Editar", "Eliminar"])
    with ta:
        st.caption("Para registros nuevos usa de preferencia las otras páginas (Control de acceso, Incidentes, "
                   "Riesgos). Aquí puedes capturar el documento completo en formato JSON.")
        txt = st.text_area("Documento (JSON)", "{\n  \n}", height=160, key=f"nuevo_{col}")
        if st.button("Agregar documento"):
            try:
                bd.insertar(col, json.loads(txt))
                st.toast("Documento agregado.")
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"El JSON tiene un error en la línea {e.lineno}: {e.msg}")
    if docs:
        etiquetas = {f"{str(d['_id'])[-6:]} · {_etiqueta(d)}": d for d in docs}
        with te:
            d = etiquetas[st.selectbox("Documento", list(etiquetas), key="ed_doc")]
            txt = st.text_area("Edita el documento (JSON)",
                               json.dumps(bd.limpiar({k: v for k, v in d.items() if k != "_id"}),
                                          ensure_ascii=False, indent=2), height=300, key=f"ed_{d['_id']}")
            if st.button("Guardar cambios"):
                try:
                    bd.reemplazar(col, d["_id"], json.loads(txt))
                    st.toast("Documento actualizado.")
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"El JSON tiene un error en la línea {e.lineno}: {e.msg}")
        with tb:
            k = st.selectbox("Documento a eliminar", list(etiquetas), key="del_doc")
            ok = st.checkbox("Confirmo la eliminación", key="del_ok")
            if st.button("Eliminar documento", disabled=not ok):
                bd.eliminar(col, etiquetas[k]["_id"])
                st.toast("Documento eliminado.")
                st.rerun()


def _etiqueta(d):
    return str(d.get("placa") or d.get("correo_original", {}).get("asunto") or d.get("modulo")
               or d.get("origen") or "")[:60]


def _crud_camiones(docs):
    ta, te, tb = st.tabs(["Agregar camión", "Editar camión", "Eliminar camión"])
    with ta:
        _form_camion("nuevo_camion", {})
    if docs:
        opciones = {f"{d['camion_id']} · {d['placa']}": d for d in docs}
        with te:
            d = opciones[st.selectbox("Camión", list(opciones))]
            _form_camion(f"cam_{d['_id']}", d)
        with tb:
            k = st.selectbox("Camión a eliminar", list(opciones), key="del_cam")
            ok = st.checkbox("Confirmo la eliminación", key="del_cam_ok")
            if st.button("Eliminar camión", disabled=not ok):
                bd.eliminar("camiones", opciones[k]["_id"])
                st.toast("Camión eliminado.")
                st.rerun()


def _camion_repetido(placa, cid, propio_id=None):
    otro = bd.buscar_uno("camiones", {"$or": [{"placa": placa}, {"camion_id": cid}]})
    return bool(otro) and otro["_id"] != propio_id


def _form_camion(clave, d):
    cert = d.get("certificacion_conductor", {})
    with st.form(clave):
        a, b, c = st.columns(3)
        cid = a.text_input("ID del camión", d.get("camion_id", ""), placeholder="CAM-120").strip().upper()
        placa = b.text_input("Placa", d.get("placa", ""), placeholder="ABC-123-D").strip().upper()
        emp = c.text_input("Empresa", d.get("empresa", ""))
        a, b, c, e = st.columns(4)
        aut = a.toggle("Autorización previa (P)", d.get("autorizacion", {}).get("autorizado", True))
        carga = b.selectbox("Tipo de carga", ["general", "peligrosa"], index=1 if d.get("tipo_carga") == "peligrosa" else 0)
        folio = c.text_input("Folio de certificación", cert.get("folio") or "")
        vence = e.date_input("Certificación vigente hasta",
                             (cert.get("vigente_hasta") or datetime.now() + timedelta(days=365)).date(),
                             format="DD/MM/YYYY")
        if st.form_submit_button("Guardar camión", type="primary"):
            if not re.fullmatch(r"CAM-\d+", cid):
                st.error("El ID debe tener el formato CAM-### (por ejemplo CAM-120).")
            elif not re.fullmatch(FORMATO_PLACA, placa):
                st.error("La placa debe tener el formato ABC-123-D.")
            elif not emp.strip():
                st.error("Escribe el nombre de la empresa.")
            elif _camion_repetido(placa, cid, d.get("_id")):
                st.error(f"Ya existe otro camión con la placa {placa} o el ID {cid}. Usa valores distintos.")
            else:
                doc = {"camion_id": cid, "placa": placa, "empresa": emp.strip(), "tipo_carga": carga,
                       "autorizacion": {"autorizado": aut, "folio": f"AUT-{cid[4:]}" if aut else None},
                       "certificacion_conductor": {"folio": folio.strip() or None,
                                                   "vigente_hasta": datetime.combine(vence, dtime.max)}}
                try:
                    if d:
                        bd.actualizar("camiones", d["_id"], doc)
                    else:
                        bd.insertar("camiones", doc)
                except bd.ErrorBD as e:
                    st.error(str(e))
                    return
                st.toast("Camión guardado.")
                st.rerun()


COLUMNAS_PDF = {
    "camiones": ["camion_id", "placa", "empresa", "tipo_carga", "autorizacion.autorizado",
                 "certificacion_conductor.vigente_hasta"],
    "accesos": ["marca_tiempo", "camion_id", "placa", "P", "Q", "R", "S", "A", "E", "decision", "operador"],
    "incidentes": ["marca_tiempo", "correo_original.asunto", "clasificacion.categoria", "clasificacion.prioridad",
                   "estado", "clasificacion.requiere_revision_humana"],
    "riesgos_eticos": ["modulo", "descripcion", "categoria", "puntaje_inherente", "puntaje_residual",
                       "nivel_residual", "mitigacion"],
    "evaluaciones_llm": ["marca_tiempo", "origen", "modelo", "latencia_s", "json_valido", "coincidio_reglas"],
}


def pagina_reportes():
    encabezado("Reportes", "Descarga cualquier colección en PDF, CSV o JSON y revisa los resultados del experimento.")
    t1, t2 = st.tabs(["Exportar datos", "Resultados del experimento"])
    with t1:
        _exportar()
    with t2:
        _experimento()


def _exportar():
    col = st.selectbox("¿Qué quieres exportar?", bd.COLECCIONES, format_func=lambda c: c.replace("_", " ").capitalize())
    docs = bd.listar(col, limite=5000)
    if not docs:
        st.info("No hay datos para exportar en esa colección.")
    else:
        df = reportes.a_df(docs)
        tabla(df[[c for c in COLUMNAS_PDF[col] if c in df.columns]].head(50))
        resumen = None
        if col == "riesgos_eticos":
            resumen = [f"Riesgos: {len(df)} · puntaje inherente promedio {df.puntaje_inherente.mean():.1f} · "
                       f"puntaje residual promedio {df.puntaje_residual.mean():.1f}"]
        a, b, c = st.columns(3)
        a.download_button("Descargar CSV", reportes.a_csv(df), f"{col}.csv", "text/csv", icon=":material/table:")
        b.download_button("Descargar JSON", reportes.a_json(docs), f"{col}.json", "application/json",
                          icon=":material/data_object:")
        c.download_button("Descargar PDF", reportes.a_pdf(f"Reporte de {col.replace('_', ' ')}", df,
                                                          COLUMNAS_PDF[col], resumen),
                          f"{col}.pdf", "application/pdf", icon=":material/picture_as_pdf:")


def _experimento():
    st.caption(f"Clasifica los {len(DATASET)} correos etiquetados a mano con reglas, con el LLM y con el híbrido, "
               "y compara exactitud, matriz de confusión y latencia. Tarda unos minutos.")
    if st.button("Ejecutar experimento", icon=":material/science:"):
        import experimento
        barra = st.progress(0.0, text="Preparando...")
        try:
            experimento.correr(ajustes()["modelo"], progreso=lambda _t: None,
                               avance=lambda i, n: barra.progress(i / n, text=f"Clasificando correo {i} de {n}..."))
            barra.progress(1.0, text="Listo.")
            st.toast("Experimento terminado.")
        except llm.ErrorLLM as e:
            barra.empty()
            st.error(str(e))
    if not os.path.exists("resultados_experimento.json"):
        st.info("Aún no hay resultados. Presiona «Ejecutar experimento» (requiere Ollama abierto).")
        return
    with open("resultados_experimento.json", encoding="utf-8") as f:
        r = json.load(f)
    st.caption(f"Modelo {r['modelo']} · {r['n_correos']} correos ({r['n_informales']} con ortografía informal) · "
               f"JSON válido {r['json_valido_pct']}% · revisión humana {r['revision_humana_pct']}% · {r['fecha'][:16]}")
    t = pd.DataFrame([{"método": k, "exactitud categoría": v["exactitud_categoria"],
                       "exactitud prioridad": v["exactitud_prioridad"],
                       "correos formales": v["exactitud_cat_formales"],
                       "correos informales": v["exactitud_cat_informales"],
                       "latencia media (s)": v["latencia_media_s"]} for k, v in r["metodos"].items()])
    st.dataframe(t.style.format({c: "{:.0%}" for c in t.columns[1:5]} | {"latencia media (s)": "{:.2f}"}),
                 hide_index=True, width="stretch")
    metodo = st.radio("Matriz de confusión de", list(r["metodos"]), horizontal=True)
    m = pd.DataFrame(r["metodos"][metodo]["matriz_confusion"]).T
    m = m.loc[:, (m != 0).any(axis=0) | m.columns.isin(m.index)]
    grafica(px.imshow(m, text_auto=True, color_continuous_scale=["#fbf5ec", CALABAZA], aspect="auto",
                      labels=dict(x="categoría predicha", y="categoría real", color="correos")), 440)

def pagina_config():
    encabezado("Configuración", "Modelo de Ollama, umbrales y modo de simulación. Los cambios se guardan al presionar Guardar.")
    cfg = ajustes()
    modelos = llm.modelos_disponibles()
    if not modelos:
        st.warning("No pude obtener la lista de modelos de Ollama. ¿Está abierto?")
    opciones = sorted(set(modelos + [cfg["modelo"]]))
    with st.form("ajustes"):
        a, b = st.columns(2)
        modelo = a.selectbox("Modelo de Ollama", opciones, index=opciones.index(cfg["modelo"]))
        reint = b.slider("Reintentos si el LLM devuelve un JSON inválido", 0, 5, cfg["reintentos"])
        a, b = st.columns(2)
        umbral = a.slider("Umbral de riesgo crítico (puntaje residual)", 5, 25, cfg["umbral_critico"])
        peso = b.number_input("Peso máximo en báscula (kg) para calcular Q", 10000, 100000, cfg["peso_max_kg"], 500)
        h = st.slider("Horario permitido para materiales peligrosos (H), en horas", 0, 24,
                      tuple(cfg["horario_peligrosos"]))
        sim = st.toggle("Modo simulación de correo (correos de ejemplo y avisos a soporte sin enviar)",
                        cfg["simulacion_correo"])
        if st.form_submit_button("Guardar configuración", type="primary"):
            if h[0] >= h[1]:
                st.error("La hora de inicio debe ser menor que la hora de fin.")
            else:
                configuracion.guardar_ajustes({**cfg, "modelo": modelo, "reintentos": reint, "umbral_critico": umbral,
                                               "peso_max_kg": int(peso), "horario_peligrosos": list(h),
                                               "simulacion_correo": sim})
                st.toast("Configuración guardada.")
    st.divider()
    a, b, c = st.columns(3)
    if a.button("Probar conexión a MongoDB", icon=":material/database:"):
        try:
            bd.get_db()
            st.success(f"Conectado a {bd.modo()}.")
        except bd.ErrorBD as e:
            st.error(str(e))
    if b.button("Probar Ollama", icon=":material/smart_toy:"):
        with st.spinner("Esperando respuesta del modelo..."):
            try:
                texto, lat = llm.chat([{"role": "user", "content": "Responde solo: listo"}], cfg["modelo"])
                st.success(f"Ollama respondió en {lat:.1f} s: {texto[:40]}")
            except llm.ErrorLLM as e:
                st.error(str(e))
    if c.button("Cargar datos de demostración", icon=":material/upload:"):
        import datos_demo
        with st.spinner("Cargando datos..."):
            datos_demo.cargar()
        st.success("Listo. Solo se llenaron las colecciones que estaban vacías.")
    with st.expander("Reiniciar datos"):
        ok = st.checkbox("Entiendo que esto BORRA las 5 colecciones")
        if st.button("Borrar todo y recargar la demostración", disabled=not ok, type="primary"):
            import datos_demo
            datos_demo.cargar(reset=True)
            st.success("Colecciones reiniciadas con los datos de demostración.")


def pagina_acerca():
    encabezado("Acerca de", "Cómo está construido LogiSmart.")
    st.markdown("Agente de control inteligente de acceso y seguridad logística. Arquitectura por capas:")
    st.code("presentación   aplicacion.py (Streamlit)\n"
            "lógica         capa_logica/  reglas · clasificador · llm · asistente · riesgos · reportes · notificaciones\n"
            "datos          capa_datos/basedatos.py → MongoDB (camiones, accesos, incidentes, riesgos_eticos, "
            "evaluaciones_llm)\n"
            "modelo         Ollama local (JSON validado con pydantic y respaldo por reglas)", language=None)
    st.subheader("Diseño PEAS del agente")
    p = PEAS_LOGISMART
    a, b = st.columns(2)
    with a:
        st.markdown("**P · Medidas de desempeño**\n" + "\n".join(f"- {x}" for x in p["P_desempeno"]))
        st.markdown("**A · Actuadores**\n" + "\n".join(f"- {x}" for x in p["A_actuadores"]))
    with b:
        st.markdown(f"**E · Entorno:** {p['E_entorno']['descripcion']}\n"
                    + "\n".join(f"- {k}: {v}" for k, v in p["E_entorno"]["propiedades"].items()))
        st.markdown("**S · Sensores**\n" + "\n".join(f"- {x}" for x in p["S_sensores"]))


PAG_PANEL = st.Page(pagina_panel, title="Panel de control", icon=":material/home:", default=True)
PAG_ACCESO = st.Page(pagina_acceso, title="Control de acceso", icon=":material/traffic:", url_path="acceso")
PAG_INCIDENTES = st.Page(pagina_incidentes, title="Incidentes", icon=":material/inbox:", url_path="incidentes")
PAG_ASISTENTE = st.Page(pagina_asistente, title="Asistente", icon=":material/forum:", url_path="asistente")
PAGINAS = {
    "Operación": [PAG_PANEL, PAG_ACCESO, PAG_INCIDENTES, PAG_ASISTENTE],
    "Análisis": [
        st.Page(pagina_simulador, title="Simulador lógico", icon=":material/toggle_on:", url_path="simulador"),
        st.Page(pagina_riesgos, title="Riesgos éticos", icon=":material/balance:", url_path="riesgos"),
        st.Page(pagina_reportes, title="Reportes", icon=":material/description:", url_path="reportes"),
    ],
    "Administración": [
        st.Page(pagina_datos, title="Datos", icon=":material/database:", url_path="datos"),
        st.Page(pagina_config, title="Configuración", icon=":material/settings:", url_path="configuracion"),
        st.Page(pagina_acerca, title="Acerca de", icon=":material/info:", url_path="acerca"),
    ],
}

pagina = st.navigation(PAGINAS)
with st.sidebar:
    st.divider()
    st.markdown("<h3 style='margin:0'>LogiSmart</h3>", unsafe_allow_html=True)
    st.caption(f"Centro de control inteligente  \nBase de datos: {bd.modo()} · {configuracion.MONGO_DB}")
try:
    pagina.run()
except bd.ErrorBD as e:
    st.error(str(e), icon=":material/cloud_off:")
    st.info("Revisa el archivo .env y tu conexión a internet. Para probar sin servidor usa MONGO_URI=memoria.")
    if e.detalle:
        with st.expander("Detalle técnico"):
            st.code(e.detalle[:1500], language=None)
except llm.ErrorLLM as e:
    st.error(str(e), icon=":material/smart_toy:")
    if e.detalle:
        with st.expander("Detalle técnico"):
            st.code(e.detalle[:1500], language=None)
