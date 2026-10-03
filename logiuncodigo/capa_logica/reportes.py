"""Exportación de reportes a CSV, JSON y PDF."""
import io
import json
from datetime import datetime

import pandas as pd

from capa_datos import basedatos as bd


def a_df(docs):
    df = pd.json_normalize(bd.limpiar(list(docs)), max_level=1)  # {"a": {"b": 1}} -> columna "a.b"
    for c in df.columns:
        if df[c].map(lambda x: isinstance(x, (list, dict))).any():
            df[c] = df[c].map(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x)
    return df


def a_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")  # utf-8-sig: Excel respeta los acentos


def a_json(docs):
    return json.dumps(bd.limpiar(list(docs)), ensure_ascii=False, indent=2).encode("utf-8")


def a_pdf(titulo, df, columnas=None, resumen=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=titulo, leftMargin=28, rightMargin=28)
    est = getSampleStyleSheet()
    celda = est["BodyText"].clone("celda", fontSize=7, leading=8.5)
    elems = [Paragraph(titulo, est["Title"]),
             Paragraph(f"LogiSmart · generado el {datetime.now():%Y-%m-%d %H:%M}", est["Normal"]), Spacer(1, 10)]
    for linea in resumen or []:
        elems.append(Paragraph(linea, est["Normal"]))
    if resumen:
        elems.append(Spacer(1, 8))
    if df.empty:
        elems.append(Paragraph("Sin datos.", est["Normal"]))
    else:
        d = df.drop(columns=[c for c in ("_id", "historial", "historico", "prompt") if c in df.columns])
        if columnas:
            d = d[[c for c in columnas if c in d.columns]]
        d = d.iloc[:, :12]
        filas = [[Paragraph(f"<b>{c}</b>", celda) for c in d.columns]]
        filas += [[Paragraph(str(x)[:160].replace("<", "&lt;"), celda) for x in r] for r in d.values.tolist()]
        t = Table(filas, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6b3f24")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7efe4")]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9c3a5")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        elems.append(t)
    doc.build(elems)
    return buf.getvalue()
