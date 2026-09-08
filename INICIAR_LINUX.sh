#!/usr/bin/env bash
set -Eeuo pipefail

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"

for f in app.py base_maestra.xlsx requirements.txt; do
  if [ ! -f "$f" ]; then
    echo "ERROR: falta $f en $DIR"
    exit 1
  fi
done

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "ERROR: no se encontro Python 3."
  echo "Ejecuta: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

RUNTIME_ROOT="${ASISTENTE_MOLECULAR_HOME:-$HOME/.asistente_molecular}"
VENV_DIR="$RUNTIME_ROOT/venv"
CACHE_DIR="$RUNTIME_ROOT/cache"
STAMP="$RUNTIME_ROOT/requirements.sha256"
mkdir -p "$RUNTIME_ROOT" "$CACHE_DIR"

create_or_repair_venv() {
  echo "Creando o reparando el entorno compartido en $VENV_DIR ..."
  if ! "$PYTHON_BIN" -m venv --clear "$VENV_DIR"; then
    echo
    echo "ERROR: Python no pudo crear un entorno virtual completo."
    echo "Dentro de Ubuntu/WSL ejecuta:"
    echo "  sudo apt update"
    echo "  sudo apt install -y python3-venv python3-pip"
    echo "Luego vuelve a ejecutar INICIAR_WINDOWS_WSL.bat."
    exit 1
  fi
}

# Un entorno puede contener bin/python pero estar incompleto y no tener pip.
if [ ! -x "$VENV_DIR/bin/python" ]; then
  create_or_repair_venv
elif ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
  echo "Se detecto un entorno virtual incompleto: Python existe, pero pip no."
  create_or_repair_venv
fi

VENV_PY="$VENV_DIR/bin/python"

# Comprobacion posterior obligatoria para no reutilizar un entorno danado.
if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
  echo
  echo "ERROR: el entorno virtual sigue sin disponer de pip."
  echo "Dentro de Ubuntu/WSL ejecuta:"
  echo "  sudo apt update"
  echo "  sudo apt install -y python3-venv python3-pip"
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  REQ_HASH="$(sha256sum "$DIR/requirements.txt" | awk '{print $1}')"
else
  REQ_HASH="$("$PYTHON_BIN" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$DIR/requirements.txt")"
fi
OLD_HASH="$(cat "$STAMP" 2>/dev/null || true)"

if [ "$REQ_HASH" != "$OLD_HASH" ]; then
  echo "Instalando/actualizando dependencias..."
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r "$DIR/requirements.txt"
  printf '%s\n' "$REQ_HASH" > "$STAMP"
else
  echo "Dependencias listas. Inicio rapido."
fi

# Verifica los modulos esenciales incluso cuando el hash no cambio.
if ! "$VENV_PY" -c "import streamlit,pandas,openpyxl,requests,regex,reportlab" >/dev/null 2>&1; then
  echo "Falta al menos una dependencia esencial. Reinstalando requirements.txt..."
  "$VENV_PY" -m pip install -r "$DIR/requirements.txt"
  "$VENV_PY" -c "import streamlit,pandas,openpyxl,requests,regex,reportlab"
fi

export ASISTENTE_MOLECULAR_CACHE_DIR="$CACHE_DIR"

echo
echo "============================================================"
echo " Asistente Molecular Nanopore"
echo "============================================================"
echo "URL: http://localhost:8501"
echo "Entorno: $VENV_DIR"
echo "Cache:   $CACHE_DIR"
echo "Para detenerlo: Ctrl+C"
echo

exec "$VENV_PY" -m streamlit run "$DIR/app.py" \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
