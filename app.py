# Triage clínico — Wizard vertical + sidebar de referencias ocultable
# Parcheado: progreso compatible (0–100 / 0–1), descarga robusta, clamp de step,
# CSS sidebar tolerante, fix fecha "Elegir otra"; selects estandarizados 0–4/0–3/A–E.

import io, json
from datetime import date, datetime
from typing import Dict
import streamlit as st

# ──────────────────────────────────────────────────────────────
# Configuración general
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Triage Clínico",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed"  # referencias ocultas de inicio
)

# Estado inicial
if "step" not in st.session_state:
    st.session_state.step = 1
if "help_width" not in st.session_state:
    st.session_state.help_width = "Estrecho"
if "result" not in st.session_state:
    st.session_state.result = None
if "fecha_modo" not in st.session_state:
    st.session_state.fecha_modo = "Hoy"

# Clamp defensivo del paso (1..9)
if not 1 <= st.session_state.step <= 9:
    st.session_state.step = 1

# Anchos para la sidebar (cuando está visible)
SIDEBAR_WIDTHS = {"Estrecho": 320, "Amplio": 460}

# ──────────────────────────────────────────────────────────────
# Sidebar: referencias completas (ocultable)
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📘 Referencias")

    # Control de ancho del panel de referencias
    ancho_opt = st.selectbox(
        "Ancho de panel",
        ["Estrecho", "Amplio"],
        index=0 if st.session_state.help_width == "Estrecho" else 1,
        help="Ajusta el ancho de esta barra lateral."
    )
    if ancho_opt != st.session_state.help_width:
        st.session_state.help_width = ancho_opt

    # CSS para ensanchar la sidebar (selector tolerante a cambios de DOM)
    st.markdown(
        f"""
        <style>
          section[data-testid="stSidebar"], aside[aria-label="sidebar"] {{
            width: {SIDEBAR_WIDTHS[st.session_state.help_width]}px !important;
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

    with st.expander("Ver/ocultar leyendas y criterios", expanded=False):
        st.markdown("""
**Escalas**
- **0–4**: 0 sin síntomas · 1 leve · 2 moderado · 3 severo · 4 potencialmente mortal  
- **A–E**: A leve · B moderado · C severo · D muy severo · E compromiso vital

**Derivación (del flujograma)**
- **Guardia URGENTE**: Sangrado **C–E**
- **Guardia**: Náuseas **2–3** · Vómitos **B–E** · >7 comp. **loperamida** en 24 h · Dolor abd. **D** ·
  Mucositis **D (3)** · Eritema/descamación **D–E** · Acné **3** · SMP **3** · Hipertensión **4**
- **Interconsulta**: Neuropatía **≥2** · Ototoxicidad
- **Aviso**: **ECOG 3–4** sin paliativos → considerar seguimiento por paliativos
        """)

# ──────────────────────────────────────────────────────────────
# Utilidades de selects estandarizados
# ──────────────────────────────────────────────────────────────
def op_0_4():
    return ["0 — sin síntomas", "1 — leve", "2 — moderado", "3 — severo", "4 — potencialmente mortal"]
def to_0_4(v: str) -> int:
    return int(v.split("—")[0].strip())

def op_0_3(lbl3="3 — severo"):
    return ["0 — sin síntomas", "1 — leve (A)", "2 — moderado (B/C)", lbl3]
def to_0_3(v: str) -> int:
    return int(v.split("—")[0].strip())

def op_A_E(include_zero=True):
    base = ["A — leve", "B — moderado", "C — severo", "D — muy severo", "E — compromiso vital"]
    return (["0 — sin síntomas"] + base) if include_zero else base
def to_A_E(v: str) -> str:
    return v.split("—")[0].strip()

# ──────────────────────────────────────────────────────────────
# Motor de reglas (DOCX)
# ──────────────────────────────────────────────────────────────
PRIORIDAD = {"URGENTE": 3, "Guardia": 2, "Interconsulta": 1, "Continuar": 0}
def decide_higher(current: str, candidate: str) -> str:
    return candidate if PRIORIDAD[candidate] > PRIORIDAD[current] else current

def evaluar(data: Dict) -> Dict:
    rec = "Continuar"; msgs = []; det = {}

    det["DNI"] = data["dni"] or "N/D"
    det["Fecha"] = data["fecha"].isoformat()
    det["Momento tto."] = data["momento"]

    det["RT recibida"] = "Sí" if data["rt"] else "No"
    if data["rt"]:
        det["RT en curso"] = "Sí" if data["rt_en_curso"] else "No"
        if data["rt_en_curso"]:
            det["Semana RT (en curso)"] = data["rt_semana"]
        else:
            det["Tiempo desde fin RT"] = data["rt_fin"]

    det["ECOG"] = data["ecog"]
    det["Paliativos"] = data["paliativos"]
    if data["ecog"] in (3,4) and data["paliativos"] == "No":
        msgs.append("Aviso: ECOG 3–4 sin paliativos → considerar derivación/seguimiento por paliativos.")

    # GI
    if data["gi_on"]:
        if data["diarrea"]:
            det["GI - Diarrea"] = f"Grado {data['diarrea_g']}"
            if not data["lop"]:
                msgs.append("Loperamida: 2 comp. al inicio, luego 1 tras cada deposición (máx. 7/día).")
            elif data["lop_mas7"]:
                rec = decide_higher(rec, "Guardia")
                msgs.append(">7 comprimidos de loperamida en 24 h → **Guardia**.")
        if data["nauseas"]:
            det["GI - Náuseas"] = f"Grado {data['nauseas_g']}"
            if data["nauseas_g"] in (2,3):
                rec = decide_higher(rec, "Guardia"); msgs.append("Náuseas grado 2–3 → **Guardia**.")
            elif data["nauseas_g"] == 1:
                if not data["nauseas_ant"]:
                    msgs.append("Náuseas 1: indicar antiemético (p.ej., Relivera 30 gotas antes de comidas).")
                else:
                    msgs.append("Náuseas 1 con medicación: ajustar esquema con su médico.")
        if data["vom_g"] != "0":
            det["GI - Vómitos"] = f"Grado {data['vom_g']}"
            if data["vom_g"] in ("B","C","D","E"):
                rec = decide_higher(rec, "Guardia"); msgs.append(f"Vómitos {data['vom_g']} → **Guardia**.")
            else:
                msgs.append("Vómitos A: antiemético y control.")
        if data["dolor_abd"] != "No":
            det["GI - Dolor abdominal"] = f"Grado {data['dolor_abd']}"
            if data["dolor_abd"] == "D":
                rec = decide_higher(rec, "Guardia"); msgs.append("Dolor abdominal D → **Guardia**.")

    # Derm
    if data["derm_on"]:
        if data["mucositis"]:
            det["Derm - Mucositis"] = f"Grado {data['mucositis_g']}"
            if data["mucositis_g"] == 3:
                rec = decide_higher(rec, "Guardia"); msgs.append("Mucositis D (3) → **Guardia**.")
        if data["eritema"]:
            det["Derm - Eritema/descamación"] = f"Grado {data['eritema_g']}"
            if data["eritema_g"] in ("D","E"):
                rec = decide_higher(rec, "Guardia"); msgs.append("Eritema/descamación D–E → **Guardia**.")
        if data["acne"]:
            det["Derm - Acné"] = f"Grado {data['acne_g']}"
            if data["acne_g"] == 3:
                rec = decide_higher(rec, "Guardia"); msgs.append("Acné 3 → **Guardia**.")
        if data["smp"]:
            det["Derm - Síndrome mano-pie"] = f"Grado {data['smp_g']}"
            if data["smp_g"] == 3:
                rec = decide_higher(rec, "Guardia"); msgs.append("Síndrome mano-pie 3 → **Guardia**.")

    # Neuro
    if data["neuro_on"]:
        if data["neuropatia"]:
            det["Neuro - Neuropatía"] = f"Grado {data['neuropatia_g']}"
            if data["neuropatia_g"] >= 2:
                rec = decide_higher(rec, "Interconsulta"); msgs.append("Neuropatía ≥2 → **Interconsulta**.")
        if data["ototox"]:
            det["Neuro - Ototoxicidad"] = "Sospecha/Presente"
            rec = decide_higher(rec, "Interconsulta"); msgs.append("Ototoxicidad → **Interconsulta**.")

    # CV
    if data["cv_on"]:
        if data["sang_g"] != "No":
            det["CV - Sangrado"] = f"Grado {data['sang_g']}"
            if data["sang_g"] in ("C","D","E"):
                rec = decide_higher(rec, "URGENTE"); msgs.append("Sangrado C–E → **GUARDIA URGENTE**.")
            else:
                rec = decide_higher(rec, "Guardia"); msgs.append("Sangrado A–B → **Guardia**.")
        if data["hta"]:
            det["CV - HTA"] = f"Grado {data['hta_g']}"
            if data["hta_g"] >= 4:
                rec = decide_higher(rec, "Guardia"); msgs.append("Hipertensión 4 → **Guardia**.")

    if data["otros"]:
        det["Otros"] = data["otros"]

    return {"recomendacion": rec, "mensajes": msgs, "detalles": det}

# ──────────────────────────────────────────────────────────────
# Helpers de navegación (con re-run seguro)
# ──────────────────────────────────────────────────────────────
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass

def next_button(valid: bool):
    left, _ = st.columns([1, 3])
    if left.button("Siguiente", type="primary", use_container_width=True):
        if valid:
            st.session_state.step += 1
            safe_rerun()
        else:
            st.warning("Completa los campos requeridos antes de continuar.")

def finish_button(valid: bool, data: Dict):
    left, _ = st.columns([1, 3])
    if left.button("Finalizar y calcular", type="primary", use_container_width=True):
        if valid:
            st.session_state.result = evaluar(data)
            st.session_state.step += 1
            safe_rerun()
        else:
            st.warning("Completa los campos requeridos antes de finalizar.")

# ──────────────────────────────────────────────────────────────
# FORMULARIO (wizard vertical)
# ──────────────────────────────────────────────────────────────
st.header("🩺 Triage clínico — Formulario")

# Progreso compatible con distintas versiones (0–100 vs 0–1)
TOTAL_STEPS = 8  # pasos del formulario antes del resultado
frac = max(0.0, min(1.0, (st.session_state.step - 1) / TOTAL_STEPS))
try:
    st.progress(int(round(frac * 100)))
except Exception:
    st.progress(frac)

# Paso 1 — Identificación y fecha (bug fix “Elegir otra”)
if st.session_state.step == 1:
    st.subheader("1) Identificación y contexto")
    c1, c2 = st.columns(2)
    st.session_state.dni = c1.text_input("DNI", value=st.session_state.get("dni", ""))
    # modo de fecha con estado persistente
    st.session_state.fecha_modo = c2.radio(
        "Fecha de evaluación",
        ["Hoy", "Elegir otra"],
        horizontal=True,
        index=0 if st.session_state.fecha_modo == "Hoy" else 1,
        key="fecha_modo_radio"
    )
    if st.session_state.fecha_modo == "Elegir otra":
        # aparece SIEMPRE el selector cuando se elige esta opción
        st.session_state.fecha = st.date_input(
            "Selecciona fecha",
            value=st.session_state.get("fecha", date.today()),
            key="fecha_selector"
        )
    else:
        st.session_state.fecha = date.today()
        st.caption(f"Usando fecha de hoy: **{st.session_state.fecha.isoformat()}**")

    valid = bool(st.session_state.dni.strip())
    next_button(valid)

# Paso 2 — Momento y RT
if st.session_state.step == 2:
    st.subheader("2) Momento y radioterapia")
    st.session_state.momento = st.radio(
        "Momento del tratamiento",
        ["< 7 días", "> 7 días", "Semana de descanso"],
        horizontal=True
    )
    st.session_state.rt = st.radio("¿Recibió radioterapia?", ["No", "Sí"], horizontal=True) == "Sí"
    st.session_state.rt_en_curso = False
    st.session_state.rt_semana = None
    st.session_state.rt_fin = None
    if st.session_state.rt:
        st.session_state.rt_en_curso = st.radio(
            "¿Radioterapia en curso?", ["Sí", "No"], horizontal=True, index=1
        ) == "Sí"
        if st.session_state.rt_en_curso:
            st.session_state.rt_semana = st.selectbox(
                "Semana de tratamiento (si está en curso)", ["< 7 días", "> 7 días", "> 14 días"]
            )
        else:
            st.session_state.rt_fin = st.selectbox(
                "Tiempo desde fin de radioterapia", ["< 7 días", "> 7 días"]
            )
    valid = True
    if st.session_state.rt and st.session_state.rt_en_curso and not st.session_state.rt_semana:
        valid = False
    if st.session_state.rt and (not st.session_state.rt_en_curso) and not st.session_state.rt_fin:
        valid = False
    next_button(valid)

# Paso 3 — ECOG & Paliativos (selects)
if st.session_state.step == 3:
    st.subheader("3) ECOG & Paliativos")
    c1, c2 = st.columns(2)
    st.session_state.ecog = to_0_4(c1.selectbox("ECOG (0–4)", op_0_4(), index=0))
    st.session_state.paliativos = c2.radio("¿En cuidados paliativos?", ["N/A", "Sí", "No"], horizontal=True)
    next_button(True)

# Paso 4 — Gastrointestinales
if st.session_state.step == 4:
    st.subheader("4) Síntomas por sistema — Gastrointestinales")
    st.session_state.gi_on = st.checkbox("Registrar síntomas gastrointestinales", value=False)
    diarrea = False; diarrea_g = 0; lop = False; lop_mas7 = False
    nauseas = False; nauseas_g = 0; nauseas_ant = False
    vom_g = "0"; dolor_abd = "No"
    if st.session_state.gi_on:
        g1, g2 = st.columns(2)
        diarrea = g1.radio("¿Diarrea?", ["No", "Sí"], horizontal=True) == "Sí"
        if diarrea:
            diarrea_g = to_0_4(g2.selectbox("Grado de diarrea (0–4)", op_0_4(), index=0))
            gg1, gg2 = st.columns(2)
            lop = gg1.radio("¿Usó loperamida?", ["No", "Sí"], horizontal=True) == "Sí"
            if lop:
                lop_mas7 = gg2.radio(">7 comprimidos en 24 h", ["No", "Sí"], horizontal=True) == "Sí"

        st.markdown("---")
        h1, h2 = st.columns(2)
        nauseas = h1.radio("¿Náuseas?", ["No", "Sí"], horizontal=True) == "Sí"
        if nauseas:
            nauseas_g = to_0_3(h2.selectbox("Grado de náuseas (0–3)", op_0_3("3 — severo"), index=0))
            nauseas_ant = st.radio("¿Usa antiemético?", ["No", "Sí"], horizontal=True) == "Sí"

        st.markdown("---")
        k1, k2 = st.columns(2)
        vom_g = to_A_E(k1.selectbox("Vómitos (A–E; 0 = sin síntomas)", op_A_E(True), index=0))
        dolor_abd = k2.selectbox("Dolor abdominal", ["No", "A", "B", "C", "D"], index=0)

    st.session_state.diarrea = diarrea
    st.session_state.diarrea_g = diarrea_g
    st.session_state.lop = lop
    st.session_state.lop_mas7 = lop_mas7
    st.session_state.nauseas = nauseas
    st.session_state.nauseas_g = nauseas_g
    st.session_state.nauseas_ant = nauseas_ant
    st.session_state.vom_g = vom_g
    st.session_state.dolor_abd = dolor_abd
    next_button(True)

# Paso 5 — Dermatológicos
if st.session_state.step == 5:
    st.subheader("5) Síntomas por sistema — Dermatológicos")
    st.session_state.derm_on = st.checkbox("Registrar síntomas dermatológicos", value=False)
    mucositis = False; mucositis_g = 0
    eritema = False; eritema_g = "A"
    acne = False; acne_g = 0
    smp = False; smp_g = 0
    if st.session_state.derm_on:
        d1, d2 = st.columns(2)
        mucositis = d1.radio("¿Mucositis?", ["No", "Sí"], horizontal=True) == "Sí"
        if mucositis:
            mucositis_g = to_0_3(d2.selectbox("Grado mucositis (0–3; D=3)", op_0_3("3 — severo (D)"), index=0))
        st.markdown("---")
        d3, d4 = st.columns(2)
        eritema = d3.radio("¿Eritema/descamación?", ["No", "Sí"], horizontal=True) == "Sí"
        if eritema:
            eritema_g = to_A_E(d4.selectbox("Grado eritema/descamación (A–E)", op_A_E(False), index=0))
        st.markdown("---")
        d5, d6 = st.columns(2)
        acne = d5.radio("¿Acné?", ["No", "Sí"], horizontal=True) == "Sí"
        if acne:
            acne_g = to_0_3(d6.selectbox("Grado acné (0–3)", op_0_3("3 — severo"), index=0))
        st.markdown("---")
        d7, d8 = st.columns(2)
        smp = d7.radio("¿Síndrome mano-pie?", ["No", "Sí"], horizontal=True) == "Sí"
        if smp:
            smp_g = to_0_3(d8.selectbox("Grado SMP (0–3)", op_0_3("3 — severo"), index=0))
    st.session_state.mucositis = mucositis
    st.session_state.mucositis_g = mucositis_g
    st.session_state.eritema = eritema
    st.session_state.eritema_g = eritema_g
    st.session_state.acne = acne
    st.session_state.acne_g = acne_g
    st.session_state.smp = smp
    st.session_state.smp_g = smp_g
    next_button(True)

# Paso 6 — Neurológicos
if st.session_state.step == 6:
    st.subheader("6) Síntomas por sistema — Neurológicos")
    st.session_state.neuro_on = st.checkbox("Registrar síntomas neurológicos", value=False)
    neuropatia = False; neuropatia_g = 0; ototox = False
    if st.session_state.neuro_on:
        n1, n2 = st.columns(2)
        neuropatia = n1.radio("¿Neuropatía?", ["No", "Sí"], horizontal=True) == "Sí"
        if neuropatia:
            neuropatia_g = to_0_3(n2.selectbox("Grado neuropatía (0–3)", op_0_3("3 — severo"), index=0))
        ototox = st.radio("¿Ototoxicidad (hipoacusia/tinnitus)?", ["No", "Sí"], horizontal=True) == "Sí"
    st.session_state.neuropatia = neuropatia
    st.session_state.neuropatia_g = neuropatia_g
    st.session_state.ototox = ototox
    next_button(True)

# Paso 7 — Cardiovasculares
if st.session_state.step == 7:
    st.subheader("7) Síntomas por sistema — Cardiovasculares")
    st.session_state.cv_on = st.checkbox("Registrar síntomas cardiovasculares", value=False)
    sang_g = "No"; hta = False; hta_g = 0
    if st.session_state.cv_on:
        c1, c2 = st.columns(2)
        sang_g = to_A_E(c1.selectbox("Sangrado (A–E; 0 = sin síntomas)", op_A_E(True), index=0))
        hta = c2.radio("¿Hipertensión?", ["No", "Sí"], horizontal=True) == "Sí"
        if hta:
            hta_g = to_0_4(st.selectbox("Grado HTA (0–4)", op_0_4(), index=0))
    st.session_state.sang_g = sang_g
    st.session_state.hta = hta
    st.session_state.hta_g = hta_g
    next_button(True)

# Paso 8 — Otros + Finalizar
if st.session_state.step == 8:
    st.subheader("8) Otros / cierre")
    st.session_state.otros = st.text_area("Otros (campo libre)", height=80).strip()

    data = dict(
        dni=st.session_state.dni, fecha=st.session_state.fecha, momento=st.session_state.momento,
        rt=st.session_state.rt, rt_en_curso=st.session_state.rt_en_curso,
        rt_semana=st.session_state.rt_semana, rt_fin=st.session_state.rt_fin,
        ecog=st.session_state.ecog, paliativos=st.session_state.paliativos,
        gi_on=st.session_state.gi_on, diarrea=st.session_state.diarrea,
        diarrea_g=st.session_state.diarrea_g, lop=st.session_state.lop,
        lop_mas7=st.session_state.lop_mas7, nauseas=st.session_state.nauseas,
        nauseas_g=st.session_state.nauseas_g, nauseas_ant=st.session_state.nauseas_ant,
        vom_g=st.session_state.vom_g, dolor_abd=st.session_state.dolor_abd,
        derm_on=st.session_state.derm_on, mucositis=st.session_state.mucositis,
        mucositis_g=st.session_state.mucositis_g, eritema=st.session_state.eritema,
        eritema_g=st.session_state.eritema_g, acne=st.session_state.acne,
        acne_g=st.session_state.acne_g, smp=st.session_state.smp, smp_g=st.session_state.smp_g,
        neuro_on=st.session_state.neuro_on, neuropatia=st.session_state.neuropatia,
        neuropatia_g=st.session_state.neuropatia_g, ototox=st.session_state.ototox,
        cv_on=st.session_state.cv_on, sang_g=st.session_state.sang_g,
        hta=st.session_state.hta, hta_g=st.session_state.hta_g,
        otros=st.session_state.otros,
    )
    finish_button(True, data)

# Paso 9 — Resultado
if st.session_state.step == 9 and st.session_state.result:
    res = st.session_state.result
    rec = res["recomendacion"]

    st.success(f"Recomendación final: **{rec}**")
    if rec == "URGENTE":
        st.error("Derivar a **GUARDIA URGENTE**. Activar protocolo de emergencia y documentar SV.")
    elif rec == "Guardia":
        st.warning("Derivar a **Guardia** para evaluación inmediata.")
    elif rec == "Interconsulta":
        st.info("Coordinar **interconsulta** (servicio correspondiente) a corto plazo.")
    else:
        st.success("**Continuar** seguimiento + educación de signos de alarma.")

    if res["mensajes"]:
        st.markdown("**Observaciones/acciones**")
        for m in res["mensajes"]:
            st.markdown(f"- {m}")

    st.markdown("**Resumen de respuestas**")
    for k, v in res["detalles"].items():
        st.markdown(f"- **{k}:** {v}")

    # Descarga JSON (usa bytes, no file-like)
    payload = {
        "datos": {"dni": st.session_state.dni, "fecha": st.session_state.fecha.isoformat(),
                  "momento": st.session_state.momento},
        "resultado": res,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    json_bytes = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    st.download_button(
        "⬇️ Descargar informe (JSON)",
        data=json_bytes.getvalue(),  # <- robusto entre versiones
        file_name=f"triage_{st.session_state.dni or 'ND'}.json",
        mime="application/json"
    )

    st.button("🔄 Reiniciar", on_click=lambda: (st.session_state.clear(), safe_rerun()))
