# Triage clínico — Wizard vertical + sidebar de referencias ocultable
# - Fecha: selector aparece al elegir "Elegir otra" (bug fix)
# - Referencias: TODO en la sidebar (colapsada), con ancho ajustable
# - Selects estandarizados (número + texto) para todos los grados
# - Lógica alineada al DOCX

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
if "step" not in st.session_state: st.session_state.step = 1
if "help_width" not in st.session_state: st.session_state.help_width = "Estrecho"
if "result" not in st.session_state: st.session_state.result = None

# Anchos para la sidebar (cuando está visible)
SIDEBAR_WIDTHS = {"Estrecho": 320, "Amplio": 460}

# ──────────────────────────────────────────────────────────────
# Sidebar: referencias completas (ocultable)
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📘 Referencias")
    # Control de ancho del panel de referencias
    ancho_opt = st.selectbox("Ancho de panel", ["Estrecho", "Amplio"],
                             index=0 if st.session_state.help_width=="Estrecho" else 1,
                             help="Ajusta el ancho de esta barra lateral.")
    if ancho_opt != st.session_state.help_width:
        st.session_state.help_width = ancho_opt

    # CSS para ensanchar la sidebar cuando corresponda
    st.markdown(
        f"""
        <style>
          section[data-testid="stSidebar"] {{
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
    return [
        "0 — sin síntomas", "1 — leve", "2 — moderado",
        "3 — severo", "4 — potencialmente mortal"
    ]
def to_0_4(v: str) -> int: return int(v.split("—")[0].strip())

def op_0_3(lbl3="3 — severo"):
    return ["0 — sin síntomas", "1 — leve (A)", "2 — moderado (B/C)", lbl3]
def to_0_3(v: str) -> int: return int(v.split("—")[0].strip())

def op_A_E(include_zero=True):
    base = ["A — leve","B — moderado","C — severo","D — muy severo","E — compromiso vital"]
    return (["0 — sin síntomas"] + base) if include_zero else base
def to_A_E(v: str) -> str: return v.split("—")[0].strip()

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
# Helpers de navegación
# ──────────────────────────────────────────────────────────────
def next_button(valid: bool):
    left, _ = st.columns([1,3])
    if left.button("Siguiente", type="primary", use_container_width=True):
        if valid:
            st.session_state.step += 1
            st.rerun()
        else:
            st.warning("Completa los campos requeridos antes de continuar.")

def finish_button(valid: bool, data: Dict):
    left, _ = st.columns([1,3])
    if left.button("Finalizar y calcular", type="primary", use_container_width=True):
        if valid:
            st.session_state.result = evaluar(data)
            st.session_state.step += 1
            st.rerun()
        else:
            st.warning("Completa los campos requeridos antes de finalizar.")

# ──────────────────────────────────────────────────────────────
# FORMULARIO (wizard vertical)
# ──────────────────────────────────────────────────────────────
st.header("🩺 Triage clínico — Formulario")
st.progress((st.session_state.step-1)/7)

# Paso 1 — Identificación y fecha (bug fix “Elegir otra”)
if st.session_state.step == 1:
    st.subheader("1) Identificación y contexto")
    c1, c2 = st.columns(2)
    st.session_state.dni = c1.text_input("DNI", value=st.session_state.get("dni",""))
    # modo de fecha con estado persistente
    st.session_state.fecha_modo = c2.radio(
        "Fecha de evaluación", ["Hoy", "Elegir otra"],
        horizontal=True, index=0 if st.session_state.get("fecha_modo","Hoy")=="Hoy" else 1, key="f
