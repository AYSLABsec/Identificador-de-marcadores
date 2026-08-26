#!/usr/bin/env bash
set -e

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"

for f in app.py base_maestra.xlsx requirements.txt; do
  if [ ! -f "$f" ]; then
    echo "ERROR: falta $f en $DIR"
    read -r -p "Presiona Enter para cerrar..." _ || true
    exit 1
  fi
done

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "ERROR: No se encontro Python 3."
  echo "Ubuntu/WSL: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

RUNTIME_ROOT="${ASISTENTE_MOLECULAR_HOME:-$HOME/.asistente_molecular}"
VENV_DIR="$RUNTIME_ROOT/venv"
CACHE_DIR="$RUNTIME_ROOT/cache"
STAMP="$RUNTIME_ROOT/requirements.sha256"
mkdir -p "$RUNTIME_ROOT" "$CACHE_DIR"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Primera ejecucion: creando entorno compartido en $VENV_DIR ..."
  rm -rf "$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || {
    echo "ERROR: No se pudo crear el entorno virtual."
    echo "Ubuntu/WSL: sudo apt install -y python3-venv"
    exit 1
  }
fi

VENV_PY="$VENV_DIR/bin/python"
if command -v sha256sum >/dev/null 2>&1; then
  REQ_HASH="$(sha256sum "$DIR/requirements.txt" | awk '{print $1}')"
else
  REQ_HASH="$($PYTHON_BIN -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$DIR/requirements.txt")"
fi
OLD_HASH="$(cat "$STAMP" 2>/dev/null || true)"

if [ "$REQ_HASH" != "$OLD_HASH" ]; then
  echo "Instalando/actualizando dependencias (solo porque requirements.txt cambio)..."
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r "$DIR/requirements.txt"
  printf '%s\n' "$REQ_HASH" > "$STAMP"
else
  echo "Dependencias listas. Inicio rapido."
fi

export ASISTENTE_MOLECULAR_CACHE_DIR="$CACHE_DIR"

echo
echo "============================================================"
echo " Asistente Molecular Nanopore V10.4"
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
