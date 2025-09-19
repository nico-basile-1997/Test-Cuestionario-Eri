# app.py — Triage clínico (Streamlit)
# UI estandarizada + leyendas | Lógica alineada al DOCX

import json, io
from datetime import datetime, date
from typing import Dict
import streamlit as st

# ---------- Página ----------
st.set_page_config(page_title="Triage Clínico", page_icon="🩺", layout="centered")

st.title("🩺 Triage clínico")
st.caption("Basado en el flujograma original. No reemplaza criterio médico.")

# ---------- Utilidades ----------
PRIORIDAD = {"URGENTE": 3, "Guardia": 2, "Interconsulta": 1, "Continuar": 0}
def decide_higher(current: str, candidate: str) -> str:
    return candidate if PRIORIDAD[candidate] > PRIORIDAD[current] else current

def op_0_4():
    return [
        "0 — sin síntomas",
        "1 — leve",
        "2 — moderado",
        "3 — severo",
        "4 — potencialmente mortal",
    ]
def to_0_4(val: str) -> int:
    return int(val.split("—")[0].strip())

def op_0_3(lbl3="3 — severo"):
    return ["0 — sin síntomas", "1 — leve (A)", "2 — moderado (B/C)", lbl3]
def to_0_3(val: str) -> int:
    return int(val.split("—")[0].strip())

def op_A_E(include_zero=True):
    base = ["A — leve","B — moderado","C — severo","D — muy severo","E — compromiso vital"]
    return (["0 — sin síntomas"] + base) if include_zero else base
def to_A_E(val: str) -> str:
    return val.split("—")[0].strip()  # "0" | "A"…"E"

def leyendas():
    with st.sidebar.expander("📘 Leyendas y criterios", expanded=True):
        st.markdown("""
**Escalas**
- **0–4**: 0 sin síntomas · 1 leve · 2 moderado · 3 severo · 4 potencialmente mortal  
- **A–E**: A leve · B moderado · C severo · D muy severo · E compromiso vital

**Derivación**
- **Guardia URGENTE**: Sangrado **C–E**  
- **Guardia**: Náuseas **2–3** · Vómitos **B–E** · >7 comp. **loperamida** en 24 h · Dolor abd. **D** ·
  Mucositis **D (3)** · Eritema/descamación **D–E** · Acné **3** · SMP **3** · Hipertensión **4**
- **Interconsulta**: Neuropatía **≥2** · Ototoxicidad  
- **Aviso**: **ECOG 3–4** sin paliativos → considerar seguimiento por paliativos
        """)
        st.toggle("🔎 Modo expandido (mostrar todos los campos)", key="expanded", value=False)

def evaluar(data: Dict) -> Dict:
    rec = "Continuar"; msgs = []; det = {}

    det["DNI"] = data["dni"] or "N/D"
    det["Fecha"] = data["fecha"].isoformat()
    det["Momento tto."] = data["momento"]

    # Radioterapia
    det["RT recibida"] = "Sí" if data["rt"] else "No"
    if data["rt"]:
        det["RT en curso"] = "Sí" if data["rt_en_curso"] else "No"
        if data["rt_en_curso"]:
            det["Semana RT (en curso)"] = data["rt_semana"]
        else:
            det["Tiempo desde fin RT"] = data["rt_fin"]

    # ECOG & paliativos (solo aviso)
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
            else:
                if data["lop_mas7"]:
                    rec = decide_higher(rec, "Guardia")
                    msgs.append(">7 comprimidos de loperamida en 24 h → **Guardia**.")

        if data["nauseas"]:
            det["GI - Náuseas"] = f"Grado {data['nauseas_g']}"
            if data["nauseas_g"] in (2,3):
                rec = decide_higher(rec, "Guardia"); msgs.append("Náuseas grado 2–3 → **Guardia**.")
            elif data["nauseas_g"] == 1:
                if not data["nauseas_ant"]:
                    msgs.append("Náuseas grado 1: indicar antiemético (p.ej., Relivera 30 gotas antes de comidas).")
                else:
                    msgs.append("Náuseas grado 1 con medicación: ajustar esquema con su médico.")

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

    # Dermatológicos
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

    # Neurológicos
    if data["neuro_on"]:
        if data["neuropatia"]:
            det["Neuro - Neuropatía"] = f"Grado {data['neuropatia_g']}"
            if data["neuropatia_g"] >= 2:
                rec = decide_higher(rec, "Interconsulta"); msgs.append("Neuropatía ≥2 → **Interconsulta**.")
        if data["ototox"]:
            det["Neuro - Ototoxicidad"] = "Sospecha/Presente"
            rec = decide_higher(rec, "Interconsulta"); msgs.append("Ototoxicidad → **Interconsulta**.")

    # Cardiovasculares
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

# ---------- Sidebar ----------
leyendas()

# ---------- Tabs ----------
tabs = st.tabs([
    "1) Identificación", "2) Radioterapia", "3) ECOG & Paliativos",
    "4) GI", "5) Derm", "6) Neuro", "7) CV", "8) Otros"
])

with tabs[0]:
    col1, col2 = st.columns(2)
    dni = col1.text_input("DNI")
    fecha = col2.date_input("Fecha", value=date.today())
    momento = st.radio("Momento del tratamiento", ["< 7 días", "> 7 días", "Semana de descanso"], horizontal=True)

with tabs[1]:
    rt = st.radio("¿Recibió radioterapia?", ["No","Sí"], horizontal=True) == "Sí"
    rt_en_curso = False
    rt_semana = None
    rt_fin = None
    if st.session_state.get("expanded") or rt:
        rt_en_curso = st.radio("¿Radioterapia en curso?", ["Sí","No"], horizontal=True, index=1) == "Sí"
        if st.session_state.get("expanded") or rt_en_curso:
            rt_semana = st.selectbox("Semana de tratamiento (si está en curso)", ["< 7 días", "> 7 días", "> 14 días"])
        if st.session_state.get("expanded") or (rt and not rt_en_curso):
            rt_fin = st.selectbox("Tiempo desde fin de radioterapia", ["< 7 días", "> 7 días"])

with tabs[2]:
    col1, col2 = st.columns(2)
    ecog = col1.number_input("ECOG (0–4)", min_value=0, max_value=4, value=0, step=1)
    paliativos = col2.radio("¿En cuidados paliativos?", ["N/A","Sí","No"], horizontal=True)

with tabs[3]:
    gi_on = st.checkbox("Incluir síntomas gastrointestinales", value=False)
    diarrea = False; diarrea_g = 0; lop = False; lop_mas7 = False
    nauseas = False; nauseas_g = 0; nauseas_ant = False
    vom_g = "0"; dolor_abd = "No"

    if st.session_state.get("expanded") or gi_on:
        st.subheader("Gastrointestinales")
        c1, c2 = st.columns(2)
        diarrea = c1.radio("¿Diarrea?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or diarrea:
            diarrea_g = to_0_4(c2.selectbox("Grado de diarrea (0–4)", op_0_4(), index=0))
            cc1, cc2 = st.columns(2)
            lop = cc1.radio("¿Usó loperamida?", ["No","Sí"], horizontal=True) == "Sí"
            if st.session_state.get("expanded") or lop:
                lop_mas7 = cc2.radio(">7 comprimidos en 24 h", ["No","Sí"], horizontal=True) == "Sí"

        st.divider()
        c3, c4 = st.columns(2)
        nauseas = c3.radio("¿Náuseas?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or nauseas:
            nauseas_g = to_0_3(c4.selectbox("Grado de náuseas (0–3)", op_0_3("3 — severo"), index=0))
            nauseas_ant = st.radio("¿Usa antiemético?", ["No","Sí"], horizontal=True) == "Sí"

        st.divider()
        c5, c6 = st.columns(2)
        vom_g = to_A_E(c5.selectbox("Vómitos (A–E; 0 = sin síntomas)", op_A_E(True), index=0))
        dolor_abd = c6.selectbox("Dolor abdominal", ["No","A","B","C","D"], index=0)

with tabs[4]:
    derm_on = st.checkbox("Incluir síntomas dermatológicos", value=False)
    mucositis = False; mucositis_g = 0
    eritema = False; eritema_g = "A"
    acne = False; acne_g = 0
    smp = False; smp_g = 0

    if st.session_state.get("expanded") or derm_on:
        st.subheader("Dermatológicos")
        c1, c2 = st.columns(2)
        mucositis = c1.radio("¿Mucositis?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or mucositis:
            mucositis_g = to_0_3(c2.selectbox("Grado mucositis (0–3; D=3)", op_0_3("3 — severo (D)"), index=0))

        st.divider()
        c3, c4 = st.columns(2)
        eritema = c3.radio("¿Eritema/descamación?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or eritema:
            eritema_g = to_A_E(c4.selectbox("Grado eritema/descamación (A–E)", op_A_E(False), index=0))

        st.divider()
        c5, c6 = st.columns(2)
        acne = c5.radio("¿Acné?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or acne:
            acne_g = to_0_3(c6.selectbox("Grado acné (0–3)", op_0_3("3 — severo"), index=0))

        st.divider()
        c7, c8 = st.columns(2)
        smp = c7.radio("¿Síndrome mano-pie?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or smp:
            smp_g = to_0_3(c8.selectbox("Grado SMP (0–3)", op_0_3("3 — severo"), index=0))

with tabs[5]:
    neuro_on = st.checkbox("Incluir síntomas neurológicos", value=False)
    neuropatia = False; neuropatia_g = 0; ototox = False

    if st.session_state.get("expanded") or neuro_on:
        st.subheader("Neurológicos")
        c1, c2 = st.columns(2)
        neuropatia = c1.radio("¿Neuropatía?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or neuropatia:
            neuropatia_g = to_0_3(c2.selectbox("Grado neuropatía (0–3)", op_0_3("3 — severo"), index=0))
        ototox = st.radio("¿Ototoxicidad (hipoacusia/tinnitus)?", ["No","Sí"], horizontal=True) == "Sí"

with tabs[6]:
    cv_on = st.checkbox("Incluir síntomas cardiovasculares", value=False)
    sang_g = "No"; hta = False; hta_g = 0

    if st.session_state.get("expanded") or cv_on:
        st.subheader("Cardiovasculares")
        c1, c2 = st.columns(2)
        sang_g = to_A_E(c1.selectbox("Sangrado (A–E; 0 = sin síntomas)", op_A_E(True), index=0))
        hta = c2.radio("¿Hipertensión?", ["No","Sí"], horizontal=True) == "Sí"
        if st.session_state.get("expanded") or hta:
            hta_g = to_0_4(st.selectbox("Grado HTA (0–4)", op_0_4(), index=0))

with tabs[7]:
    otros = st.text_area("Otros (campo libre)", height=80)

# ---------- Calcular ----------
if st.button("Calcular recomendación", type="primary"):
    data = dict(
        dni=dni, fecha=fecha, momento=momento,
        rt=rt, rt_en_curso=rt_en_curso, rt_semana=rt_semana, rt_fin=rt_fin,
        ecog=ecog, paliativos=paliativos,
        gi_on=gi_on, diarrea=diarrea, diarrea_g=diarrea_g, lop=lop, lop_mas7=lop_mas7,
        nauseas=nauseas, nauseas_g=nauseas_g, nauseas_ant=nauseas_ant,
        vom_g=vom_g, dolor_abd=dolor_abd,
        derm_on=derm_on, mucositis=mucositis, mucositis_g=mucositis_g,
        eritema=eritema, eritema_g=eritema_g, acne=acne, acne_g=acne_g,
        smp=smp, smp_g=smp_g,
        neuro_on=neuro_on, neuropatia=neuropatia, neuropatia_g=neuropatia_g, ototox=ototox,
        cv_on=cv_on, sang_g=sang_g, hta=hta, hta_g=hta_g,
        otros=otros.strip()
    )

    resultado = evaluar(data)
    rec = resultado["recomendacion"]

    st.subheader(f"Recomendación final: **{rec}**")
    if rec == "URGENTE":
        st.error("Derivar a **GUARDIA URGENTE**. Activar protocolo de emergencia y documentar SV.")
    elif rec == "Guardia":
        st.warning("Derivar a **Guardia** para evaluación inmediata.")
    elif rec == "Interconsulta":
        st.info("Coordinar **interconsulta** (servicio correspondiente) a corto plazo.")
    else:
        st.success("**Continuar** seguimiento + educación de signos de alarma.")

    if resultado["mensajes"]:
        st.markdown("**Observaciones/acciones**")
        for m in resultado["mensajes"]:
            st.markdown(f"- {m}")

    st.markdown("**Resumen de respuestas**")
    for k, v in resultado["detalles"].items():
        st.markdown(f"- **{k}:** {v}")

    # Descargas
    payload = {
        "datos": {
            "dni": dni, "fecha": fecha.isoformat(), "momento": momento
        },
        "resultado": resultado,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    json_bytes = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    st.download_button("⬇️ Descargar informe (JSON)", data=json_bytes,
                       file_name=f"triage_{dni or 'ND'}.json", mime="application/json")

    # CSV simple
    csv_lines = ["campo;valor"]
    for k, v in resultado["detalles"].items():
        csv_lines.append(f"{k};{v}")
    csv_lines.append(f"Recomendación;{rec}")
    st.download_button("⬇️ Descargar informe (CSV)",
                       data="\n".join(csv_lines).encode("utf-8"),
                       file_name=f"triage_{dni or 'ND'}.csv", mime="text/csv")
