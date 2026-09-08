# Asistente Molecular Nanopore

## Manual completo de instalación y uso en Windows

Este documento explica cómo instalar y ejecutar el **Asistente Molecular Nanopore** en un computador Windows completamente nuevo.

La aplicación está desarrollada en Python y Streamlit. En Windows se ejecuta dentro de **WSL 2 (Windows Subsystem for Linux)**, usando Ubuntu. El navegador continúa siendo el navegador normal de Windows.

---

## 1. Función del programa

El Asistente Molecular Nanopore ayuda a seleccionar y evaluar estrategias de identificación molecular de microorganismos. Utiliza una base maestra en Excel que integra:

- clasificación taxonómica;
- marcadores moleculares recomendados;
- sets de primers Forward y Reverse;
- secuencias 5' a 3';
- tamaños esperados de amplicón;
- Tm calculada y Ta bibliográfica;
- fuentes bibliográficas;
- paneles incluidos en metodologías SAG;
- primers disponibles en el laboratorio;
- dificultad de discriminación taxonómica;
- validación remota contra NCBI;
- matching de primers degenerados mediante códigos IUPAC;
- validación individual y masiva de paneles;
- exportación de resultados en CSV y Excel;
- generación de informes técnicos en PDF.

La aplicación es una herramienta de apoyo. Una buena cobertura *in silico* no demuestra por sí sola que un marcador discrimine especies cercanas ni sustituye la validación experimental.

---

## 2. Requisitos del computador

### Sistema operativo

- Windows 10 actualizado o Windows 11.
- Arquitectura de 64 bits.
- Permisos para instalar WSL y Ubuntu.

### Hardware mínimo

- Procesador de 2 núcleos.
- 4 GB de RAM.
- 2 GB de espacio libre.
- Conexión a internet para instalar dependencias y consultar NCBI.

### Hardware recomendado

- Procesador de 4 núcleos o más.
- 8 GB de RAM o más.
- Unidad SSD.
- Al menos 5 GB de espacio libre.
- Conexión estable a internet.

---

## 3. Archivos obligatorios

Extraiga completamente el ZIP del programa. No ejecute los archivos directamente desde el interior del ZIP.

La carpeta debe contener:

```text
Identificador-de-marcadores/
├── app.py
├── base_maestra.xlsx
├── requirements.txt
├── INICIAR_LINUX.sh
├── INICIAR_WINDOWS_WSL.bat
└── README.md
```

Los nombres deben ser exactos. Windows suele agregar sufijos al descargar varias veces un archivo. Deben eliminarse:

| Nombre incorrecto | Nombre correcto |
|---|---|
| `app(1).py` | `app.py` |
| `base_maestra(4).xlsx` | `base_maestra.xlsx` |
| `requirements(1).txt` | `requirements.txt` |
| `INICIAR_LINUX(2).sh` | `INICIAR_LINUX.sh` |
| `INICIAR_WINDOWS_WSL(1).bat` | `INICIAR_WINDOWS_WSL.bat` |

Para comprobar las extensiones reales:

1. Abra el Explorador de archivos.
2. Seleccione **Ver**.
3. Active **Mostrar > Extensiones de nombre de archivo**.
4. Confirme que no existan nombres como `requirements.txt.txt` o `INICIAR_WINDOWS_WSL.bat.txt`.

Se recomienda utilizar inicialmente una ruta sencilla:

```text
C:\AsistenteMolecular
```

Una vez comprobado el funcionamiento, la carpeta puede trasladarse. Deben evitarse inicialmente rutas excesivamente largas, unidades de red y carpetas sincronizadas que bloqueen archivos.

---

## 4. Contenido de `requirements.txt`

El archivo debe incluir:

```text
streamlit>=1.40
pandas>=2.0
openpyxl>=3.1
requests>=2.31
regex>=2024.0
reportlab>=4.0
```

`reportlab` es necesario para generar los informes PDF.

---

## 5. Instalar WSL 2 y Ubuntu

### Paso 1: abrir PowerShell como administrador

1. Abra el menú Inicio.
2. Busque **PowerShell**.
3. Presione el botón derecho.
4. Seleccione **Ejecutar como administrador**.

### Paso 2: instalar Ubuntu

Ejecute:

```powershell
wsl --install -d Ubuntu
```

Windows instalará WSL y Ubuntu. Reinicie el computador si se solicita.

### Paso 3: completar la configuración de Ubuntu

Después del reinicio:

1. Abra **Ubuntu** desde el menú Inicio.
2. Espere a que finalice la instalación.
3. Cree un nombre de usuario Linux.
4. Cree una contraseña.

Al escribir la contraseña no se muestran asteriscos ni caracteres. Es normal.

### Paso 4: comprobar WSL

Abra PowerShell o CMD y ejecute:

```powershell
wsl --status
wsl -l -v
```

El resultado debería mostrar Ubuntu y la versión 2:

```text
NAME      STATE      VERSION
Ubuntu    Stopped    2
```

Si aparece versión 1:

```powershell
wsl --set-version Ubuntu 2
```

---

## 6. Instalar Python dentro de Ubuntu

Abra Ubuntu desde el menú Inicio y ejecute:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

Compruebe:

```bash
python3 --version
python3 -m pip --version
```

La aplicación admite normalmente Python 3.10 a 3.12.

> Python instalado directamente en Windows no reemplaza el Python de Ubuntu. El lanzador utiliza el Python instalado dentro de WSL.

---

## 7. Primera ejecución

1. Confirme que los seis archivos principales estén juntos.
2. Haga doble clic en:

```text
INICIAR_WINDOWS_WSL.bat
```

El lanzador:

1. comprueba que WSL esté disponible;
2. comprueba los archivos obligatorios;
3. convierte la ruta Windows a una ruta WSL;
4. corrige finales de línea Windows en `INICIAR_LINUX.sh`;
5. crea el entorno virtual;
6. instala las dependencias;
7. verifica los módulos esenciales;
8. inicia Streamlit;
9. abre el navegador de Windows.

La primera ejecución puede tardar varios minutos. No cierre la ventana.

La aplicación utiliza:

```text
http://localhost:8501
```

Si el navegador se abre antes de que Streamlit termine, espere unos segundos y actualice la página.

---

## 8. Entorno virtual y caché

El programa no instala paquetes dentro de la carpeta de Windows. Utiliza:

```text
~/.asistente_molecular/venv
```

La caché de validaciones se almacena en:

```text
~/.asistente_molecular/cache
```

El hash de las dependencias se almacena en:

```text
~/.asistente_molecular/requirements.sha256
```

Si `requirements.txt` no cambia, las ejecuciones siguientes reutilizan el entorno y arrancan más rápido.

El lanzador corregido no considera válido un entorno que solo tenga Python: también comprueba que disponga de `pip`.

---

## 9. Uso cotidiano

### Iniciar

Haga doble clic una sola vez en:

```text
INICIAR_WINDOWS_WSL.bat
```

Si la aplicación ya está activa, el lanzador abre el navegador sin iniciar una segunda copia.

### Abrir manualmente

Si el navegador no se abre automáticamente:

```text
http://localhost:8501
```

### Detener

1. Vuelva a la ventana del lanzador.
2. Presione `Ctrl+C`.
3. Confirme si Windows pregunta si desea terminar el trabajo por lotes.

Cerrar solamente la pestaña del navegador no detiene Streamlit.

---

## 10. Inicio manual para diagnóstico

### Desde Ubuntu

La carpeta Windows:

```text
C:\Users\usuario\Downloads\Identificador-de-marcadores
```

se ve en WSL como:

```text
/mnt/c/Users/usuario/Downloads/Identificador-de-marcadores
```

Ejemplo:

```bash
cd "/mnt/c/Users/usuario/Downloads/Identificador-de-marcadores"
bash INICIAR_LINUX.sh
```

### Ejecución directa con el entorno compartido

```bash
~/.asistente_molecular/venv/bin/python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

---

## 11. Problemas frecuentes

### 11.1 El `.bat` indica que falta un archivo

Compruebe nombres y extensiones. Los nombres válidos son:

```text
app.py
base_maestra.xlsx
requirements.txt
INICIAR_LINUX.sh
```

### 11.2 `No module named pip`

Ejemplo:

```text
~/.asistente_molecular/venv/bin/python: No module named pip
```

Significa que una creación anterior del entorno virtual quedó incompleta.

Primero instale el soporte de entornos:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

El `INICIAR_LINUX.sh` actualizado detecta esta condición y reconstruye el entorno automáticamente con `python3 -m venv --clear`.

Si se necesita reparación manual:

```bash
python3 -m venv --clear ~/.asistente_molecular/venv
~/.asistente_molecular/venv/bin/python -m pip install --upgrade pip
```

Después vuelva a ejecutar el lanzador.

### 11.3 Falta `reportlab`

Confirme que `requirements.txt` contenga:

```text
reportlab>=4.0
```

Instalación directa dentro del entorno utilizado por la aplicación:

```bash
~/.asistente_molecular/venv/bin/python -m pip install reportlab
```

Comprobación:

```bash
~/.asistente_molecular/venv/bin/python -c "import reportlab; print(reportlab.Version)"
```

### 11.4 Mensaje “utilizado por otro proceso”

Generalmente significa que quedó otra ejecución del lanzador o Streamlit activa.

No pulse repetidamente el `.bat`. Abra PowerShell y ejecute:

```powershell
wsl --shutdown
```

Espere cinco segundos y ejecute el lanzador una sola vez.

La versión actual no utiliza un archivo de registro compartido durante la ejecución normal.

### 11.5 El puerto 8501 ya está ocupado

Primero pruebe:

```text
http://localhost:8501
```

La aplicación podría estar funcionando.

Para detener todos los procesos WSL:

```powershell
wsl --shutdown
```

Después inicie nuevamente.

### 11.6 El navegador no abre automáticamente

Abra manualmente:

```text
http://localhost:8501
```

Si la página todavía no responde, espere y actualice. Compruebe en la consola que Streamlit continúe ejecutándose.

Políticas corporativas pueden impedir que PowerShell abra el navegador automáticamente sin impedir que la aplicación funcione.

### 11.7 Error `/usr/bin/env: bash\\r`

El archivo `.sh` tiene finales de línea Windows. El `.bat` actualizado los corrige automáticamente.

Reparación manual desde Ubuntu:

```bash
sed -i 's/\r$//' INICIAR_LINUX.sh
```

### 11.8 La aplicación se cierra al instalar paquetes

Ejecute manualmente:

```bash
cd "/mnt/c/ruta/de/la/carpeta"
bash INICIAR_LINUX.sh
```

El último mensaje visible indicará qué dependencia falló.

### 11.9 NCBI no responde

La búsqueda local y la revisión de primers pueden seguir funcionando. Las validaciones dependen de los servicios públicos de NCBI y pueden sufrir:

- límites de consultas;
- demoras;
- falta de referencias;
- interrupciones temporales.

Un resultado “No concluyente” no debe convertirse automáticamente en “primer inválido”.

---

## 12. Actualizar el programa

Para instalar una versión nueva:

1. Detenga la aplicación con `Ctrl+C`.
2. Haga una copia de respaldo de `base_maestra.xlsx` si contiene cambios propios.
3. Reemplace `app.py`, los lanzadores y los demás archivos actualizados.
4. Mantenga los nombres exactos.
5. Si cambió `requirements.txt`, el lanzador reinstalará las dependencias automáticamente.
6. Ejecute nuevamente `INICIAR_WINDOWS_WSL.bat`.

No es necesario reinstalar WSL ni Ubuntu para cada actualización.

---

## 13. Verificaciones posteriores a la instalación

Después del primer inicio, compruebe:

- la página abre en `http://localhost:8501`;
- la barra lateral informa que la Base Maestra fue cargada;
- se puede buscar un microorganismo;
- aparecen candidatos taxonómicos;
- se muestran marcadores y primers;
- la validación individual permite elegir un panel;
- la validación masiva permite marcar y desmarcar sets;
- se pueden descargar CSV y Excel;
- el informe PDF se genera sin advertencia de `reportlab`.

No es necesario ejecutar una validación NCBI completa para comprobar que la interfaz fue instalada correctamente.

---

## 14. Seguridad y privacidad

- La Base Maestra se lee localmente.
- Las consultas NCBI requieren internet.
- El correo NCBI y la API key son opcionales.
- La API key no se guarda dentro del Excel.
- La aplicación se sirve localmente en el puerto 8501.
- No exponga el puerto a una red pública sin configurar medidas adicionales.
- No comparta archivos que contengan información interna del laboratorio sin autorización.

---

## 15. Resumen rápido de instalación

En PowerShell como administrador:

```powershell
wsl --install -d Ubuntu
```

Reinicie y complete la creación del usuario Ubuntu.

En Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

En Windows:

1. Extraiga la carpeta completa.
2. Corrija los nombres de los archivos.
3. Ejecute una sola vez `INICIAR_WINDOWS_WSL.bat`.
4. Abra `http://localhost:8501` si el navegador no se abre automáticamente.

---

## 16. Soporte diagnóstico mínimo

Cuando solicite ayuda, incluya:

- versión de Windows;
- salida de `wsl -l -v`;
- ubicación de la carpeta;
- nombres visibles de los archivos;
- último mensaje mostrado por el lanzador;
- si `http://localhost:8501` abre manualmente;
- si el problema ocurre durante instalación, inicio, validación NCBI o generación del PDF.

No envíe contraseñas ni API keys.
