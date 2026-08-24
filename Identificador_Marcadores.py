import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "base_maestra.xlsx"

st.set_page_config(page_title="Asistente molecular Nanopore", page_icon="🧬", layout="wide")


def norm_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9+./ -]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_items(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    parts = re.split(r"\s*;\s*|\s*,\s*", str(value))
    return [p.strip() for p in parts if p and p.strip()]


@st.cache_data(show_spinner=False)
def load_book(path_str):
    path = Path(path_str)
    base = pd.read_excel(path, sheet_name="Base_maestra")
    primers = pd.read_excel(path, sheet_name="Catalogo_partidores")
    allowed = pd.read_excel(path, sheet_name="Marcadores_permitidos")
    rules = pd.read_excel(path, sheet_name="Reglas_familia")
    qa = pd.read_excel(path, sheet_name="QA")
    return base, primers, allowed, rules, qa


def make_search_blob(row):
    fields = ["Grupo", "Clado", "Clase", "Orden", "Familia", "Genero", "Especie", "Sinonimia"]
    return " | ".join(norm_text(row.get(c, "")) for c in fields)


def score_row(row, query):
    q = norm_text(query)
    if not q:
        return 0.0, []
    score = 0.0
    reasons = []
    weights = [
        ("Especie", 100), ("Sinonimia", 80), ("Genero", 55), ("Familia", 42),
        ("Orden", 32), ("Clase", 24), ("Clado", 18), ("Grupo", 12),
    ]
    for field, weight in weights:
        val = norm_text(row.get(field, ""))
        if not val:
            continue
        # Exact taxon mention in free text.
        if val in q:
            score += weight
            reasons.append(f"{field}: {row.get(field)}")
            continue
        # Synonym cell may contain slash-separated names.
        if field == "Sinonimia":
            for syn in re.split(r"\s*/\s*|\s*;\s*", val):
                if len(syn) >= 5 and syn in q:
                    score += weight
                    reasons.append(f"Sinonimia: {syn}")
                    break
        # Conservative fuzzy match only for taxonomic words present in query.
        if field in {"Especie", "Genero", "Familia", "Orden"}:
            tokens = [t for t in re.split(r"\W+", q) if len(t) >= 5]
            val_tokens = [t for t in re.split(r"\W+", val) if len(t) >= 5]
            best = 0
            for a in tokens:
                for b in val_tokens:
                    best = max(best, SequenceMatcher(None, a, b).ratio())
            if best >= 0.90:
                score += weight * 0.20
    return score, reasons


def rank_candidates(base, query, filters):
    df = base.copy()
    for col, selected in filters.items():
        if selected and selected != "Todos":
            df = df[df[col].astype(str) == selected]
    scored = []
    for idx, row in df.iterrows():
        score, reasons = score_row(row, query)
        scored.append((idx, score, "; ".join(reasons)))
    if not scored:
        return pd.DataFrame()
    meta = pd.DataFrame(scored, columns=["_idx", "Puntaje", "Coincidencias"])
    out = df.reset_index().rename(columns={"index": "_idx"}).merge(meta, on="_idx", how="left")
    if query.strip():
        out = out[out["Puntaje"] > 0]
    out = out.sort_values(["Puntaje", "Especie"], ascending=[False, True])
    return out


def panel_applicability(panel_row, taxon_row, allowed_markers):
    marker = norm_text(panel_row.get("Marcador_autorizado", ""))
    if not any(norm_text(m) in marker or marker in norm_text(m) for m in allowed_markers if norm_text(m)):
        return None

    scope = norm_text(str(panel_row.get("Alcance", "")) + " " + str(panel_row.get("Nivel_objetivo", "")))
    family = norm_text(taxon_row.get("Familia", ""))
    genus = norm_text(taxon_row.get("Genero", ""))
    order = norm_text(taxon_row.get("Orden", ""))
    clade = norm_text(taxon_row.get("Clado", ""))
    group = norm_text(taxon_row.get("Grupo", ""))

    for label, val in [("género", genus), ("familia", family), ("orden", order), ("clado", clade)]:
        if val and val in scope:
            return f"Dirigido al {label}"

    # Generic panels can be shown, but never as family-specific validation.
    bacterial_generic = group.startswith("bacter") and any(x in scope for x in ["bacter", "universal"])
    fungal_generic = (group.startswith("hongo") or group.startswith("levadura")) and any(x in scope for x in ["fung", "hongo", "levadura", "universal"])
    archaea_generic = group.startswith("arque") and any(x in scope for x in ["archaea", "arque"])
    if bacterial_generic or fungal_generic or archaea_generic:
        return "Panel general del grupo; validar cobertura"

    # Avoid borrowing a panel explicitly named for another family/genus.
    return None


def get_primer_panels(primers, taxon_row):
    markers = split_items(taxon_row.get("Marcadores_normalizados", ""))
    rows = []
    for panel_id, grp in primers.groupby("Panel_ID", dropna=False):
        first = grp.iloc[0]
        applicability = panel_applicability(first, taxon_row, markers)
        if applicability:
            rows.append((str(panel_id), applicability, grp.copy()))
    return rows


def confidence_label(cands, query):
    if cands.empty:
        return "Sin coincidencia", "No se encontró un taxón del catálogo a partir de las pistas disponibles."
    top = float(cands.iloc[0]["Puntaje"])
    if not query.strip():
        return "Filtrado manual", "La selección se basa en filtros estructurados, no en el texto libre."
    if top >= 90:
        return "Alta", "La descripción contiene una especie o sinonimia muy compatible con el catálogo."
    if top >= 50:
        return "Media", "La descripción apunta al menos a género/familia, pero requiere confirmación."
    return "Baja", "La coincidencia es amplia; revise los candidatos antes de elegir un flujo molecular."


st.title("🧬 Asistente de decisión molecular para microorganismos")
st.caption("Basado exclusivamente en la base maestra y en los marcadores autorizados del Excel original.")

with st.sidebar:
    st.header("Base de datos")
    uploaded = st.file_uploader("Usar otra base maestra (.xlsx)", type=["xlsx"])
    if uploaded:
        temp_path = APP_DIR / "_base_temporal.xlsx"
        temp_path.write_bytes(uploaded.getbuffer())
        db_path = temp_path
    else:
        db_path = DEFAULT_DB

try:
    base, primers, allowed, rules, qa = load_book(str(db_path))
except Exception as exc:
    st.error(f"No se pudo cargar la base maestra: {exc}")
    st.stop()

with st.sidebar:
    st.success(f"{len(base)} microorganismos cargados")
    st.caption(f"{base['Orden'].nunique()} órdenes · {base['Familia'].nunique()} familias")
    st.divider()
    st.subheader("Filtros opcionales")
    group_opts = ["Todos"] + sorted(base["Grupo"].dropna().astype(str).unique().tolist())
    group_sel = st.selectbox("Grupo", group_opts)
    base_group = base if group_sel == "Todos" else base[base["Grupo"].astype(str) == group_sel]
    clade_opts = ["Todos"] + sorted(base_group["Clado"].dropna().astype(str).unique().tolist())
    clade_sel = st.selectbox("Clado", clade_opts)
    base_clade = base_group if clade_sel == "Todos" else base_group[base_group["Clado"].astype(str) == clade_sel]
    order_opts = ["Todos"] + sorted(base_clade["Orden"].dropna().astype(str).unique().tolist())
    order_sel = st.selectbox("Orden", order_opts)
    base_order = base_clade if order_sel == "Todos" else base_clade[base_clade["Orden"].astype(str) == order_sel]
    family_opts = ["Todos"] + sorted(base_order["Familia"].dropna().astype(str).unique().tolist())
    family_sel = st.selectbox("Familia", family_opts)

st.subheader("1. Describe el microorganismo sospechoso")
query = st.text_area(
    "Puedes incluir nombre sospechoso, género, familia u otras observaciones.",
    placeholder="Ej.: aislado bacteriano; sospecha de Pseudomonas fluorescens...",
    height=120,
)

filters = {"Grupo": group_sel, "Clado": clade_sel, "Orden": order_sel, "Familia": family_sel}
cands = rank_candidates(base, query, filters)
conf, conf_note = confidence_label(cands, query)

col1, col2 = st.columns([1, 2])
with col1:
    st.metric("Confianza de búsqueda", conf)
with col2:
    st.info(conf_note)

if cands.empty:
    st.warning("No hay una coincidencia taxonómica utilizable. Selecciona filtros o incluye al menos un nombre de género, familia, orden o especie que esté en el catálogo.")
    st.stop()

show_cols = ["Especie", "Genero", "Familia", "Orden", "Grupo", "Puntaje", "Coincidencias"]
st.subheader("2. Candidatos del catálogo")
st.dataframe(cands[show_cols].head(12), use_container_width=True, hide_index=True)

options = cands.head(30).copy()
options["_label"] = options.apply(lambda r: f"{r['Especie']}  |  {r['Familia']}  |  {r['Orden']}", axis=1)
selected_label = st.selectbox("Selecciona el microorganismo/candidato para generar el flujo", options["_label"].tolist())
row = options[options["_label"] == selected_label].iloc[0]

st.subheader("3. Identificación taxonómica de referencia")
tax_cols = st.columns(6)
for c, label in zip(tax_cols, ["Grupo", "Clado", "Clase", "Orden", "Familia", "Genero"]):
    c.markdown(f"**{label}**")
    c.write(row.get(label, "—") if pd.notna(row.get(label, None)) else "—")
st.markdown(f"**Especie:** *{row['Especie']}*")
if pd.notna(row.get("Sinonimia", None)) and str(row.get("Sinonimia")).strip():
    st.caption(f"Sinonimia registrada: {row['Sinonimia']}")

st.subheader("4. Flujo molecular recomendado por la base")
left, right = st.columns(2)
with left:
    st.markdown("#### Marcadores del Excel original")
    st.write(row.get("Marcadores_originales", "—"))
    st.caption("Esta recomendación se conserva literalmente desde la base original.")
with right:
    st.markdown("#### Secuencia de decisión")
    p1 = row.get("Paso_1_original", "")
    p2 = row.get("Paso_2_original", "")
    if pd.notna(p1) and str(p1).strip():
        st.markdown(f"**Paso 1:** {p1}")
    if pd.notna(p2) and str(p2).strip():
        st.markdown(f"**Paso 2:** {p2}")
    if (pd.isna(p2) or not str(p2).strip()):
        st.caption("La base original no define un segundo paso para esta entrada.")

st.markdown("#### Marcadores normalizados autorizados")
marker_list = split_items(row.get("Marcadores_normalizados", ""))
if marker_list:
    st.write(" · ".join(f"`{m}`" for m in marker_list))
else:
    st.write("—")

st.subheader("5. Primers concretos disponibles en el catálogo")
panels = get_primer_panels(primers, row)
if not panels:
    st.warning("No hay un par de primers con secuencia que pueda asignarse de forma segura a este taxón usando las reglas actuales. No se propone una secuencia por analogía.")
else:
    for panel_id, applicability, grp in panels:
        with st.expander(f"{panel_id} — {applicability}", expanded=True):
            st.write(f"**Marcador:** {grp.iloc[0]['Marcador_autorizado']}")
            st.write(f"**Alcance publicado:** {grp.iloc[0]['Alcance']}")
            st.write(f"**Estado:** {grp.iloc[0]['Estado_validacion_catalogo']}")
            primer_table = grp[["Primer", "Direccion", "Secuencia_5_a_3", "Pareja_mezcla", "Amplicon_reportado"]].copy()
            st.dataframe(primer_table, use_container_width=True, hide_index=True)
            ref = grp.iloc[0].get("Referencia", "")
            url = grp.iloc[0].get("URL_fuente", "")
            if pd.notna(ref) and str(ref).strip():
                st.write(f"**Fuente:** {ref}")
            if pd.notna(url) and str(url).strip():
                st.link_button("Abrir fuente", str(url))
            st.caption("La presencia de una secuencia publicada no demuestra por sí sola cobertura de todas las especies de la familia; revise el estado de validación.")

st.subheader("6. Trazabilidad y salida")
source_tax = row.get("Fuente_taxonomica", "")
if pd.notna(source_tax) and str(source_tax).strip():
    st.link_button("Abrir fuente taxonómica", str(source_tax))

report_lines = [
    f"Especie seleccionada: {row['Especie']}",
    f"Grupo: {row.get('Grupo','')}", f"Clado: {row.get('Clado','')}", f"Clase: {row.get('Clase','')}",
    f"Orden: {row.get('Orden','')}", f"Familia: {row.get('Familia','')}", f"Género: {row.get('Genero','')}",
    f"Marcadores originales: {row.get('Marcadores_originales','')}",
    f"Paso 1: {row.get('Paso_1_original','')}", f"Paso 2: {row.get('Paso_2_original','')}",
]
if panels:
    report_lines.append("Paneles con secuencia disponibles:")
    for pid, applicability, grp in panels:
        report_lines.append(f"- {pid} ({applicability})")
        for _, pr in grp.iterrows():
            report_lines.append(f"  {pr['Primer']} [{pr['Direccion']}]: {pr['Secuencia_5_a_3']}")
        report_lines.append(f"  Fuente: {grp.iloc[0].get('URL_fuente','')}")
report = "\n".join(report_lines)
st.download_button("Descargar resumen (.txt)", report, file_name="flujo_molecular.txt", mime="text/plain")

with st.expander("Controles de calidad de la base"):
    st.dataframe(qa, use_container_width=True, hide_index=True)

st.divider()
st.caption("Herramienta de apoyo a la decisión. No sustituye la validación in silico/experimental de cobertura, especificidad ni condiciones de PCR.")
