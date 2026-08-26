import re
import unicodedata
import json
import time
import hashlib
import urllib.parse
import xml.etree.ElementTree as ET
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import regex as fuzzy_regex

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "base_maestra.xlsx"
NCBI_BLAST_URL = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PRIMER_BLAST_URL = "https://www.ncbi.nlm.nih.gov/tools/primer-blast/index.cgi"
CACHE_DIR = Path(os.environ.get("ASISTENTE_MOLECULAR_CACHE_DIR", str(APP_DIR / ".primer_validation_cache"))).expanduser()
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_SCHEMA_VERSION = "10.8-genome-deep-validation-v1"

st.set_page_config(page_title="Asistente molecular Nanopore", page_icon="🧬", layout="wide")

st.markdown(
    """
    <style>
    .badge {display:inline-block; padding:0.22rem 0.55rem; border-radius:0.45rem; font-weight:800;
            font-size:0.82rem; margin-right:0.35rem; margin-bottom:0.25rem;}
    .badge-lab {background:#d9f7df; color:#116329; border:1px solid #73c686;}
    .badge-sag {background:#dcecff; color:#0b4f8a; border:1px solid #7eb3e6;}
    .badge-both {background:#eee3ff; color:#5b2494; border:1px solid #b695db;}
    .badge-warn {background:#fff1cc; color:#7b5300; border:1px solid #e3bd58;}
    .difficulty-high {padding:.75rem 1rem; border-radius:.6rem; background:#fff1cc; color:#6b4800; border:1px solid #e3bd58; font-weight:700;}
    .difficulty-veryhigh {padding:.75rem 1rem; border-radius:.6rem; background:#ffe1e1; color:#8b1111; border:1px solid #e08a8a; font-weight:800;}
    .difficulty-standard {padding:.6rem .9rem; border-radius:.6rem; background:#e8f6ea; color:#1f6a2a; border:1px solid #8bc796; font-weight:700;}
    .metricbox {padding:0.55rem 0.7rem; border:1px solid rgba(128,128,128,.25); border-radius:.55rem; min-height:5.1rem;}
    .smallmuted {font-size:.85rem; opacity:.76;}
    </style>
    """,
    unsafe_allow_html=True,
)


def norm_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("β", "beta")
    s = re.sub(r"[^a-z0-9+./ -]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_seq(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = re.sub(r"<[^>]+>", "", str(value))
    return re.sub(r"[^A-Za-z]", "", s).upper()


def split_items(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    parts = re.split(r"\s*;\s*|\s*,\s*", str(value))
    return [p.strip() for p in parts if p and p.strip()]


def truthy_si(value):
    return norm_text(value) in {"si", "sí", "yes", "true", "1"}


def val_or_dash(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in {"", "nan", "None"}:
        return "—"
    return str(v)


def fmt_temp(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    if not s or s.lower() == "nan" or s.lower() == "no localizada":
        return "—"
    try:
        return f"{float(v):.1f} °C"
    except Exception:
        return f"{s} °C" if "°" not in s and any(ch.isdigit() for ch in s) else s


@st.cache_data(show_spinner=False)
def load_book(path_str):
    path = Path(path_str)
    xls = pd.ExcelFile(path)
    def read(name):
        return pd.read_excel(path, sheet_name=name) if name in xls.sheet_names else pd.DataFrame()
    return {
        "base": read("Base_maestra"),
        "primers": read("Catalogo_partidores"),
        "allowed": read("Marcadores_permitidos"),
        "rules": read("Reglas_familia"),
        "qa": read("QA"),
        "compat": read("Compatibilidad_taxon_primer"),
        "coverage": read("Cobertura_especie_marcador"),
        "sag": read("Partidores_SAG"),
        "inventory": read("Inventario_lab_partidores"),
        "temp_sources": read("Fuentes_temperatura"),
        "difficulty": read("Dificultad_identificacion"),
        "reinforcement": read("Cobertura_refuerzo_dificultad"),
    }



def prepare_blast_seq(value):
    """Normalize a primer for NCBI BLAST. Inosine/unknown symbols become N."""
    seq = norm_seq(value)
    allowed = set("ACGTRYSWKMBDHVN")
    return "".join(("N" if b == "I" or b not in allowed else b) for b in seq)




IUPAC_BASES = {
    "A": "A", "C": "C", "G": "G", "T": "T",
    "R": "AG", "Y": "CT", "S": "GC", "W": "AT",
    "K": "GT", "M": "AC", "B": "CGT", "D": "AGT",
    "H": "ACT", "V": "ACG", "N": "ACGT", "I": "ACGT",
}
IUPAC_COMPLEMENT = {
    "A":"T", "T":"A", "C":"G", "G":"C", "R":"Y", "Y":"R",
    "S":"S", "W":"W", "K":"M", "M":"K", "B":"V", "V":"B",
    "D":"H", "H":"D", "N":"N", "I":"N",
}
IUPAC_MULTIPLICITY = {k: len(v) for k, v in IUPAC_BASES.items()}

# NCBI does not use one canonical label for every locus. These aliases are
# deliberately redundant so that locus-specific GenBank records are preferred
# before falling back to genomic records.
LOCUS_ALIASES = {
    "TEF1": ["TEF1", "TEF1-alpha", "TEF1 alpha", "EF1-alpha", "EF-1 alpha", "elongation factor 1-alpha", "translation elongation factor 1-alpha"],
    "RPB1": ["RPB1", "RNA polymerase II largest subunit", "RNA polymerase II subunit 1"],
    "RPB2": ["RPB2", "RNA polymerase II second largest subunit", "RNA polymerase II subunit 2"],
    "TUB2": ["TUB2", "BenA", "beta-tubulin", "beta tubulin"],
    "CAL": ["CAL", "CaM", "calmodulin"],
    "ACT1": ["ACT1", "actin"],
    "GAPDH": ["GAPDH", "glyceraldehyde-3-phosphate dehydrogenase"],
    "ITS": ["ITS", "internal transcribed spacer", "ITS1", "ITS2"],
    "18S": ["18S", "18S ribosomal RNA", "small subunit ribosomal RNA", "SSU rRNA"],
    "28S": ["28S", "28S ribosomal RNA", "large subunit ribosomal RNA", "LSU rRNA"],
    "LSU": ["LSU", "large subunit ribosomal RNA", "28S ribosomal RNA"],
    "16S": ["16S", "16S ribosomal RNA"],
    "GYRA": ["gyrA", "DNA gyrase subunit A"],
    "GYRB": ["gyrB", "DNA gyrase subunit B"],
    "RPOB": ["rpoB", "RNA polymerase beta subunit", "DNA-directed RNA polymerase subunit beta"],
    "RPOD": ["rpoD", "RNA polymerase sigma factor", "sigma factor 70"],
    "RECA": ["recA", "recombinase A"],
    "ATPD": ["atpD", "ATP synthase subunit beta"],
    "GLNII": ["glnII", "glutamine synthetase II"],
    "PHES": ["pheS", "phenylalanyl-tRNA synthetase alpha subunit"],
    "TUF": ["tuf", "tufA", "elongation factor Tu"],
    "TUFA": ["tufA", "elongation factor Tu"],
    "MDH": ["mdh", "malate dehydrogenase"],
    "INFB": ["infB", "translation initiation factor IF-2", "translation initiation factor 2"],
    "TRPB": ["trpB", "tryptophan synthase beta chain"],
    "GROEL": ["groEL", "hsp60", "cpn60", "chaperonin GroEL"],
    "HSP60": ["hsp60", "cpn60", "groEL", "60 kDa chaperonin"],
    "RBCL": ["rbcL", "ribulose-1,5-bisphosphate carboxylase/oxygenase large subunit"],
    "RADA": ["radA", "DNA repair and recombination protein RadA"],
    "ATPB": ["atpB", "ATP synthase subunit A", "ATP synthase subunit beta"],
}


def canonical_marker_key(marker):
    m = re.sub(r"[^A-Za-z0-9]+", "", str(marker or "")).upper()
    if "TEF1" in m or "EF1" in m:
        return "TEF1"
    if "RPB1" in m:
        return "RPB1"
    if "RPB2" in m:
        return "RPB2"
    if "TUB2" in m or "BENA" in m or "BETATUB" in m:
        return "TUB2"
    if m in {"CAL", "CAM", "CALMODULIN"}:
        return "CAL"
    if "ACT1" in m or m == "ACTIN":
        return "ACT1"
    if "GAPDH" in m:
        return "GAPDH"
    if "ITS" in m:
        return "ITS"
    if "18S" in m or "SSU" in m:
        return "18S"
    if "28S" in m or "LSU" in m:
        return "28S"
    for key in ["16S","GYRA","GYRB","RPOB","RPOD","RECA","ATPD","GLNII","PHES","TUFA","TUF","MDH","INFB","TRPB","GROEL","HSP60","RBCL","RADA","ATPB"]:
        if key in m:
            return key
    return m


def locus_aliases(marker):
    key = canonical_marker_key(marker)
    aliases = list(LOCUS_ALIASES.get(key, []))
    raw = str(marker or "").strip()
    if raw and raw.lower() not in {a.lower() for a in aliases}:
        aliases.insert(0, raw)
    # Stable de-duplication
    out, seen = [], set()
    for a in aliases:
        aa = str(a).strip()
        if aa and aa.lower() not in seen:
            seen.add(aa.lower()); out.append(aa)
    return out


def primer_degeneracy(seq):
    seq = norm_seq(seq)
    ambiguous = [b for b in seq if IUPAC_MULTIPLICITY.get(b, 1) > 1]
    variants = 1
    for b in seq:
        variants *= IUPAC_MULTIPLICITY.get(b, 1)
    return {"is_degenerate": bool(ambiguous), "ambiguous_positions": len(ambiguous), "variants": variants}


def reverse_complement_iupac(seq):
    seq = norm_seq(seq)
    return "".join(IUPAC_COMPLEMENT.get(b, "N") for b in reversed(seq))


def iupac_regex_pattern(seq):
    seq = norm_seq(seq)
    chunks = []
    for b in seq:
        bases = IUPAC_BASES.get(b, "ACGT")
        chunks.append(bases if len(bases) == 1 else f"[{bases}]")
    return "".join(chunks)


def find_iupac_hits(sequence, primer, max_mismatches=4, max_hits=250):
    """Find primer-compatible sites allowing substitutions only; IUPAC codes are honored."""
    sequence = re.sub(r"[^ACGTN]", "N", str(sequence).upper())
    pattern = iupac_regex_pattern(primer)
    # BESTMATCH minimizes substitutions. No insertions/deletions are allowed for primer binding.
    fuzzy = fuzzy_regex.compile(f"(?b)(?:{pattern}){{s<={int(max_mismatches)}}}", fuzzy_regex.IGNORECASE)
    out = []
    for m in fuzzy.finditer(sequence, overlapped=True):
        subs, ins, dels = m.fuzzy_counts
        out.append({"start": m.start()+1, "end": m.end(), "mismatches": int(subs), "matched": m.group(0)})
        if len(out) >= max_hits:
            break
    return out


def parse_fasta(text):
    records = []
    header = None
    seq_parts = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header is not None:
                records.append((header, "".join(seq_parts).upper()))
            header = line[1:].strip()
            seq_parts = []
        elif header is not None:
            seq_parts.append(line.strip())
    if header is not None:
        records.append((header, "".join(seq_parts).upper()))
    return records


def ncbi_params(email="", api_key=""):
    p = {"tool": "AsistenteMolecularNanopore"}
    if email:
        p["email"] = email
    if api_key:
        p["api_key"] = api_key
    return p


def esearch_nucleotide(term, retmax=5, email="", api_key="", timeout=30):
    params = {"db":"nuccore", "term":term, "retmode":"json", "retmax":str(int(retmax)), **ncbi_params(email, api_key)}
    r = requests.get(f"{NCBI_EUTILS}/esearch.fcgi", params=params, timeout=timeout, headers={"User-Agent":"AsistenteMolecularNanopore/10.0"})
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])


def efetch_fasta(ids, email="", api_key="", timeout=90):
    if not ids:
        return []
    params = {"db":"nuccore", "id":",".join(ids), "rettype":"fasta", "retmode":"text", **ncbi_params(email, api_key)}
    r = requests.get(f"{NCBI_EUTILS}/efetch.fcgi", params=params, timeout=timeout, headers={"User-Agent":"AsistenteMolecularNanopore/10.0"})
    r.raise_for_status()
    return parse_fasta(r.text)


def fetch_transient_references(species, marker="", email="", api_key="", records_per_species=20, genomic_fallback_records=3):
    """Retrieve temporary NCBI references with locus-aware searching.

    Locus-specific records are preferred. Only if none are found do we fall
    back to a small genomic sample. The return metadata tells the caller
    whether absence of a PCR product can be interpreted as evidence against
    the primer pair or must remain inconclusive.
    """
    aliases = locus_aliases(marker)
    search_log = []

    # 1) Strong locus-specific query, first Title then All Fields. This catches
    # GenBank naming differences such as TEF1 / EF1-alpha / elongation factor 1-alpha.
    if aliases:
        title_clause = " OR ".join(f'"{a}"[Title]' for a in aliases)
        broad_clause = " OR ".join(f'"{a}"[All Fields]' for a in aliases)
        locus_queries = [
            (f'"{species}"[Organism] AND ({title_clause})', "locus_specific_title", True),
            # All Fields is intentionally treated as probable, not definitive:
            # the term may occur in linked metadata rather than the sequence title.
            (f'"{species}"[Organism] AND ({broad_clause})', "locus_probable_allfields", False),
        ]
        for q, retrieval_mode, locus_confirmed in locus_queries:
            ids = esearch_nucleotide(q, retmax=records_per_species, email=email, api_key=api_key)
            search_log.append({"query": q, "hits": len(ids), "mode": retrieval_mode})
            if ids:
                records = efetch_fasta(ids, email=email, api_key=api_key)
                if records:
                    return records, {
                        "used_query": q, "retrieval_mode": retrieval_mode, "locus_confirmed": locus_confirmed,
                        "aliases": aliases, "search_log": search_log, "record_count": len(records),
                    }
            time.sleep(0.12 if api_key else 0.35)

    # 2) Genomic fallback. Keep deliberately small to avoid downloading large
    # eukaryotic genomes. A negative result here is NOT treated as 0 % coverage.
    fallback_queries = [
        f'"{species}"[Organism] AND (refseq[filter] OR "complete genome"[Title] OR chromosome[Title])',
        f'"{species}"[Organism] AND biomol_genomic[PROP]',
    ]
    for q in fallback_queries:
        ids = esearch_nucleotide(q, retmax=genomic_fallback_records, email=email, api_key=api_key)
        search_log.append({"query": q, "hits": len(ids), "mode": "genomic_fallback"})
        if ids:
            records = efetch_fasta(ids, email=email, api_key=api_key)
            if records:
                return records, {
                    "used_query": q, "retrieval_mode": "genomic_fallback", "locus_confirmed": False,
                    "aliases": aliases, "search_log": search_log, "record_count": len(records),
                }
        time.sleep(0.12 if api_key else 0.35)

    return [], {
        "used_query": "", "retrieval_mode": "none", "locus_confirmed": False,
        "aliases": aliases, "search_log": search_log, "record_count": 0,
    }



def fetch_deep_genomic_references(species, email="", api_key="", max_records=12):
    """Retrieve temporary genomic references for a deeper primer-pair check.

    Prefer complete/chromosomal RefSeq/GenBank records. If these are absent, a
    small genomic fallback is returned but is explicitly marked as incomplete,
    so absence of a PCR product is not interpreted as definitive failure.
    """
    search_log = []
    queries = [
        (f'"{species}"[Organism] AND biomol_genomic[PROP] AND (refseq[filter] OR "complete genome"[Title] OR chromosome[Title])', "complete_or_chromosome", True),
        (f'"{species}"[Organism] AND biomol_genomic[PROP]', "genomic_fallback", False),
    ]
    for q, mode, genome_complete in queries:
        ids = esearch_nucleotide(q, retmax=max_records, email=email, api_key=api_key, timeout=45)
        search_log.append({"query": q, "hits": len(ids), "mode": mode})
        if ids:
            records = efetch_fasta(ids, email=email, api_key=api_key, timeout=180)
            if records:
                return records, {
                    "used_query": q,
                    "retrieval_mode": mode,
                    "genome_complete": genome_complete,
                    "search_log": search_log,
                    "record_count": len(records),
                    "total_bases": sum(len(seq) for _, seq in records),
                }
        time.sleep(0.12 if api_key else 0.35)
    return [], {
        "used_query": "", "retrieval_mode": "none", "genome_complete": False,
        "search_log": search_log, "record_count": 0, "total_bases": 0,
    }


def run_deep_genome_validation(seq_f, seq_r, marker, base, row, scope, email="", api_key="", product_min=80, product_max=3000, max_mismatches=4, max_records_per_species=12, max_species=10):
    """Second-stage validation on temporary genomic references.

    This is invoked only on demand after a locus-level result is inconclusive.
    No persistent genome database is created.
    """
    targets, taxon = target_species_for_scope(base, row, scope)
    sampled = targets[:max_species]
    truncated = len(targets) > len(sampled)
    covered = []
    evaluable = []
    species_without_refs = []
    examples = []
    retrieval_details = {}
    total_records = total_bases = 0
    f_hits_total = r_hits_total = paired_accessions = 0
    products_all = []

    for species in sampled:
        records, meta = fetch_deep_genomic_references(
            species, email=email, api_key=api_key, max_records=max_records_per_species
        )
        retrieval_details[species] = meta
        if not records:
            species_without_refs.append(species)
            continue
        total_records += len(records)
        total_bases += sum(len(seq) for _, seq in records)
        species_product = False
        species_f_hits = species_r_hits = 0
        species_both = 0
        diagnostics = []
        for header, sequence in records:
            products, fh, rh = pair_iupac_sites(
                sequence, seq_f, seq_r, max_mismatches=max_mismatches,
                product_min=product_min, product_max=product_max,
            )
            species_f_hits += fh; species_r_hits += rh
            f_hits_total += fh; r_hits_total += rh
            if fh > 0 and rh > 0:
                species_both += 1
            diagnostics.append({
                "species": species,
                "accession": header.split()[0],
                "sequence_length": len(sequence),
                "f_hits": fh,
                "r_hits": rh,
                "both_sites_observed": bool(fh > 0 and rh > 0),
                "product_observed": bool(products),
                "definition": header[:180],
                "retrieval_mode": meta.get("retrieval_mode", ""),
            })
            if products:
                species_product = True
                paired_accessions += 1
                best = products[0]
                products_all.append(best["product_bp"])
                examples.append({
                    "species": species, "accession": header.split()[0],
                    "product_bp": best["product_bp"],
                    "f_mismatches": best["f_mismatches"],
                    "r_mismatches": best["r_mismatches"],
                    "orientation": best["orientation"],
                    "definition": header[:180],
                    "retrieval_mode": meta.get("retrieval_mode", ""),
                })
        meta["species_forward_hits"] = species_f_hits
        meta["species_reverse_hits"] = species_r_hits
        meta["records_with_both_primer_sites"] = species_both
        meta["record_diagnostics"] = diagnostics
        if species_product:
            covered.append(species)
            evaluable.append(species)
        elif meta.get("genome_complete"):
            # A complete/chromosomal genomic representation is sufficiently strong
            # to interpret absence of a compatible primer pair as an in-silico negative.
            evaluable.append(species)
        time.sleep(0.10 if api_key else 0.34)

    evaluable = list(dict.fromkeys(evaluable))
    if not (set(sampled) - set(species_without_refs)):
        status = "sin_referencias_genomicas"
    elif covered:
        status = "producto_genomico_observado"
    elif evaluable:
        status = "sin_producto_genoma_completo"
    else:
        status = "genoma_no_concluyente"

    return {
        "validation_method": "IUPAC sobre referencias genómicas NCBI temporales (profundización)",
        "deep_genome_validation": True,
        "scope": scope, "taxon": taxon, "target_species": targets,
        "sampled_species": sampled, "sample_truncated": truncated,
        "covered_species": covered,
        "species_without_references": species_without_refs,
        "coverage_species_denominator": evaluable,
        "coverage_pct": (100.0 * len(covered) / len(evaluable)) if evaluable else None,
        "coverage_denominator": "especies con representación genómica completa/cromosómica o producto observado",
        "reference_records": total_records,
        "reference_bases": total_bases,
        "paired_accessions": paired_accessions,
        "forward_hits": f_hits_total, "reverse_hits": r_hits_total,
        "shared_accessions": paired_accessions,
        "product_min_observed": min(products_all) if products_all else None,
        "product_max_observed": max(products_all) if products_all else None,
        "paired_examples": examples[:100],
        "primer_f": norm_seq(seq_f), "primer_r": norm_seq(seq_r), "marker": marker,
        "product_min": product_min, "product_max": product_max,
        "max_mismatches": max_mismatches,
        "retrieval_details": retrieval_details,
        "interpretation_status": status,
    }

def pair_iupac_sites(sequence, seq_f, seq_r, max_mismatches=4, product_min=80, product_max=3000):
    """Search both possible genomic orientations and return compatible PCR products."""
    f_plus = find_iupac_hits(sequence, seq_f, max_mismatches=max_mismatches)
    r_plus = find_iupac_hits(sequence, reverse_complement_iupac(seq_r), max_mismatches=max_mismatches)
    r_minus = find_iupac_hits(sequence, seq_r, max_mismatches=max_mismatches)
    f_minus = find_iupac_hits(sequence, reverse_complement_iupac(seq_f), max_mismatches=max_mismatches)
    products = []
    for f in f_plus:
        for r in r_plus:
            if f["start"] >= r["start"]:
                continue
            bp = r["end"] - f["start"] + 1
            if product_min <= bp <= product_max:
                products.append({"product_bp":bp, "f_mismatches":f["mismatches"], "r_mismatches":r["mismatches"], "orientation":"+"})
    for r in r_minus:
        for f in f_minus:
            if r["start"] >= f["start"]:
                continue
            bp = f["end"] - r["start"] + 1
            if product_min <= bp <= product_max:
                products.append({"product_bp":bp, "f_mismatches":f["mismatches"], "r_mismatches":r["mismatches"], "orientation":"-"})
    products.sort(key=lambda x: (x["f_mismatches"] + x["r_mismatches"], abs(x["product_bp"] - (product_min+product_max)/2)))
    return products, len(f_plus) + len(f_minus), len(r_plus) + len(r_minus)


def run_iupac_reference_validation(seq_f, seq_r, marker, base, row, scope, email="", api_key="", product_min=80, product_max=3000, max_mismatches=4, records_per_species=20, max_species=25):
    targets, taxon = target_species_for_scope(base, row, scope)
    sampled = targets[:max_species]
    truncated = len(targets) > len(sampled)
    covered = []
    species_with_refs = []
    species_without_refs = []
    species_locus_confirmed = []
    species_locus_unconfirmed = []
    species_definitively_evaluable = []
    examples = []
    total_records = 0
    f_hits_total = 0
    r_hits_total = 0
    paired_accessions = 0
    products_all = []
    retrieval_details = {}

    for species in sampled:
        records, meta = fetch_transient_references(
            species, marker=marker, email=email, api_key=api_key,
            records_per_species=records_per_species, genomic_fallback_records=3,
        )
        retrieval_details[species] = meta
        if not records:
            species_without_refs.append(species)
            continue
        species_with_refs.append(species)
        if meta.get("locus_confirmed"):
            species_locus_confirmed.append(species)
        else:
            species_locus_unconfirmed.append(species)
        total_records += len(records)
        species_product = False
        species_f_hits = species_r_hits = 0
        species_records_with_both_sites = 0
        species_records_one_sided = 0
        species_record_diagnostics = []
        for header, sequence in records:
            products, fh, rh = pair_iupac_sites(
                sequence, seq_f, seq_r, max_mismatches=max_mismatches,
                product_min=product_min, product_max=product_max,
            )
            species_f_hits += fh; species_r_hits += rh
            f_hits_total += fh; r_hits_total += rh
            if fh > 0 and rh > 0:
                species_records_with_both_sites += 1
            elif (fh > 0) != (rh > 0):
                species_records_one_sided += 1
            species_record_diagnostics.append({
                "species": species,
                "accession": header.split()[0],
                "sequence_length": len(sequence),
                "f_hits": fh,
                "r_hits": rh,
                "both_sites_observed": bool(fh > 0 and rh > 0),
                "one_sided_only": bool((fh > 0) != (rh > 0)),
                "product_observed": bool(products),
                "definition": header[:180],
                "retrieval_mode": meta.get("retrieval_mode", ""),
            })
            if products:
                species_product = True
                paired_accessions += 1
                best = products[0]
                products_all.append(best["product_bp"])
                examples.append({
                    "species": species, "accession": header.split()[0], "product_bp": best["product_bp"],
                    "f_mismatches": best["f_mismatches"], "r_mismatches": best["r_mismatches"],
                    "orientation": best["orientation"], "definition": header[:180],
                    "retrieval_mode": meta.get("retrieval_mode", ""),
                    "locus_confirmed_by_query": bool(meta.get("locus_confirmed")),
                })
        meta["species_forward_hits"] = species_f_hits
        meta["species_reverse_hits"] = species_r_hits
        meta["records_with_both_primer_sites"] = species_records_with_both_sites
        meta["records_one_sided"] = species_records_one_sided
        meta["record_diagnostics"] = species_record_diagnostics
        if species_product:
            covered.append(species)
            # A product itself confirms that the relevant primer-binding region is present.
            if species not in species_definitively_evaluable:
                species_definitively_evaluable.append(species)
        elif meta.get("locus_confirmed") and species_records_with_both_sites > 0:
            # A negative is considered interpretable only if at least one locus-specific
            # record contains detectable sites for BOTH primers. If only one side is
            # represented, the GenBank record may simply be a partial locus fragment.
            species_definitively_evaluable.append(species)
        time.sleep(0.10 if api_key else 0.34)

    # Only locus-confirmed species (or species with an actual product) belong in
    # the denominator. Genomic fallback records with no product are inconclusive.
    denom_species = list(dict.fromkeys(species_definitively_evaluable))
    deg_f = primer_degeneracy(seq_f)
    deg_r = primer_degeneracy(seq_r)

    partial_species = []
    for sp, md in retrieval_details.items():
        if md.get("locus_confirmed") and md.get("record_count", 0) > 0 and md.get("records_with_both_primer_sites", 0) == 0:
            # Especially important for partial gene submissions: a forward hit with no
            # reverse site (or vice versa) is not evidence that the primer pair fails.
            partial_species.append(sp)

    if not species_with_refs:
        status = "sin_referencias"
    elif covered:
        status = "producto_observado"
    elif denom_species:
        status = "sin_producto_locus_completo"
    elif partial_species:
        status = "referencias_parciales_no_concluyente"
    else:
        status = "locus_no_confirmado"

    return {
        "validation_method":"IUPAC sobre referencias NCBI temporales (búsqueda locus-aware)",
        "scope":scope, "taxon":taxon, "target_species":targets, "sampled_species":sampled,
        "covered_species":covered, "species_with_references":species_with_refs,
        "species_without_references":species_without_refs,
        "species_locus_confirmed":species_locus_confirmed,
        "species_locus_unconfirmed":species_locus_unconfirmed,
        "species_partial_references":partial_species,
        "coverage_species_denominator":denom_species,
        "coverage_pct": (100.0*len(covered)/len(denom_species)) if denom_species else None,
        "coverage_denominator":"especies con locus confirmado o producto observado", "sample_truncated":truncated,
        "reference_records":total_records, "paired_accessions":paired_accessions,
        "forward_hits":f_hits_total, "reverse_hits":r_hits_total, "shared_accessions":paired_accessions,
        "product_min_observed":min(products_all) if products_all else None,
        "product_max_observed":max(products_all) if products_all else None,
        "paired_examples":examples[:100], "primer_f":norm_seq(seq_f), "primer_r":norm_seq(seq_r),
        "degeneracy_forward":deg_f, "degeneracy_reverse":deg_r, "marker":marker,
        "marker_aliases_used":locus_aliases(marker),
        "product_min":product_min, "product_max":product_max, "max_mismatches":max_mismatches,
        "retrieval_details":retrieval_details,
        "interpretation_status": status,
    }


def cache_key(payload):
    # Include the validation-schema version so results produced by older
    # taxonomic algorithms are never silently reused after an update.
    enriched = dict(payload)
    enriched["_cache_schema"] = CACHE_SCHEMA_VERSION
    raw = json.dumps(enriched, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_validation_cache(payload, max_age_days=30):
    path = CACHE_DIR / f"{cache_key(payload)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("cache_schema") != CACHE_SCHEMA_VERSION:
            return None
        ts = datetime.fromisoformat(data.get("cached_at"))
        age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
        if age_days <= max_age_days:
            data["cache_age_days"] = age_days
            return data
    except Exception:
        return None
    return None


def save_validation_cache(payload, result):
    out = dict(result)
    out["cached_at"] = datetime.now(timezone.utc).isoformat()
    out["cache_schema"] = CACHE_SCHEMA_VERSION
    path = CACHE_DIR / f"{cache_key(payload)}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def clear_legacy_cache_files():
    """Remove JSON caches that predate the current interpretation schema."""
    removed = 0
    try:
        for path in CACHE_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("cache_schema") != CACHE_SCHEMA_VERSION:
                    path.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                path.unlink(missing_ok=True)
                removed += 1
    except Exception:
        pass
    return removed


def primer_blast_link(seq_f, seq_r, organism, amp_min=80, amp_max=3000):
    params = {
        "PRIMER_LEFT_INPUT": prepare_blast_seq(seq_f),
        "PRIMER_RIGHT_INPUT": prepare_blast_seq(seq_r),
        "ORGANISM": organism,
        "PRIMER_PRODUCT_MIN": str(int(amp_min)),
        "PRIMER_PRODUCT_MAX": str(int(amp_max)),
        "PRIMER_SPECIFICITY_DATABASE": "nt",
        "SEARCH_SPECIFIC_PRIMER": "on",
    }
    return PRIMER_BLAST_URL + "?" + urllib.parse.urlencode(params)


def submit_blast_short(seq, taxon, email="", hitlist_size=1000, timeout=45):
    seq = prepare_blast_seq(seq)
    if not seq:
        raise ValueError("Secuencia de primer vacía.")
    data = {
        "CMD": "Put",
        "PROGRAM": "blastn",
        "DATABASE": "nt",
        "QUERY": seq,
        "ENTREZ_QUERY": f'{taxon}[Organism]' if taxon else "",
        "HITLIST_SIZE": str(int(hitlist_size)),
        "EXPECT": "1000",
        "WORD_SIZE": "7",
        "FILTER": "F",
        "TOOL": "AsistenteMolecularNanopore",
    }
    if email:
        data["EMAIL"] = email
    r = requests.post(NCBI_BLAST_URL, data=data, timeout=timeout, headers={"User-Agent": "AsistenteMolecularNanopore/8.0"})
    r.raise_for_status()
    rid_m = re.search(r"RID\s*=\s*([A-Z0-9-]+)", r.text)
    rtoe_m = re.search(r"RTOE\s*=\s*(\d+)", r.text)
    if not rid_m:
        msg = re.sub(r"\s+", " ", r.text[:500])
        raise RuntimeError(f"NCBI no devolvió RID. Respuesta: {msg}")
    return rid_m.group(1), int(rtoe_m.group(1)) if rtoe_m else 5


def wait_blast(rid, max_wait=240, poll_seconds=5, timeout=30):
    start = time.time()
    while time.time() - start < max_wait:
        params = {"CMD": "Get", "RID": rid, "FORMAT_OBJECT": "SearchInfo"}
        r = requests.get(NCBI_BLAST_URL, params=params, timeout=timeout, headers={"User-Agent": "AsistenteMolecularNanopore/8.0"})
        r.raise_for_status()
        m = re.search(r"Status=(\w+)", r.text)
        status = m.group(1) if m else "UNKNOWN"
        if status == "READY":
            if "ThereAreHits=yes" in r.text:
                return True
            return False
        if status in {"FAILED", "UNKNOWN"}:
            raise RuntimeError(f"BLAST terminó con estado {status} para RID {rid}.")
        time.sleep(poll_seconds)
    raise TimeoutError(f"BLAST no terminó en {max_wait} segundos.")


def fetch_blast_xml(rid, timeout=60):
    params = {
        "CMD": "Get", "RID": rid, "FORMAT_TYPE": "XML",
        "DESCRIPTIONS": "1000", "ALIGNMENTS": "1000",
    }
    r = requests.get(NCBI_BLAST_URL, params=params, timeout=timeout, headers={"User-Agent": "AsistenteMolecularNanopore/8.0"})
    r.raise_for_status()
    return r.text


def parse_blast_hits(xml_text, query_len, max_mismatches=4, min_query_coverage=0.80):
    if not xml_text.strip():
        return []
    root = ET.fromstring(xml_text)
    hits = []
    for hit in root.findall(".//Hit"):
        accession = hit.findtext("Hit_accession") or hit.findtext("Hit_id") or ""
        hit_def = hit.findtext("Hit_def") or ""
        organisms = re.findall(r"\[([^\[\]]+)\]", hit_def)
        for hsp in hit.findall(".//Hsp"):
            try:
                h_from = int(hsp.findtext("Hsp_hit-from"))
                h_to = int(hsp.findtext("Hsp_hit-to"))
                q_from = int(hsp.findtext("Hsp_query-from"))
                q_to = int(hsp.findtext("Hsp_query-to"))
                identities = int(hsp.findtext("Hsp_identity"))
                align_len = int(hsp.findtext("Hsp_align-len"))
            except (TypeError, ValueError):
                continue
            query_aligned = abs(q_to - q_from) + 1
            coverage = query_aligned / max(query_len, 1)
            mismatches = max(0, query_len - identities)
            if coverage < min_query_coverage or mismatches > max_mismatches:
                continue
            hits.append({
                "accession": accession, "definition": hit_def, "organisms": organisms,
                "start": min(h_from, h_to), "end": max(h_from, h_to),
                "strand": "+" if h_from <= h_to else "-",
                "identities": identities, "align_len": align_len,
                "query_coverage": coverage, "mismatches": mismatches,
                "identity_pct": 100.0 * identities / max(query_len, 1),
            })
    return hits


def pair_primer_hits(f_hits, r_hits, product_min=80, product_max=3000):
    by_f, by_r = {}, {}
    for h in f_hits:
        by_f.setdefault(h["accession"], []).append(h)
    for h in r_hits:
        by_r.setdefault(h["accession"], []).append(h)
    paired = []
    for acc in sorted(set(by_f) & set(by_r)):
        best = None
        for f in by_f[acc]:
            for r in by_r[acc]:
                if f["strand"] == r["strand"]:
                    continue
                product = None
                if f["strand"] == "+" and r["strand"] == "-" and f["end"] < r["start"]:
                    product = r["end"] - f["start"] + 1
                elif f["strand"] == "-" and r["strand"] == "+" and r["end"] < f["start"]:
                    product = f["end"] - r["start"] + 1
                if product is None or product < product_min or product > product_max:
                    continue
                candidate = {
                    "accession": acc, "product_bp": product,
                    "f_mismatches": f["mismatches"], "r_mismatches": r["mismatches"],
                    "f_identity": f["identity_pct"], "r_identity": r["identity_pct"],
                    "organisms": sorted(set(f.get("organisms", []) + r.get("organisms", []))),
                    "definition": f.get("definition") or r.get("definition", ""),
                }
                quality = (candidate["f_mismatches"] + candidate["r_mismatches"], -min(candidate["f_identity"], candidate["r_identity"]))
                if best is None or quality < best[0]:
                    best = (quality, candidate)
        if best:
            paired.append(best[1])
    return paired


def target_species_for_scope(base, row, scope):
    mapping = {"Especie": "Especie", "Género": "Genero", "Familia": "Familia", "Orden": "Orden"}
    col = mapping[scope]
    value = str(row.get(col, ""))
    if scope == "Especie":
        sub = base[base["Especie"].astype(str) == value]
    else:
        sub = base[base[col].astype(str) == value]
    return sorted(set(str(x) for x in sub["Especie"].dropna() if str(x).strip())), value


def _species_aliases_from_base(base, species_name):
    """Return normalized aliases for a target species, including synonymy from the Base Maestra."""
    aliases = {norm_text(species_name)}
    try:
        rows = base[base["Especie"].astype(str) == str(species_name)]
        if "Sinonimia" in rows.columns:
            for raw in rows["Sinonimia"].dropna().astype(str):
                # Synonym cells sometimes contain several names separated by punctuation.
                for part in re.split(r"[;|,/]+", raw):
                    part = part.strip()
                    if part and part.lower() not in {"nan", "none", "-"}:
                        aliases.add(norm_text(part))
    except Exception:
        pass
    return {a for a in aliases if a}


def _paired_record_search_text(record):
    """Build normalized taxonomic text from all BLAST metadata available."""
    parts = []
    parts.extend(record.get("organisms", []) or [])
    if record.get("definition"):
        parts.append(str(record.get("definition")))
    if record.get("title"):
        parts.append(str(record.get("title")))
    return norm_text(" ".join(str(x) for x in parts if x))


def _alias_in_taxonomic_text(alias, search_text):
    """Match a taxon alias as complete normalized words, not a loose substring."""
    alias = norm_text(alias)
    search_text = norm_text(search_text)
    if not alias or not search_text:
        return False
    # Word boundaries around the complete binomial/synonym. This still matches
    # 'Beauveria bassiana isolate...' but avoids accidental fragments.
    return re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", search_text) is not None


def summarize_remote_validation(base, row, scope, paired):
    targets, taxon = target_species_for_scope(base, row, scope)

    paired_orgs = []
    for p in paired:
        paired_orgs.extend(p.get("organisms", []) or [])

    covered = []
    species_evidence = {}
    accession_species = {}
    for sp in targets:
        aliases = _species_aliases_from_base(base, sp)
        hits = []
        for p in paired:
            search_text = _paired_record_search_text(p)
            if any(_alias_in_taxonomic_text(alias, search_text) for alias in aliases):
                acc = p.get("accession", "")
                hits.append(acc)
                if acc:
                    accession_species.setdefault(acc, []).append(sp)
        if hits:
            covered.append(sp)
            species_evidence[sp] = sorted(set(x for x in hits if x))

    # Annotate the displayed product rows so the user can see exactly how each
    # NCBI accession was mapped back to the Base Maestra.
    paired_annotated = []
    for p in paired:
        q = dict(p)
        q["especies_base_reconocidas"] = "; ".join(sorted(set(accession_species.get(p.get("accession", ""), []))))
        paired_annotated.append(q)

    products = [p["product_bp"] for p in paired]
    taxonomy_mappable = bool(covered) or not paired
    coverage = (100.0 * len(covered) / len(targets)) if targets and taxonomy_mappable else None
    status = "ok"
    if paired and not covered:
        status = "taxonomia_no_mapeada"
    elif not paired:
        status = "sin_producto_observado"

    return {
        "scope": scope, "taxon": taxon, "target_species": targets,
        "covered_species": covered,
        "species_evidence": species_evidence,
        "accession_species": accession_species,
        "coverage_pct": coverage,
        "paired_accessions": len(paired),
        "unique_organisms": sorted(set(paired_orgs)),
        "product_min_observed": min(products) if products else None,
        "product_max_observed": max(products) if products else None,
        "paired_examples": paired_annotated[:100],
        "interpretation_status": status,
    }


def run_remote_validation(seq_f, seq_r, taxon, base, row, scope, email="", product_min=80, product_max=3000, max_mismatches=4, hitlist_size=1000):
    sf, sr = prepare_blast_seq(seq_f), prepare_blast_seq(seq_r)
    rid_f, rtoe_f = submit_blast_short(sf, taxon, email=email, hitlist_size=hitlist_size)
    rid_r, rtoe_r = submit_blast_short(sr, taxon, email=email, hitlist_size=hitlist_size)
    # Respect NCBI's estimated wait time before first poll, capped to keep UI responsive.
    time.sleep(min(max(rtoe_f, rtoe_r, 2), 10))
    has_f = wait_blast(rid_f)
    has_r = wait_blast(rid_r)
    f_hits = parse_blast_hits(fetch_blast_xml(rid_f), len(sf), max_mismatches=max_mismatches) if has_f else []
    r_hits = parse_blast_hits(fetch_blast_xml(rid_r), len(sr), max_mismatches=max_mismatches) if has_r else []
    paired = pair_primer_hits(f_hits, r_hits, product_min=product_min, product_max=product_max)
    summary = summarize_remote_validation(base, row, scope, paired)
    shared_accessions = len(set(h["accession"] for h in f_hits) & set(h["accession"] for h in r_hits))
    summary.update({
        "validation_method": "BLAST remoto (blastn-short)",
        "rid_forward": rid_f, "rid_reverse": rid_r,
        "forward_hits": len(f_hits), "reverse_hits": len(r_hits), "shared_accessions": shared_accessions,
        "primer_f": sf, "primer_r": sr, "product_min": product_min, "product_max": product_max,
        "max_mismatches": max_mismatches,
        "degeneracy_forward": primer_degeneracy(seq_f), "degeneracy_reverse": primer_degeneracy(seq_r),
        "interpretation_status": "producto_observado" if paired else ("sin_hits" if not f_hits or not r_hits else "sin_producto_observado"),
    })
    return summary


def build_validation_panel_choices(row_compat, sag_rows):
    choices = []
    seen = set()
    if row_compat is not None and not row_compat.empty:
        for _, r in row_compat.iterrows():
            if str(r.get("Panel_ID", "")) == "SIN_PANEL_VALIDADO":
                continue
            sf, sr = str(r.get("Secuencia_F_5_a_3", "")), str(r.get("Secuencia_R_5_a_3", ""))
            key = (norm_seq(sf), norm_seq(sr))
            if not all(key) or key in seen:
                continue
            seen.add(key)
            choices.append({
                "label": f"{r.get('Marcador','')} → {r.get('Panel_ID','')}",
                "marker": r.get("Marcador", ""), "panel": r.get("Panel_ID", ""),
                "primer_f": r.get("Primer_F", ""), "primer_r": r.get("Primer_R", ""),
                "seq_f": sf, "seq_r": sr,
                "amplicon": r.get("Amplicon_reportado", ""), "source": "Base maestra",
            })
    if sag_rows is not None and not sag_rows.empty:
        for _, r in sag_rows.iterrows():
            sf, sr = str(r.get("Secuencia_F_5_a_3", "")), str(r.get("Secuencia_R_5_a_3", ""))
            key = (norm_seq(sf), norm_seq(sr))
            if not all(key) or key in seen:
                continue
            seen.add(key)
            choices.append({
                "label": f"🇨🇱 {r.get('Marcador_normalizado','')} → {r.get('Primer_F','')} / {r.get('Primer_R','')}",
                "marker": r.get("Marcador_normalizado", ""), "panel": "SAG",
                "primer_f": r.get("Primer_F", ""), "primer_r": r.get("Primer_R", ""),
                "seq_f": sf, "seq_r": sr, "amplicon": "", "source": "SAG",
            })
    return choices



def resolve_validation_engine(panel, requested="Automático"):
    degf = primer_degeneracy(panel.get("seq_f", ""))
    degr = primer_degeneracy(panel.get("seq_r", ""))
    if requested == "Automático":
        return "IUPAC + referencias NCBI" if (degf.get("is_degenerate") or degr.get("is_degenerate")) else "BLAST remoto"
    return requested


def make_validation_payload(panel, engine, taxon, scope, product_min, product_max, max_mm, targets):
    return {
        "engine": engine,
        "primer_f": norm_seq(panel.get("seq_f", "")),
        "primer_r": norm_seq(panel.get("seq_r", "")),
        "marker": str(panel.get("marker", "")),
        "taxon": taxon,
        "scope": scope,
        "product_min": int(product_min),
        "product_max": int(product_max),
        "max_mismatches": int(max_mm),
        "base_species": list(targets),
    }


def validate_one_panel(panel, base, row, scope, requested_engine="Automático", email="", api_key="",
                       product_min=80, product_max=3000, max_mm=4, cache_days=30, force_refresh=False):
    targets, taxon = target_species_for_scope(base, row, scope)
    engine = resolve_validation_engine(panel, requested_engine)
    payload = make_validation_payload(panel, engine, taxon, scope, product_min, product_max, max_mm, targets)
    cached = None if force_refresh else load_validation_cache(payload, max_age_days=int(cache_days))
    if cached:
        return cached, True, engine
    if engine == "IUPAC + referencias NCBI":
        result = run_iupac_reference_validation(
            panel.get("seq_f", ""), panel.get("seq_r", ""), panel.get("marker", ""), base, row, scope,
            email=email, api_key=api_key, product_min=int(product_min), product_max=int(product_max),
            max_mismatches=int(max_mm), records_per_species=20, max_species=25,
        )
    else:
        result = run_remote_validation(
            panel.get("seq_f", ""), panel.get("seq_r", ""), taxon, base, row, scope, email=email,
            product_min=int(product_min), product_max=int(product_max), max_mismatches=int(max_mm), hitlist_size=1000,
        )
    result = save_validation_cache(payload, result)
    return result, False, engine


def batch_summary_row(panel, result, engine, from_cache, primers, inv_seqs):
    cov = result.get("coverage_pct")
    covered = result.get("covered_species", []) or []
    denom = result.get("coverage_species_denominator", result.get("species_with_references", result.get("target_species", []))) or []
    pmin, pmax = result.get("product_min_observed"), result.get("product_max_observed")
    product_txt = "—" if pmin is None else (f"{pmin} bp" if pmin == pmax else f"{pmin}–{pmax} bp")
    meta = panel_meta_from_catalog(
        primers, panel.get("panel", ""), panel.get("primer_f", ""), panel.get("primer_r", ""),
        panel.get("seq_f", ""), panel.get("seq_r", "")
    )
    sag = bool(meta.get("es_sag")) or panel.get("source") == "SAG"
    lab = pair_in_lab(panel.get("seq_f", ""), panel.get("seq_r", ""), inv_seqs)
    status_raw = result.get("interpretation_status", "")
    if cov is None:
        state = "⚪ No concluyente"
    elif cov >= 95:
        state = "🟢 Excelente"
    elif cov >= 80:
        state = "🟡 Aceptable"
    else:
        state = "🔴 Baja"
    if status_raw in {"sin_referencias", "taxonomia_no_mapeada", "sin_hits", "locus_no_confirmado", "referencias_parciales_no_concluyente"}:
        state = "⚪ No concluyente"
    return {
        "Marcador": panel.get("marker", ""),
        "Panel": panel.get("panel", "") or panel.get("label", ""),
        "Primer F": panel.get("primer_f", ""),
        "Primer R": panel.get("primer_r", ""),
        "Motor": engine,
        "Cobertura (%)": None if cov is None else round(float(cov), 1),
        "Especies cubiertas": f"{len(covered)}/{len(denom)}",
        "Producto observado": product_txt,
        "Hits F": result.get("forward_hits", 0),
        "Hits R": result.get("reverse_hits", 0),
        "Productos compatibles": result.get("paired_accessions", 0),
        "SAG": "Sí" if sag else "No",
        "En laboratorio": "Sí" if lab else "No",
        "Evidencia documental": evidence_assessment(meta, lab, None)["documental"],
        "Evidencia in silico": evidence_assessment(meta, lab, result)["in_silico"],
        "Valoración global": evidence_assessment(meta, lab, result)["global"],
        "Caché": "Sí" if from_cache else "No",
        "Estado": state,
        "Interpretación": status_raw,
    }


def dataframe_to_xlsx_bytes(df, sheet_name="Validacion_paneles"):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        ws = writer.book[sheet_name[:31]]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            width = min(max(len(str(cell.value or "")) for cell in col) + 2, 42)
            ws.column_dimensions[col[0].column_letter].width = width
    return bio.getvalue()


def render_validation_result(result, from_cache=False):
    if from_cache:
        st.success(f"Resultado recuperado de caché ({result.get('cache_age_days', 0):.1f} días).")
    method = result.get("validation_method", "Validación remota")
    st.markdown(f"**Motor utilizado:** {method}")
    dfdeg = result.get("degeneracy_forward", {})
    drdeg = result.get("degeneracy_reverse", {})
    if dfdeg.get("is_degenerate") or drdeg.get("is_degenerate"):
        st.warning(
            f"🧬 Primer degenerado detectado. F representa hasta **{dfdeg.get('variants',1):,}** variantes y R hasta **{drdeg.get('variants',1):,}**. "
            "La validación IUPAC interpreta explícitamente los códigos degenerados; no los trata como bases literales."
        )
    status = result.get("interpretation_status", "")
    if status == "sin_referencias":
        st.warning("⚠️ **Validación no concluyente:** NCBI no devolvió referencias adecuadas para las especies muestreadas. No se informa 0 % de cobertura.")
    elif status == "sin_hits":
        st.warning("⚠️ **Validación técnica no concluyente:** al menos uno de los primers no produjo hits aceptables en BLAST. Un 0 % aquí puede ser un falso negativo, especialmente con secuencias degeneradas.")
    elif status == "sin_producto_observado":
        st.warning("⚠️ No se observó un producto compatible en las referencias recuperadas bajo los parámetros seleccionados. Esto es evidencia in silico, no una demostración de fallo experimental.")
    elif status == "sin_producto_locus_completo":
        st.warning("⚠️ **No se observó producto en referencias donde se detectaron ambos sitios de primer.** Este es un negativo in silico más informativo, aunque no sustituye una PCR experimental ni Primer-BLAST.")
    elif status == "referencias_parciales_no_concluyente":
        st.warning("⚠️ **Validación no concluyente: NCBI devolvió registros específicos del locus, pero ninguno mostró evidencia de contener ambos extremos del amplicón.** Un hit solo para F o solo para R es compatible con una secuencia parcial del locus y NO se interpreta como 0 % de cobertura.")
    elif status == "locus_no_confirmado":
        st.warning("⚠️ **Validación no concluyente: NCBI devolvió referencias genómicas, pero no se pudo confirmar que los registros recuperados representaran adecuadamente el locus objetivo.** No se interpreta como 0 % de cobertura.")
    elif status == "sin_referencias_genomicas":
        st.warning("⚠️ **NCBI no devolvió referencias genómicas adecuadas para la profundización.** El resultado sigue siendo no concluyente.")
    elif status == "producto_genomico_observado":
        st.success("🧬 **Profundización genómica positiva:** se observaron ambos sitios de primer en orientación y distancia compatibles dentro de referencias genómicas NCBI.")
    elif status == "sin_producto_genoma_completo":
        st.warning("⚠️ **No se observó producto en referencias genómicas completas/cromosómicas recuperadas.** Es un negativo in silico más fuerte que el análisis de fragmentos de locus, pero no sustituye PCR experimental ni Primer-BLAST.")
    elif status == "genoma_no_concluyente":
        st.warning("⚠️ **Profundización genómica no concluyente:** NCBI devolvió secuencias genómicas, pero no una representación que el programa considere suficientemente completa para interpretar la ausencia de producto.")
    elif status == "taxonomia_no_mapeada":
        st.warning(
            "⚠️ **Se encontraron productos PCR compatibles, pero la cobertura taxonómica no pudo calcularse con seguridad.** "
            "NCBI devolvió accesiones compatibles, pero sus metadatos no pudieron asociarse automáticamente a las especies objetivo. "
            "Por eso se muestra **No concluyente** en vez de 0 %. Revisa la columna `definition` de los hits."
        )

    cov = result.get("coverage_pct")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cobertura observada", "No concluyente" if cov is None else f"{cov:.1f} %")
    denom_species = result.get("coverage_species_denominator", result.get("species_with_references", result.get("target_species", [])))
    c2.metric("Especies cubiertas", f"{len(result.get('covered_species', []))}/{len(denom_species)}")
    c3.metric("Registros con par compatible", result.get("paired_accessions", 0))
    pmin, pmax = result.get("product_min_observed"), result.get("product_max_observed")
    c4.metric("Productos observados", "—" if pmin is None else f"{pmin}–{pmax} bp")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Hits F", result.get("forward_hits", 0))
    d2.metric("Hits R", result.get("reverse_hits", 0))
    d3.metric("Accesiones compartidas", result.get("shared_accessions", 0))
    d4.metric("Referencias analizadas", result.get("reference_records", "—"))
    if result.get("deep_genome_validation") and result.get("reference_bases") is not None:
        st.caption(f"Profundización genómica: se inspeccionaron aproximadamente **{result.get('reference_bases', 0):,} bp** en referencias NCBI temporales. No se conserva una base genómica local.")
    if result.get("sample_truncated"):
        st.info(f"El alcance tenía {len(result.get('target_species', []))} especies; por protección de tiempo/NCBI se muestrearon {len(result.get('sampled_species', []))}. Cambia a género/especie o repite por subconjuntos para una auditoría exhaustiva.")
    if result.get("species_without_references"):
        with st.expander(f"Especies sin referencia NCBI recuperada ({len(result['species_without_references'])})"):
            st.write(" · ".join(result["species_without_references"]))
    if result.get("marker_aliases_used"):
        st.caption("Sinónimos de locus usados en NCBI: " + " · ".join(result.get("marker_aliases_used", [])))
    if result.get("species_locus_unconfirmed"):
        with st.expander(f"Referencias recuperadas por fallback genómico, locus no confirmado ({len(result['species_locus_unconfirmed'])})"):
            st.write(" · ".join(result["species_locus_unconfirmed"]))
    if result.get("species_partial_references"):
        with st.expander(f"Referencias específicas del locus pero aparentemente parciales ({len(result['species_partial_references'])})"):
            st.write(" · ".join(result["species_partial_references"]))
    if result.get("retrieval_details"):
        with st.expander("Diagnóstico de recuperación NCBI por especie"):
            diag_rows = []
            for sp, md in result["retrieval_details"].items():
                diag_rows.append({
                    "Especie": sp, "Modo": md.get("retrieval_mode", ""),
                    "Locus confirmado": "Sí" if md.get("locus_confirmed") else "No",
                    "Genoma completo/cromosómico": "Sí" if md.get("genome_complete") else "No",
                    "Registros": md.get("record_count", 0),
                    "Bases recuperadas": md.get("total_bases", ""),
                    "Hits F": md.get("species_forward_hits", 0),
                    "Hits R": md.get("species_reverse_hits", 0),
                    "Registros con ambos sitios": md.get("records_with_both_primer_sites", 0),
                    "Registros con un solo extremo": md.get("records_one_sided", 0),
                    "Consulta usada": md.get("used_query", ""),
                })
            st.dataframe(pd.DataFrame(diag_rows), use_container_width=True, hide_index=True)
            detail_rows = []
            for sp, md in result["retrieval_details"].items():
                detail_rows.extend(md.get("record_diagnostics", []))
            if detail_rows:
                st.markdown("**Diagnóstico por referencia**")
                st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)
    st.caption(
        "La cobertura automática es una estimación in silico. En el motor IUPAC el denominador son las especies para las que NCBI entregó referencias; "
        "en BLAST se basa en registros donde ambos primers pueden emparejarse. Ninguno sustituye una PCR experimental ni una revisión crítica de Primer-BLAST."
    )
    covered = result.get("covered_species", [])
    if covered:
        st.markdown("**Especies con producto observado:** " + ", ".join(covered))
        evidence = result.get("species_evidence", {})
        if evidence:
            with st.expander("Evidencia de asignación especie ↔ accesión"):
                for sp in covered:
                    accs = evidence.get(sp, [])
                    st.markdown(f"- **{sp}:** " + (", ".join(accs[:20]) if accs else "hit taxonómico"))
    targets_eval = result.get("coverage_species_denominator", result.get("species_with_references", result.get("target_species", [])))
    missing = [x for x in targets_eval if x not in covered]
    if missing:
        with st.expander(f"Especies evaluadas sin producto observado ({len(missing)})"):
            st.write(" · ".join(missing))
    ex = result.get("paired_examples", [])
    if ex:
        df = pd.DataFrame(ex)
        keep = [c for c in ["species", "accession", "especies_base_reconocidas", "organisms", "product_bp", "f_mismatches", "r_mismatches", "f_identity", "r_identity", "orientation", "definition"] if c in df.columns]
        st.dataframe(df[keep].head(100), use_container_width=True, hide_index=True)
    if result.get("rid_forward") or result.get("rid_reverse"):
        st.caption(f"NCBI BLAST RID F: {result.get('rid_forward','—')} · RID R: {result.get('rid_reverse','—')}")


def inventory_sequences(inventory):
    if inventory.empty:
        return set()
    seqs = set()
    for col in ["Secuencia_F_5_a_3", "Secuencia_R_5_a_3"]:
        if col in inventory.columns:
            for v in inventory[col].dropna():
                n = norm_seq(v)
                if n:
                    seqs.add(n)
    return seqs


def pair_in_lab(seq_f, seq_r, inv_seqs):
    return bool(norm_seq(seq_f) and norm_seq(seq_r) and norm_seq(seq_f) in inv_seqs and norm_seq(seq_r) in inv_seqs)


def difficulty_banner(row):
    level = str(row.get("Dificultad_identificacion", "Estándar") or "Estándar")
    if level == "Muy alta":
        css, icon = "difficulty-veryhigh", "🔴"
    elif level == "Alta":
        css, icon = "difficulty-high", "🟠"
    else:
        css, icon = "difficulty-standard", "🟢"
    st.markdown(f'<div class="{css}">{icon} Dificultad de discriminación por amplicones: <b>{level}</b></div>', unsafe_allow_html=True)
    return level


def _search_tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", norm_text(text)) if t]


def _token_similarity(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Fragmentos: coli -> coli; velez -> velezensis; pseudo -> pseudomonas.
    if len(a) >= 3 and (a in b or b in a):
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        return max(0.88, shorter / longer)
    return SequenceMatcher(None, a, b).ratio()


def score_row(row, query):
    q = norm_text(query)
    if not q:
        return 0.0, []

    q_tokens = _search_tokens(q)
    score = 0.0
    reasons = []
    weights = [("Especie", 100), ("Sinonimia", 80), ("Genero", 55), ("Familia", 42),
               ("Orden", 32), ("Clase", 24), ("Clado", 18), ("Grupo", 12)]

    for field, weight in weights:
        raw = row.get(field, "")
        val = norm_text(raw)
        if not val:
            continue

        # 1) Nombre completo escrito dentro de una descripción libre.
        if val in q:
            score += weight
            reasons.append(f"{field}: {raw}")
            continue

        # 2) La consulta es un fragmento del taxón: 'coli' -> Escherichia coli.
        # Se exige >=3 caracteres para evitar coincidencias accidentales.
        if len(q) >= 3 and q in val:
            bonus = weight * (0.95 if field == "Especie" else 0.75)
            score += bonus
            reasons.append(f"{field} contiene '{query.strip()}'")
            continue

        val_tokens = _search_tokens(val)
        if not q_tokens or not val_tokens:
            continue

        # 3) Cada palabra de la consulta puede ser fragmento/prefijo o tener un typo leve.
        sims = []
        matched_pairs = []
        for qt in q_tokens:
            best = 0.0
            best_vt = ""
            for vt in val_tokens:
                sim = _token_similarity(qt, vt)
                if sim > best:
                    best, best_vt = sim, vt
            sims.append(best)
            if best >= 0.78:
                matched_pairs.append((qt, best_vt, best))

        if matched_pairs:
            # Dar más peso si todas las palabras de la consulta encuentran correspondencia.
            coverage = len(matched_pairs) / max(len(q_tokens), 1)
            mean_sim = sum(x[2] for x in matched_pairs) / len(matched_pairs)
            if coverage == 1.0 and mean_sim >= 0.88:
                factor = 0.72 if field == "Especie" else 0.45
            elif mean_sim >= 0.86:
                factor = 0.35 if field == "Especie" else 0.22
            else:
                factor = 0.16 if field == "Especie" else 0.10
            score += weight * factor
            reasons.append(f"{field}: coincidencia flexible")

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
    return out.sort_values(["Puntaje", "Especie"], ascending=[False, True])


def confidence_label(cands, query):
    if cands.empty:
        return "Sin coincidencia", "No se encontró un taxón del catálogo a partir de las pistas disponibles."
    top = float(cands.iloc[0]["Puntaje"])
    if not query.strip():
        return "Filtrado manual", "La selección se basa en filtros estructurados."
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
    out["Prioridad_sort"] = pd.to_numeric(out.get("Prioridad", 99), errors="coerce").fillna(99)
    return out.sort_values(["Tipo_recomendacion", "Marcador", "Prioridad_sort", "Panel_ID"])


def context_matches_taxon(context, row):
    c = norm_text(context)
    genus = norm_text(row.get("Genero", ""))
    species = norm_text(row.get("Especie", ""))
    group = norm_text(row.get("Grupo", ""))
    if not c:
        return False
    if "hongos - generico" in c or "sag - adicional suministrado" in c:
        return group == "hongos"
    if "bacillus spp" in c:
        return genus == "bacillus"
    if "grupo bacillus pumilus" in c:
        return species == "bacillus pumilus"
    if "bacillus thuringiensis" in c:
        return species in {"bacillus thuringiensis", "bacillus thuringensis"}
    if "grupo pseudomonas fluorescens" in c:
        return species == "pseudomonas fluorescens"
    for g in ["beauveria", "lecanicillium", "purpureocillium", "trichoderma"]:
        if f"{g} spp" in c and genus == g:
            return True
    return False


def applicable_sag_panels(sag, row):
    """Return complete SAG primer pairs applicable to the selected taxon.

    Uses Partidores_SAG rather than only catalog flags, because that sheet preserves
    each official F/R pair as a complete unit.
    """
    if sag.empty:
        return pd.DataFrame()
    out = sag.copy()
    if "Usar_en_motor_Streamlit" in out.columns:
        out = out[out["Usar_en_motor_Streamlit"].apply(truthy_si)]
    if "Marcador_en_Excel_original" in out.columns:
        out = out[out["Marcador_en_Excel_original"].apply(truthy_si)]
    if out.empty:
        return out
    out = out[out["Contexto_SAG"].apply(lambda x: context_matches_taxon(x, row))].copy()
    if out.empty:
        return out
    # Deduplicate identical official pairs while retaining different taxonomic contexts.
    for col in ["Secuencia_F_5_a_3", "Secuencia_R_5_a_3"]:
        out[f"_{col}"] = out[col].apply(norm_seq)
    return out.drop_duplicates(subset=["Contexto_SAG", "Marcador_normalizado", "_Secuencia_F_5_a_3", "_Secuencia_R_5_a_3"])


def find_amplicon_for_pair(seq_f, seq_r, primers, inventory):
    sf, sr = norm_seq(seq_f), norm_seq(seq_r)
    if sf and sr and not primers.empty:
        hits = primers[primers["Secuencia_5_a_3"].apply(lambda x: norm_seq(x) in {sf, sr})]
        for pid, grp in hits.groupby("Panel_ID"):
            seqs = set(grp["Secuencia_5_a_3"].apply(norm_seq))
            if sf in seqs and sr in seqs:
                vals = [x for x in grp.get("Amplicon_reportado", pd.Series(dtype=object)).tolist()
                        if pd.notna(x) and str(x).strip().lower() not in {"", "nan"}]
                if vals:
                    return vals[0]
    if sf and sr and not inventory.empty:
        for _, ir in inventory.iterrows():
            if norm_seq(ir.get("Secuencia_F_5_a_3", "")) == sf and norm_seq(ir.get("Secuencia_R_5_a_3", "")) == sr:
                amp = ir.get("Amplicon_bp", None)
                if pd.notna(amp):
                    try: return f"{int(float(amp))} bp"
                    except Exception: return str(amp)
    return None

def panel_meta_from_catalog(primers, panel_id, primer_f=None, primer_r=None, seq_f=None, seq_r=None):
    if primers.empty:
        return {}
    p = primers[primers["Panel_ID"].astype(str) == str(panel_id)].copy() if panel_id else pd.DataFrame()
    if p.empty and seq_f and seq_r:
        sf, sr = norm_seq(seq_f), norm_seq(seq_r)
        p = primers[primers["Secuencia_5_a_3"].apply(lambda x: norm_seq(x) in {sf, sr})].copy()
    if p.empty:
        return {}
    f = p[p["Direccion"].astype(str).str.upper().str.startswith("F")]
    r = p[p["Direccion"].astype(str).str.upper().str.startswith("R")]
    if primer_f and not f.empty:
        exact = f[f["Primer"].astype(str) == str(primer_f)]
        if not exact.empty: f = exact
    if primer_r and not r.empty:
        exact = r[r["Primer"].astype(str) == str(primer_r)]
        if not exact.empty: r = exact
    fr = f.iloc[0] if not f.empty else p.iloc[0]
    rr = r.iloc[0] if not r.empty else (p.iloc[1] if len(p) > 1 else p.iloc[0])
    ta = next((x for x in p.get("Ta_PCR_bibliografica_C", pd.Series(dtype=object)).tolist()
               if pd.notna(x) and str(x).strip().lower() not in {"", "nan", "no localizada"}), None)
    return {
        "tm_f": fr.get("Tm_oligo_calculada_C", None),
        "tm_r": rr.get("Tm_oligo_calculada_C", None),
        "method": fr.get("Metodo_Tm", ""),
        "ta": ta,
        "ta_ref": fr.get("Referencia_temperatura", ""),
        "ta_url": fr.get("URL_fuente_temperatura", ""),
        "amplicon": next((x for x in p.get("Amplicon_reportado", pd.Series(dtype=object)).tolist()
                           if pd.notna(x) and str(x).strip().lower() not in {"", "nan"}), None),
        "es_sag": any(p["Es_SAG"].apply(truthy_si)) if "Es_SAG" in p.columns else False,
        "contexto_sag": " | ".join(sorted(set(str(x) for x in p.get("Contexto_SAG", pd.Series(dtype=object)).dropna() if str(x).strip()))),
        "sag_ref": next((str(x) for x in p.get("Referencia_SAG", pd.Series(dtype=object)).tolist() if pd.notna(x) and str(x).strip()), ""),
        "sag_url": next((str(x) for x in p.get("URL_PDF_SAG", pd.Series(dtype=object)).tolist() if pd.notna(x) and str(x).strip()), ""),
        "reference": next((str(x) for x in p.get("Referencia", pd.Series(dtype=object)).tolist() if pd.notna(x) and str(x).strip()), ""),
        "source_url": next((str(x) for x in p.get("URL_fuente", pd.Series(dtype=object)).tolist() if pd.notna(x) and str(x).strip()), ""),
        "source_type": next((str(x) for x in p.get("Tipo_fuente", pd.Series(dtype=object)).tolist() if pd.notna(x) and str(x).strip()), ""),
        "source_verified": any(p.get("Fuente_verificada", pd.Series(dtype=object)).apply(truthy_si)) if "Fuente_verificada" in p.columns else False,
        "catalog_status": next((str(x) for x in p.get("Estado_validacion_catalogo", pd.Series(dtype=object)).tolist() if pd.notna(x) and str(x).strip()), ""),
    }


def evidence_assessment(meta, in_lab=False, result=None):
    """Evaluación conservadora: separa evidencia documental, disponibilidad y evidencia in silico."""
    sag = bool(meta.get("es_sag"))
    stype = str(meta.get("source_type", "")).lower()
    verified = bool(meta.get("source_verified"))
    status = str(meta.get("catalog_status", ""))
    peer = "revisado por pares" in stype or "publicación" in stype or "publicacion" in stype
    official = sag or "oficial" in stype
    experimental_wording = any(x in status.lower() for x in ["experimentalmente", "usado ampliamente", "recomendado para"])
    doc_score = (3 if sag else 0) + (2 if peer else 0) + (1 if verified else 0) + (1 if experimental_wording else 0)
    if doc_score >= 5:
        doc_level = "Alta"
    elif doc_score >= 3:
        doc_level = "Moderada-alta"
    elif doc_score >= 1:
        doc_level = "Moderada"
    else:
        doc_level = "Limitada"
    ins = "No evaluada"
    integrated = doc_level
    note = "La evidencia in silico es complementaria y no reemplaza PCR + secuenciación."
    if result:
        rs = result.get("interpretation_status", "")
        cov = result.get("coverage_pct")
        if rs in {"producto_genomico_observado"} or (cov is not None and cov >= 80 and result.get("paired_accessions", 0) > 0):
            ins = "Positiva"
            if doc_level in {"Alta", "Moderada-alta"}: integrated = "Alta"
            elif doc_level == "Moderada": integrated = "Moderada-alta"
        elif rs in {"sin_producto_locus_completo", "sin_producto_genoma_completo"}:
            ins = "Negativa informativa"
            integrated = "Revisar conflicto de evidencia" if doc_level in {"Alta", "Moderada-alta"} else "Baja / requiere validación experimental"
            note = "Existe tensión entre la evidencia documental y el análisis in silico; revisar referencias y validar experimentalmente antes de descartar el panel."
        elif rs in {"sin_referencias", "sin_hits", "locus_no_confirmado", "referencias_parciales_no_concluyente", "sin_referencias_genomicas", "genoma_no_concluyente", "taxonomia_no_mapeada"} or cov is None:
            ins = "No concluyente"
            note = "Un resultado in silico no concluyente no reduce por sí solo la evidencia documental existente."
        elif cov is not None and cov < 80:
            ins = "Cobertura baja observada"
            integrated = "Revisar" if doc_level in {"Alta", "Moderada-alta"} else "Limitada"
    return {
        "documental": doc_level, "in_silico": ins, "global": integrated,
        "sag": sag, "peer": peer, "official": official, "verified": verified,
        "lab": bool(in_lab), "status": status, "note": note,
    }


def render_evidence_assessment(meta, in_lab=False, result=None):
    ev = evidence_assessment(meta, in_lab, result)
    st.markdown("#### Nivel integrado de evidencia del panel")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Evidencia documental", ev["documental"])
    c2.metric("Validación in silico", ev["in_silico"])
    c3.metric("Valoración global", ev["global"])
    c4.metric("Disponible en laboratorio", "Sí" if ev["lab"] else "No")
    tags=[]
    if ev["sag"]: tags.append("🇨🇱 SAG oficial")
    if ev["peer"]: tags.append("📚 fuente bibliográfica")
    if ev["verified"]: tags.append("✓ fuente verificada")
    if tags: st.caption(" · ".join(tags))
    if ev["status"]: st.caption("**Estado documental del catálogo:** " + ev["status"])
    st.info(ev["note"])
    return ev


def badge_html(in_lab, is_sag):
    if in_lab and is_sag:
        return '<span class="badge badge-both">🧪 EN LABORATORIO · SAG OFICIAL</span>'
    if in_lab:
        return '<span class="badge badge-lab">🧪 EN LABORATORIO</span>'
    if is_sag:
        return '<span class="badge badge-sag">🇨🇱 SAG OFICIAL</span>'
    return '<span class="badge badge-warn">⚠ NO CONFIRMADO EN INVENTARIO</span>'


def metric_strip(amplicon, tm_f, tm_r, ta):
    cols = st.columns(4)
    vals = [
        ("Amplicón", val_or_dash(amplicon)),
        ("Tm F calculada", fmt_temp(tm_f)),
        ("Tm R calculada", fmt_temp(tm_r)),
        ("Ta PCR bibliográfica", fmt_temp(ta)),
    ]
    for c, (lab, val) in zip(cols, vals):
        with c:
            st.markdown(f'<div class="metricbox"><div class="smallmuted">{lab}</div><b>{val}</b></div>', unsafe_allow_html=True)


def display_compat_panel(marker, r, primers, inv_seqs, expanded=True):
    pid = r.get("Panel_ID", "")
    if str(pid) == "SIN_PANEL_VALIDADO":
        st.warning(f"{marker}: marcador autorizado, pero sin panel validado en el catálogo.")
        if pd.notna(r.get("Motivo", None)):
            st.caption(str(r.get("Motivo")))
        return
    meta = panel_meta_from_catalog(
        primers, pid,
        r.get("Primer_F", ""), r.get("Primer_R", ""),
        r.get("Secuencia_F_5_a_3", ""), r.get("Secuencia_R_5_a_3", ""),
    )
    in_lab = pair_in_lab(r.get("Secuencia_F_5_a_3", ""), r.get("Secuencia_R_5_a_3", ""), inv_seqs)
    is_sag = bool(meta.get("es_sag", False))
    title = f"{marker} → {pid} · prioridad {int(r['Prioridad_sort']) if pd.notna(r.get('Prioridad_sort')) else '—'}"
    with st.expander(title, expanded=expanded):
        st.markdown(badge_html(in_lab, is_sag), unsafe_allow_html=True)
        metric_strip(meta.get("amplicon") or r.get("Amplicon_reportado", ""), meta.get("tm_f"), meta.get("tm_r"), meta.get("ta"))
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write(f"**Nivel de compatibilidad:** {val_or_dash(r.get('Nivel_compatibilidad'))}")
            st.write(f"**Estado:** {val_or_dash(r.get('Estado'))}")
            st.write(f"**Motivo:** {val_or_dash(r.get('Motivo'))}")
            if is_sag and meta.get("contexto_sag"):
                st.write(f"**Contexto SAG:** {meta['contexto_sag']}")
        with c2:
            st.dataframe(pd.DataFrame([
                {"Primer": r.get("Primer_F", ""), "Dirección": "F", "Secuencia 5′→3′": r.get("Secuencia_F_5_a_3", ""), "Tm": fmt_temp(meta.get("tm_f"))},
                {"Primer": r.get("Primer_R", ""), "Dirección": "R", "Secuencia 5′→3′": r.get("Secuencia_R_5_a_3", ""), "Tm": fmt_temp(meta.get("tm_r"))},
            ]), use_container_width=True, hide_index=True)
        if meta.get("method"):
            st.caption(f"Tm: {meta['method']}")
        ref = r.get("Referencia", "")
        url = r.get("URL_fuente", "")
        if pd.notna(ref) and str(ref).strip(): st.write(f"**Fuente bibliográfica:** {ref}")
        b1, b2, b3 = st.columns(3)
        if pd.notna(url) and str(url).strip(): b1.link_button("Abrir fuente", str(url))
        if is_sag and meta.get("sag_url"): b2.link_button("Abrir documento SAG", meta["sag_url"])
        if meta.get("ta_url") and pd.notna(meta.get("ta_url")) and str(meta.get("ta_url")).strip(): b3.link_button("Fuente de Ta", str(meta["ta_url"]))


def display_sag_panels(sag_rows, primers, inventory, inv_seqs, recommended_markers):
    if sag_rows.empty:
        st.caption("No hay panel SAG oficial aplicable a este taxón dentro de la whitelist de marcadores del Excel original.")
        return
    for _, rr in sag_rows.iterrows():
        marker = str(rr.get("Marcador_normalizado", ""))
        pf, pr = rr.get("Primer_F", ""), rr.get("Primer_R", "")
        sf, sr = rr.get("Secuencia_F_5_a_3", ""), rr.get("Secuencia_R_5_a_3", "")
        in_lab = pair_in_lab(sf, sr, inv_seqs)
        match_recommended = any(
            norm_text(marker) == norm_text(m) or norm_text(marker) in norm_text(m) or norm_text(m) in norm_text(marker)
            for m in recommended_markers
        )
        suffix = " · coincide con marcador recomendado" if match_recommended else " · opción SAG adicional"
        title = f"🇨🇱 {marker} → {pf} / {pr}{suffix}"
        with st.expander(title, expanded=match_recommended):
            st.markdown(badge_html(in_lab, True), unsafe_allow_html=True)
            amp = find_amplicon_for_pair(sf, sr, primers, inventory)
            metric_strip(amp, rr.get("Tm_F_calculada_C", None), rr.get("Tm_R_calculada_C", None), rr.get("Ta_PCR_bibliografica_C", None))
            st.dataframe(pd.DataFrame([
                {"Primer": pf, "Dirección": "F", "Secuencia 5′→3′": sf, "Tm": fmt_temp(rr.get("Tm_F_calculada_C"))},
                {"Primer": pr, "Dirección": "R", "Secuencia 5′→3′": sr, "Tm": fmt_temp(rr.get("Tm_R_calculada_C"))},
            ]), use_container_width=True, hide_index=True)
            st.write(f"**Contexto SAG:** {val_or_dash(rr.get('Contexto_SAG'))}")
            st.write(f"**Tabla SAG:** {val_or_dash(rr.get('Tabla_SAG'))}")
            ref = rr.get("Referencia_SAG", "")
            if pd.notna(ref) and str(ref).strip(): st.write(f"**Referencia SAG:** {ref}")
            c1, c2 = st.columns(2)
            url_sag = rr.get("URL_PDF_SAG", "")
            if pd.notna(url_sag) and str(url_sag).strip(): c1.link_button("Abrir documento SAG", str(url_sag))
            ta_url = rr.get("URL_fuente_temperatura", "")
            if pd.notna(ta_url) and str(ta_url).strip(): c2.link_button("Fuente de Ta", str(ta_url))
            note = rr.get("Nota_temperatura", "")
            if pd.notna(note) and str(note).strip(): st.caption(str(note))


st.title("🧬 Asistente de decisión molecular para microorganismos")
# Invalidate caches generated by older taxonomic-mapping algorithms.
_legacy_removed = clear_legacy_cache_files()
if _legacy_removed:
    st.toast(f"Se descartaron {_legacy_removed} resultados antiguos de caché para recalcular la cobertura taxonómica.")

st.caption("Base Maestra V10.9 · Flujo molecular + paneles SAG + inventario + dificultad taxonómica + validación BLAST/IUPAC bajo demanda.")

with st.sidebar:
    st.header("Base de datos")
    uploaded = st.file_uploader("Usar otra base maestra (.xlsx)", type=["xlsx"])
    if uploaded:
        temp_path = APP_DIR / "_base_temporal.xlsx"
        temp_path.write_bytes(uploaded.getbuffer())
        db_path = temp_path
    else:
        db_path = DEFAULT_DB
    st.divider()
    st.header("Validación NCBI")
    ncbi_email = st.text_input("Correo de contacto para NCBI (opcional)", value="", help="Se envía como parámetro EMAIL a NCBI cuando se completa.")
    ncbi_api_key = st.text_input("NCBI API key (opcional)", value="", type="password", help="Aumenta el margen de consultas a E-utilities. La app no la guarda en el Excel.")
    cache_days = st.number_input("Caché de validaciones (días)", min_value=1, max_value=180, value=30, step=1)

try:
    book = load_book(str(db_path))
    base, primers, allowed, rules, qa = book["base"], book["primers"], book["allowed"], book["rules"], book["qa"]
    compat, inventory, sag = book["compat"], book["inventory"], book["sag"]
except Exception as exc:
    st.error(f"No se pudo cargar la base maestra: {exc}")
    st.stop()

inv_seqs = inventory_sequences(inventory)

with st.sidebar:
    st.success(f"{len(base)} microorganismos cargados")
    st.caption(f"{base['Orden'].nunique()} órdenes · {base['Familia'].nunique()} familias")
    if not inventory.empty: st.caption(f"{len(inventory)} pares registrados en inventario de laboratorio")
    if "Es_SAG" in primers.columns: st.caption(f"{primers['Es_SAG'].apply(truthy_si).sum()} oligos marcados como SAG")
    if "Dificultad_identificacion" in base.columns:
        n_complex = base[base["Dificultad_identificacion"].isin(["Alta","Muy alta"])].shape[0]
        st.caption(f"{n_complex} taxones con alerta de identificación compleja")
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

tab1, tab2, tab3 = st.tabs(["Identificación y Marcadores", "Primers", "Verificación"])

with tab1:
    st.subheader("1. Describe el microorganismo sospechoso")
    query = st.text_area("Incluye nombre sospechoso, género, familia u otras observaciones. La búsqueda acepta fragmentos y errores leves.",
                         placeholder="Ej.: coli, velez, Trichoderma harz, o una descripción más completa...", height=115)
    filters = {"Grupo": group_sel, "Clado": clade_sel, "Orden": order_sel, "Familia": family_sel}
    cands = rank_candidates(base, query, filters)
    conf, conf_note = confidence_label(cands, query)
    c1, c2 = st.columns([1, 2])
    c1.metric("Confianza de búsqueda", conf)
    c2.info(conf_note)
    if cands.empty:
        st.warning("No hay una coincidencia taxonómica utilizable. Ajusta filtros o incluye un nombre presente en el catálogo.")
        st.stop()

    show_cols = ["Especie", "Genero", "Familia", "Orden", "Grupo", "Puntaje", "Coincidencias"]
    st.subheader("2. Candidatos del catálogo")
    st.dataframe(cands[show_cols].head(12), use_container_width=True, hide_index=True)
    options = cands.head(30).copy()
    options["_label"] = options.apply(lambda r: f"{r['Especie']}  |  {r['Familia']}  |  {r['Orden']}", axis=1)
    selected_label = st.selectbox("Selecciona el microorganismo/candidato", options["_label"].tolist())
    row = options[options["_label"] == selected_label].iloc[0]

    st.subheader("3. Identificación taxonómica de referencia")
    tax_cols = st.columns(6)
    for c, label in zip(tax_cols, ["Grupo", "Clado", "Clase", "Orden", "Familia", "Genero"]):
        c.markdown(f"**{label}**")
        c.write(row.get(label, "—") if pd.notna(row.get(label, None)) else "—")
    st.markdown(f"**Especie:** *{row['Especie']}*")
    if pd.notna(row.get("Sinonimia", None)) and str(row.get("Sinonimia")).strip():
        st.caption(f"Sinonimia registrada: {row['Sinonimia']}")

    st.subheader("4. Complejidad de identificación")
    level = difficulty_banner(row)
    if level in {"Alta", "Muy alta"}:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Complejo / contexto taxonómico**")
            st.write(val_or_dash(row.get("Complejo_taxonomico")))
            st.markdown("**Por qué es difícil**")
            st.write(val_or_dash(row.get("Motivo_dificultad")))
        with c2:
            st.markdown("**Riesgo de interpretación**")
            st.warning(val_or_dash(row.get("Riesgo_interpretacion")))
            st.markdown("**Escalamiento recomendado**")
            st.write(val_or_dash(row.get("Escalamiento_recomendado")))
        src_diff = row.get("Fuente_dificultad", "")
        if pd.notna(src_diff) and str(src_diff).strip():
            # Puede haber dos URLs separadas por punto y coma; mostramos la primera como botón y el texto completo como caption.
            first_url = str(src_diff).split(";")[0].strip()
            if first_url.startswith("http"):
                st.link_button("Abrir fuente sobre dificultad taxonómica", first_url)
            st.caption(f"Fuentes de dificultad: {src_diff}")
    else:
        st.caption("No existe una alerta especial para este taxón. Esto no elimina la necesidad de validar resultados ambiguos.")

    st.subheader("5. Flujo molecular recomendado por la base")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Marcadores del Excel original")
        st.write(row.get("Marcadores_originales", "—"))
    with right:
        st.markdown("#### Secuencia de decisión")
        p1, p2 = row.get("Paso_1_original", ""), row.get("Paso_2_original", "")
        if pd.notna(p1) and str(p1).strip(): st.markdown(f"**Paso 1:** {p1}")
        if pd.notna(p2) and str(p2).strip(): st.markdown(f"**Paso 2:** {p2}")

    marker_list = split_items(row.get("Marcadores_normalizados", ""))
    adds = split_items(row.get("Marcadores_adicionales_por_taxon", ""))
    if marker_list:
        st.markdown("#### Marcadores normalizados autorizados")
        st.write(" · ".join(f"`{m}`" for m in marker_list))
    if adds:
        st.markdown("#### Opciones adicionales autorizadas por taxón")
        st.write(" · ".join(f"`{m}`" for m in adds))


with tab2:
    st.subheader("6. Cobertura marcador → primer")
    row_compat = get_compat_for_row(compat, row)
    if row_compat.empty:
        st.warning("No existe Compatibilidad_taxon_primer para esta entrada.")
    else:
        original = row_compat[row_compat["Tipo_recomendacion"].astype(str) == "Original del Excel"].copy()
        additional = row_compat[row_compat["Tipo_recomendacion"].astype(str) == "Adicional por taxón"].copy()
        st.markdown("### 6.1 Marcadores originales")
        for marker in original["Marcador"].drop_duplicates().tolist():
            for _, r in original[original["Marcador"] == marker].iterrows():
                display_compat_panel(marker, r, primers, inv_seqs, expanded=True)
        st.markdown("### 6.2 Opciones adicionales por taxón")
        if additional.empty:
            st.caption("No hay marcadores adicionales para esta entrada.")
        else:
            for marker in additional["Marcador"].drop_duplicates().tolist():
                for _, r in additional[additional["Marcador"] == marker].iterrows():
                    display_compat_panel(marker, r, primers, inv_seqs, expanded=False)

        reinforcement = row_compat[row_compat["Tipo_recomendacion"].astype(str) == "Refuerzo por dificultad"].copy()
        st.markdown("### 6.3 Panel reforzado para taxones complejos")
        if level not in {"Alta", "Muy alta"}:
            st.caption("Este taxón no tiene un panel reforzado especial.")
        elif reinforcement.empty:
            st.warning("El taxón está marcado como complejo, pero no existe un panel de refuerzo adicional en la base.")
        else:
            st.info("Estos paneles reutilizan exclusivamente primers ya presentes en el catálogo. No se han agregado oligos nuevos.")
            reinforcement_markers = split_items(row.get("Marcadores_refuerzo_dificultad", ""))
            if reinforcement_markers:
                st.markdown("**Marcadores de refuerzo:** " + " · ".join(f"`{m}`" for m in reinforcement_markers))
            strategy = row.get("Estrategia_reforzada", "")
            if pd.notna(strategy) and str(strategy).strip():
                st.markdown(f"**Secuencia reforzada sugerida:** {strategy}")
            for marker in reinforcement["Marcador"].drop_duplicates().tolist():
                for _, r in reinforcement[reinforcement["Marcador"] == marker].iterrows():
                    display_compat_panel(marker, r, primers, inv_seqs, expanded=False)

    st.subheader("7. Paneles SAG oficiales aplicables por taxonomía")
    sag_rows = applicable_sag_panels(sag, row)
    recommended_markers = marker_list + adds + split_items(row.get("Marcadores_refuerzo_dificultad", ""))
    display_sag_panels(sag_rows, primers, inventory, inv_seqs, recommended_markers)
    st.caption("Los paneles SAG generales siguen el contexto taxonómico declarado. En taxones de dificultad alta/muy alta, la sección de refuerzo puede activar además loci SAG ya existentes en el catálogo aunque no estuvieran en la recomendación original. No se agregan primers nuevos.")


with tab3:
    st.subheader("8. Validación remota de cobertura (NCBI, bajo demanda)")
    st.info("La V10.8 selecciona automáticamente el motor: primers no degenerados → BLAST corto; primers degenerados → búsqueda NCBI específica del locus (con sinónimos) + matching IUPAC local; solo usa un pequeño fallback genómico si no encuentra el locus. No se mantiene una base genómica permanente.")
    validation_choices = build_validation_panel_choices(row_compat if 'row_compat' in locals() else pd.DataFrame(), sag_rows if 'sag_rows' in locals() else pd.DataFrame())
    if not validation_choices:
        st.caption("No hay un par F/R disponible para validar en este taxón.")
    else:
        labels = [x["label"] for x in validation_choices]
        selected_vlabel = st.selectbox("Panel a validar", labels, key="validation_panel")
        vp = validation_choices[labels.index(selected_vlabel)]
        degf, degr = primer_degeneracy(vp["seq_f"]), primer_degeneracy(vp["seq_r"])
        c1, c2 = st.columns(2)
        c1.code(f"F {vp['primer_f']}: {vp['seq_f']}", language=None)
        c2.code(f"R {vp['primer_r']}: {vp['seq_r']}", language=None)
        vp_meta = panel_meta_from_catalog(primers, vp.get("panel", ""), vp.get("primer_f", ""), vp.get("primer_r", ""), vp.get("seq_f", ""), vp.get("seq_r", ""))
        vp_lab = pair_in_lab(vp.get("seq_f", ""), vp.get("seq_r", ""), inv_seqs)
        vp_sag = bool(vp_meta.get("es_sag")) or vp.get("source") == "SAG"
        st.markdown(badge_html(vp_lab, vp_sag), unsafe_allow_html=True)
        if vp_sag:
            st.markdown("**Evidencia documental:** 🇨🇱 **SAG lo incluye para el contexto taxonómico indicado.** La validación NCBI se muestra como una evidencia separada y no invalida por sí sola la recomendación oficial.")
            if vp_meta.get("sag_url"):
                st.link_button("Abrir documento SAG", vp_meta.get("sag_url"))
        render_evidence_assessment(vp_meta, vp_lab, None)
        if degf["is_degenerate"] or degr["is_degenerate"]:
            st.warning(f"🧬 Degeneración detectada: F ≈ {degf['variants']:,} variantes; R ≈ {degr['variants']:,}. En modo Automático se usará matching IUPAC, no BLAST directo.")
        s0, s1, s2, s3, s4 = st.columns([1.2,1,1,1,1])
        engine = s0.selectbox("Motor", ["Automático", "BLAST remoto", "IUPAC + referencias NCBI"], index=0, help="Automático usa IUPAC si cualquiera de los primers contiene bases degeneradas.")
        scope = s1.selectbox("Cobertura contra", ["Género", "Familia", "Orden", "Especie"], index=0, help="En IUPAC, familia/orden pueden muestrearse parcialmente para respetar NCBI y tiempos de ejecución.")
        product_min = s2.number_input("Amplicón mínimo (bp)", min_value=20, max_value=50000, value=80, step=10)
        product_max = s3.number_input("Amplicón máximo (bp)", min_value=50, max_value=50000, value=3000, step=100)
        max_mm = s4.number_input("Mismatches máximos / primer", min_value=0, max_value=10, value=4, step=1)
        if product_max <= product_min:
            st.error("El tamaño máximo debe ser mayor que el mínimo.")
        targets_v, taxon_v = target_species_for_scope(base, row, scope)
        st.caption(f"Taxón/alcance: **{taxon_v}** · {len(targets_v)} especie(s) de la Base Maestra.")
        pb_url = primer_blast_link(vp["seq_f"], vp["seq_r"], taxon_v, product_min, product_max)
        resolved_engine = "IUPAC + referencias NCBI" if engine == "Automático" and (degf["is_degenerate"] or degr["is_degenerate"]) else ("BLAST remoto" if engine == "Automático" else engine)
        st.caption(f"Motor que se ejecutará: **{resolved_engine}**")
        b1, b2, b3 = st.columns([1, 1, 2])
        b1.link_button("🔎 Abrir Primer-BLAST", pb_url, help="Comprobación manual oficial en NCBI Primer-BLAST.")
        force_refresh = b2.checkbox("Forzar consulta nueva", value=False, help="Ignora la caché para esta combinación.")
        payload = {
            "engine": resolved_engine, "primer_f": norm_seq(vp["seq_f"]), "primer_r": norm_seq(vp["seq_r"]),
            "marker": str(vp.get("marker", "")), "taxon": taxon_v, "scope": scope,
            "product_min": int(product_min), "product_max": int(product_max), "max_mismatches": int(max_mm),
            "base_species": targets_v,
        }
        cached = None if force_refresh else load_validation_cache(payload, max_age_days=int(cache_days))
        active_result = cached
        if cached:
            render_validation_result(cached, from_cache=True)
            render_evidence_assessment(vp_meta, vp_lab, cached)
        run_clicked = b3.button("⚙️ Validar cobertura automáticamente", type="primary", use_container_width=True)
        if run_clicked:
            try:
                if resolved_engine == "IUPAC + referencias NCBI":
                    with st.spinner("Recuperando referencias NCBI temporales y evaluando los códigos IUPAC. Puede tardar varios minutos..."):
                        result_v = run_iupac_reference_validation(
                            vp["seq_f"], vp["seq_r"], vp.get("marker", ""), base, row, scope,
                            email=ncbi_email, api_key=ncbi_api_key, product_min=int(product_min), product_max=int(product_max),
                            max_mismatches=int(max_mm), records_per_species=20, max_species=25,
                        )
                else:
                    if degf["is_degenerate"] or degr["is_degenerate"]:
                        st.warning("Estás forzando BLAST con primers degenerados. Un resultado negativo puede ser un falso negativo; para estos primers se recomienda Automático/IUPAC.")
                    with st.spinner("Consultando NCBI BLAST para F y R. Puede tardar varios minutos..."):
                        result_v = run_remote_validation(
                            vp["seq_f"], vp["seq_r"], taxon_v, base, row, scope, email=ncbi_email,
                            product_min=int(product_min), product_max=int(product_max), max_mismatches=int(max_mm), hitlist_size=1000,
                        )
                result_v = save_validation_cache(payload, result_v)
                active_result = result_v
                st.success("Validación terminada y guardada en caché.")
                render_validation_result(result_v, from_cache=False)
                render_evidence_assessment(vp_meta, vp_lab, result_v)
            except Exception as exc:
                st.error(f"La validación remota no pudo completarse: {exc}")
                st.caption("NCBI puede estar ocupado, no disponer de una referencia adecuada o limitar consultas. Primer-BLAST sigue disponible para comprobación manual.")

        # Segunda etapa opcional: solo cuando el análisis de locus quedó no concluyente.
        inconclusive_for_deep = {"referencias_parciales_no_concluyente", "locus_no_confirmado", "sin_referencias"}
        if active_result and active_result.get("interpretation_status") in inconclusive_for_deep:
            st.markdown("#### Profundización opcional con referencias genómicas")
            st.info(
                "El análisis inicial no pudo evaluar ambos extremos del amplicón con suficiente seguridad. "
                "Puedes profundizar bajo demanda usando referencias genómicas NCBI temporales. Esto puede tardar más y descargar decenas de Mb, "
                "pero no crea una base de datos genómica permanente."
            )
            deep_payload = {
                "engine": "IUPAC-genome-deep", "primer_f": norm_seq(vp["seq_f"]), "primer_r": norm_seq(vp["seq_r"]),
                "marker": str(vp.get("marker", "")), "taxon": taxon_v, "scope": scope,
                "product_min": int(product_min), "product_max": int(product_max), "max_mismatches": int(max_mm),
                "base_species": targets_v,
            }
            deep_cached = None if force_refresh else load_validation_cache(deep_payload, max_age_days=int(cache_days))
            if deep_cached:
                st.markdown("**Resultado de profundización genómica guardado:**")
                render_validation_result(deep_cached, from_cache=True)
                render_evidence_assessment(vp_meta, vp_lab, deep_cached)
            if st.button("🧬 Profundizar usando genomas completos", type="secondary", use_container_width=True, key="deep_genome_validation"):
                try:
                    with st.spinner("Recuperando referencias genómicas NCBI y buscando ambos sitios de primer. Esta etapa puede tardar varios minutos..."):
                        deep_result = run_deep_genome_validation(
                            vp["seq_f"], vp["seq_r"], vp.get("marker", ""), base, row, scope,
                            email=ncbi_email, api_key=ncbi_api_key,
                            product_min=int(product_min), product_max=int(product_max), max_mismatches=int(max_mm),
                            max_records_per_species=12, max_species=10,
                        )
                    deep_result = save_validation_cache(deep_payload, deep_result)
                    st.success("Profundización genómica terminada y guardada en caché.")
                    render_validation_result(deep_result, from_cache=False)
                    render_evidence_assessment(vp_meta, vp_lab, deep_result)
                except Exception as exc:
                    st.error(f"La profundización genómica no pudo completarse: {exc}")
                    st.caption("Puede deberse al tamaño de las referencias, disponibilidad de NCBI o límites temporales del servicio. No modifica el resultado documental SAG/bibliográfico.")


        st.markdown("### Validación masiva de paneles recomendados")
        st.caption(
            "Ejecuta todos los pares F/R recomendados para el taxón seleccionado. Primero reutiliza la caché y solo consulta NCBI para los paneles pendientes. "
            "Las consultas se ejecutan secuencialmente para no sobrecargar los servicios públicos de NCBI."
        )
        bc1, bc2, bc3, bc4 = st.columns([1, 1, 1, 1])
        batch_scope = bc1.selectbox("Alcance masivo", ["Género", "Especie"], index=0, key="batch_scope")
        batch_product_min = bc2.number_input("Mínimo (bp)", min_value=20, max_value=50000, value=int(product_min), step=10, key="batch_min")
        batch_product_max = bc3.number_input("Máximo (bp)", min_value=50, max_value=50000, value=int(product_max), step=100, key="batch_max")
        batch_mm = bc4.number_input("Mismatches / primer", min_value=0, max_value=10, value=int(max_mm), step=1, key="batch_mm")
        if batch_product_max <= batch_product_min:
            st.error("El tamaño máximo de la validación masiva debe ser mayor que el mínimo.")
        st.caption(f"Se evaluarán **{len(validation_choices)} panel(es) únicos**. Los primers degenerados usarán IUPAC automáticamente.")

        if "batch_validation_df" not in st.session_state:
            st.session_state.batch_validation_df = None
        run_all = st.button("🧪 Validar TODOS los paneles recomendados", type="primary", use_container_width=True, key="run_all_panels")
        if run_all and batch_product_max > batch_product_min:
            rows_batch = []
            progress = st.progress(0.0, text="Preparando validación masiva...")
            status_box = st.empty()
            total = len(validation_choices)
            for i, panel in enumerate(validation_choices, start=1):
                status_box.info(f"Panel {i}/{total}: {panel.get('label','')} · consultando caché/NCBI...")
                try:
                    result_b, cached_b, engine_b = validate_one_panel(
                        panel, base, row, batch_scope, requested_engine="Automático", email=ncbi_email, api_key=ncbi_api_key,
                        product_min=int(batch_product_min), product_max=int(batch_product_max), max_mm=int(batch_mm),
                        cache_days=int(cache_days), force_refresh=False,
                    )
                    rows_batch.append(batch_summary_row(panel, result_b, engine_b, cached_b, primers, inv_seqs))
                except Exception as exc:
                    rows_batch.append({
                        "Marcador": panel.get("marker", ""), "Panel": panel.get("panel", "") or panel.get("label", ""),
                        "Primer F": panel.get("primer_f", ""), "Primer R": panel.get("primer_r", ""),
                        "Motor": resolve_validation_engine(panel, "Automático"), "Cobertura (%)": None,
                        "Especies cubiertas": "—", "Producto observado": "—", "Hits F": "—", "Hits R": "—",
                        "Productos compatibles": "—", "SAG": "Sí" if panel.get("source") == "SAG" else "No",
                        "En laboratorio": "Sí" if pair_in_lab(panel.get("seq_f", ""), panel.get("seq_r", ""), inv_seqs) else "No",
                        "Caché": "No", "Estado": "⚠️ Error", "Interpretación": str(exc)[:180],
                    })
                progress.progress(i / total, text=f"Completados {i}/{total} paneles")
            status_box.empty()
            bdf = pd.DataFrame(rows_batch)
            if not bdf.empty:
                bdf["_sort_cov"] = pd.to_numeric(bdf["Cobertura (%)"], errors="coerce").fillna(-1)
                bdf["_sort_lab"] = (bdf["En laboratorio"] == "Sí").astype(int)
                bdf = bdf.sort_values(["_sort_cov", "_sort_lab"], ascending=[False, False]).drop(columns=["_sort_cov", "_sort_lab"])
            st.session_state.batch_validation_df = bdf
            st.success("Validación masiva terminada. Los resultados quedaron guardados en caché panel por panel.")

        bdf = st.session_state.get("batch_validation_df")
        if isinstance(bdf, pd.DataFrame) and not bdf.empty:
            st.dataframe(bdf, use_container_width=True, hide_index=True)
            numeric_cov = pd.to_numeric(bdf["Cobertura (%)"], errors="coerce")
            valid = bdf[numeric_cov.notna()].copy()
            if not valid.empty:
                valid["_cov"] = pd.to_numeric(valid["Cobertura (%)"], errors="coerce")
                best = valid.sort_values(["_cov", "En laboratorio"], ascending=[False, False]).iloc[0]
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Mejor cobertura", f"{best['_cov']:.1f} %")
                k2.metric("Mejor panel", str(best["Panel"]))
                k3.metric("Paneles ≥95 %", int((numeric_cov >= 95).sum()))
                k4.metric("Paneles en laboratorio", int((bdf["En laboratorio"] == "Sí").sum()))
                st.caption("El ranking prioriza cobertura observada; un panel con mayor cobertura no necesariamente tiene mayor poder discriminatorio entre especies cercanas.")
            dl1, dl2 = st.columns(2)
            csv_bytes = bdf.to_csv(index=False).encode("utf-8-sig")
            dl1.download_button("Descargar tabla CSV", csv_bytes, file_name=f"validacion_paneles_{norm_text(row.get('Especie','')).replace(' ','_')}.csv", mime="text/csv", use_container_width=True)
            xlsx_bytes = dataframe_to_xlsx_bytes(bdf)
            dl2.download_button("Descargar tabla Excel", xlsx_bytes, file_name=f"validacion_paneles_{norm_text(row.get('Especie','')).replace(' ','_')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    st.subheader("9. Resumen operacional")
    if not row_compat.empty:
        summary = []
        for _, r in row_compat.iterrows():
            if str(r.get("Panel_ID", "")) == "SIN_PANEL_VALIDADO":
                continue
            meta = panel_meta_from_catalog(primers, r.get("Panel_ID", ""), r.get("Primer_F", ""), r.get("Primer_R", ""), r.get("Secuencia_F_5_a_3", ""), r.get("Secuencia_R_5_a_3", ""))
            lab = pair_in_lab(r.get("Secuencia_F_5_a_3", ""), r.get("Secuencia_R_5_a_3", ""), inv_seqs)
            summary.append({
                "Marcador": r.get("Marcador", ""), "Panel": r.get("Panel_ID", ""),
                "SAG": "Sí" if meta.get("es_sag") else "No", "En laboratorio": "Sí" if lab else "No",
                "Amplicón": meta.get("amplicon") or r.get("Amplicon_reportado", ""),
                "Tm F": fmt_temp(meta.get("tm_f")), "Tm R": fmt_temp(meta.get("tm_r")), "Ta bibliográfica": fmt_temp(meta.get("ta")),
            })
        if summary:
            sdf = pd.DataFrame(summary).drop_duplicates()
            st.dataframe(sdf, use_container_width=True, hide_index=True)

    st.subheader("10. Trazabilidad y salida")
    source_tax = row.get("Fuente_taxonomica", "")
    if pd.notna(source_tax) and str(source_tax).strip(): st.link_button("Abrir fuente taxonómica", str(source_tax))
    report_lines = [
        f"Especie seleccionada: {row['Especie']}", f"Grupo: {row.get('Grupo','')}", f"Clado: {row.get('Clado','')}",
        f"Clase: {row.get('Clase','')}", f"Orden: {row.get('Orden','')}", f"Familia: {row.get('Familia','')}",
        f"Género: {row.get('Genero','')}", f"Dificultad: {row.get('Dificultad_identificacion','Estándar')}", f"Complejo taxonómico: {row.get('Complejo_taxonomico','')}", f"Riesgo: {row.get('Riesgo_interpretacion','')}", f"Escalamiento: {row.get('Escalamiento_recomendado','')}", f"Marcadores originales: {row.get('Marcadores_originales','')}", f"Marcadores de refuerzo: {row.get('Marcadores_refuerzo_dificultad','')}",
    ]
    if not row_compat.empty:
        report_lines.append("\nCompatibilidad marcador-primer:")
        for _, r in row_compat.iterrows():
            if str(r.get("Panel_ID", "")) == "SIN_PANEL_VALIDADO": continue
            meta = panel_meta_from_catalog(primers, r.get("Panel_ID", ""), r.get("Primer_F", ""), r.get("Primer_R", ""), r.get("Secuencia_F_5_a_3", ""), r.get("Secuencia_R_5_a_3", ""))
            lab = pair_in_lab(r.get("Secuencia_F_5_a_3", ""), r.get("Secuencia_R_5_a_3", ""), inv_seqs)
            report_lines += [
                f"- {r.get('Marcador','')}: {r.get('Panel_ID','')} | SAG={'Sí' if meta.get('es_sag') else 'No'} | Lab={'Sí' if lab else 'No'}",
                f"  F {r.get('Primer_F','')}: {r.get('Secuencia_F_5_a_3','')} | Tm {fmt_temp(meta.get('tm_f'))}",
                f"  R {r.get('Primer_R','')}: {r.get('Secuencia_R_5_a_3','')} | Tm {fmt_temp(meta.get('tm_r'))}",
                f"  Amplicón: {meta.get('amplicon') or r.get('Amplicon_reportado','')} | Ta bibliográfica: {fmt_temp(meta.get('ta'))}",
                f"  Fuente: {r.get('URL_fuente','')}",
            ]
    report = "\n".join(report_lines)
    st.download_button("Descargar resumen (.txt)", report, file_name="flujo_molecular.txt", mime="text/plain")

    with st.expander("Controles de calidad de la base"):
        if qa.empty: st.caption("No hay hoja QA.")
        else: st.dataframe(qa, use_container_width=True, hide_index=True)

    st.divider()
    st.caption("Herramienta de apoyo. V10.10: primers degenerados se validan preferentemente mediante matching IUPAC sobre referencias NCBI temporales. Tm calculada ≠ Ta de PCR. En taxones de dificultad alta/muy alta, un único locus o top-hit de BLAST no debe tratarse automáticamente como confirmación de especie. Los paneles de refuerzo reutilizan únicamente primers ya existentes en el catálogo.")
