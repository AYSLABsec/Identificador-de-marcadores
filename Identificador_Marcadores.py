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
    s = s.replace("β", "beta")
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
    xls = pd.ExcelFile(path)
    base = pd.read_excel(path, sheet_name="Base_maestra")
    primers = pd.read_excel(path, sheet_name="Catalogo_partidores")
    allowed = pd.read_excel(path, sheet_name="Marcadores_permitidos")
    rules = pd.read_excel(path, sheet_name="Reglas_familia")
    qa = pd.read_excel(path, sheet_name="QA")
    if "Compatibilidad_taxon_primer" in xls.sheet_names:
        compat = pd.read_excel(path, sheet_name="Compatibilidad_taxon_primer")
    else:
        compat = pd.DataFrame()
    if "Cobertura_especie_marcador" in xls.sheet_names:
        coverage = pd.read_excel(path, sheet_name="Cobertura_especie_marcador")
    else:
        coverage = pd.DataFrame()
    return base, primers, allowed, rules, qa, compat, coverage


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
        if val in q:
            score += weight
            reasons.append(f"{field}: {row.get(field)}")
            continue
        if field == "Sinonimia":
            for syn in re.split(r"\s*/\s*|\s*;\s*", val):
                if len(syn) >= 5 and syn in q:
                    score += weight
                    reasons.append(f"Sinonimia: {syn}")
                    break
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


def get_compat_for_row(compat, taxon_row):
    if compat.empty:
        return pd.DataFrame()
    ident = taxon_row.get("ID", None)
    species = str(taxon_row.get("Especie", ""))
    if "ID" in compat.columns and pd.notna(ident):
        out = compat[compat["ID"].astype(str) == str(ident)].copy()
    else:
        out = compat[compat["Especie"].astype(str) == species].copy()
    if out.empty:
        return out
    if "Prioridad" in out.columns:
        out["Prioridad_sort"] = pd.to_numeric(out["Prioridad"], errors="coerce").fillna(99)
    else:
        out["Prioridad_sort"] = 99
    out = out.sort_values(["Tipo_recomendacion", "Marcador", "Prioridad_sort", "Panel_ID"])
    return out


def display_marker_block(marker, rows, expanded=True):
    rows = rows.copy()
    valid = rows[rows["Panel_ID"].astype(str) != "SIN_PANEL_VALIDADO"].copy()
    if valid.empty:
        first = rows.iloc[0]
        st.warning(f"{marker}: marcador recomendado/autorizado, pero sin panel validado en el catálogo.")
        if pd.notna(first.get("Motivo", None)):
            st.caption(str(first.get("Motivo")))
        return
    # Show all compatible panels, best first.
    for _, r in valid.iterrows():
        pid = r.get("Panel_ID", "")
        title = f"{marker} → {pid} · prioridad {int(r['Prioridad_sort']) if pd.notna(r['Prioridad_sort']) else '—'} · {r.get('Nivel_compatibilidad','')}"
        with st.expander(title, expanded=expanded):
            c1, c2 = st.columns([1, 2])
            with c1:
                st.write(f"**Estado:** {r.get('Estado','—')}")
                st.write(f"**Amplicón:** {r.get('Amplicon_reportado','—')}")
                st.write(f"**Motivo:** {r.get('Motivo','—')}")
            with c2:
                primer_table = pd.DataFrame([
                    {"Primer": r.get("Primer_F", ""), "Dirección": "F", "Secuencia 5′→3′": r.get("Secuencia_F_5_a_3", "")},
                    {"Primer": r.get("Primer_R", ""), "Dirección": "R", "Secuencia 5′→3′": r.get("Secuencia_R_5_a_3", "")},
                ])
                st.dataframe(primer_table, use_container_width=True, hide_index=True)
            ref = r.get("Referencia", "")
            url = r.get("URL_fuente", "")
            if pd.notna(ref) and str(ref).strip():
                st.write(f"**Fuente:** {ref}")
            if pd.notna(url) and str(url).strip():
                st.link_button("Abrir fuente", str(url))
            st.caption("La compatibilidad indica que el panel aplica según la base; aun así, la compra debe pasar por validación in silico/experimental.")


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
    base, primers, allowed, rules, qa, compat, coverage = load_book(str(db_path))
except Exception as exc:
    st.error(f"No se pudo cargar la base maestra: {exc}")
    st.stop()

with st.sidebar:
    st.success(f"{len(base)} microorganismos cargados")
    st.caption(f"{base['Orden'].nunique()} órdenes · {base['Familia'].nunique()} familias")
    if not compat.empty:
        st.caption(f"{compat['Panel_ID'].nunique()} paneles relacionados en compatibilidad")
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
    placeholder="Ej.: aislado bacteriano; sospecha de Rhizobium leguminosarum...",
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
    if pd.isna(p2) or not str(p2).strip():
        st.caption("La base original no define un segundo paso para esta entrada.")

st.markdown("#### Marcadores normalizados autorizados")
marker_list = split_items(row.get("Marcadores_normalizados", ""))
if marker_list:
    st.write(" · ".join(f"`{m}`" for m in marker_list))
else:
    st.write("—")

adds = split_items(row.get("Marcadores_adicionales_por_taxon", ""))
if adds:
    st.markdown("#### Opciones adicionales autorizadas por taxón")
    st.write(" · ".join(f"`{m}`" for m in adds))
    st.caption("Estos marcadores estaban permitidos en el Excel original, pero se agregan como opción por compatibilidad taxonómica; no reemplazan la recomendación literal original.")

st.subheader("5. Cobertura marcador → primer")
row_compat = get_compat_for_row(compat, row)
if row_compat.empty:
    st.warning("La base no contiene una tabla Compatibilidad_taxon_primer. Actualiza a la Base Maestra V3 para evitar omisiones.")
else:
    original = row_compat[row_compat["Tipo_recomendacion"].astype(str) == "Original del Excel"].copy()
    additional = row_compat[row_compat["Tipo_recomendacion"].astype(str) == "Adicional por taxón"].copy()

    st.markdown("### 5.1 Marcadores originales")
    if original.empty:
        st.info("No hay marcadores originales normalizados para esta entrada.")
    else:
        for marker in original["Marcador"].drop_duplicates().tolist():
            display_marker_block(marker, original[original["Marcador"] == marker], expanded=True)

    st.markdown("### 5.2 Opciones adicionales por taxón")
    if additional.empty:
        st.caption("No hay marcadores adicionales por taxón para este microorganismo.")
    else:
        for marker in additional["Marcador"].drop_duplicates().tolist():
            display_marker_block(marker, additional[additional["Marcador"] == marker], expanded=False)

    st.markdown("### 5.3 Tabla de compatibilidad completa")
    cols = ["Marcador", "Tipo_recomendacion", "Panel_ID", "Prioridad", "Nivel_compatibilidad", "Estado", "Amplicon_reportado"]
    st.dataframe(row_compat[cols], use_container_width=True, hide_index=True)

st.subheader("6. Trazabilidad y salida")
source_tax = row.get("Fuente_taxonomica", "")
if pd.notna(source_tax) and str(source_tax).strip():
    st.link_button("Abrir fuente taxonómica", str(source_tax))

report_lines = [
    f"Especie seleccionada: {row['Especie']}",
    f"Grupo: {row.get('Grupo','')}", f"Clado: {row.get('Clado','')}", f"Clase: {row.get('Clase','')}",
    f"Orden: {row.get('Orden','')}", f"Familia: {row.get('Familia','')}", f"Género: {row.get('Genero','')}",
    f"Marcadores originales: {row.get('Marcadores_originales','')}",
    f"Marcadores adicionales por taxón: {row.get('Marcadores_adicionales_por_taxon','')}",
    f"Paso 1: {row.get('Paso_1_original','')}", f"Paso 2: {row.get('Paso_2_original','')}",
]
if not row_compat.empty:
    report_lines.append("Compatibilidad marcador-primer:")
    for _, r in row_compat.iterrows():
        report_lines.append(f"- {r['Marcador']} [{r['Tipo_recomendacion']}]: {r['Panel_ID']} prioridad {r.get('Prioridad','')}")
        if str(r.get('Panel_ID','')) != 'SIN_PANEL_VALIDADO':
            report_lines.append(f"  F {r.get('Primer_F','')}: {r.get('Secuencia_F_5_a_3','')}")
            report_lines.append(f"  R {r.get('Primer_R','')}: {r.get('Secuencia_R_5_a_3','')}")
            report_lines.append(f"  Fuente: {r.get('URL_fuente','')}")
report = "\n".join(report_lines)
st.download_button("Descargar resumen (.txt)", report, file_name="flujo_molecular.txt", mime="text/plain")

with st.expander("Controles de calidad de la base"):
    st.dataframe(qa, use_container_width=True, hide_index=True)

st.divider()
st.caption("Herramienta de apoyo a la decisión. No sustituye la validación in silico/experimental de cobertura, especificidad ni condiciones de PCR.")
