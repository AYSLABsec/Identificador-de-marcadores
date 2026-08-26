# Asistente Molecular Nanopore — V10.10

## Manual de instalación, uso e interpretación

**Versión documentada:** V10.10  
**Plataforma:** Streamlit / Python  
**Sistemas previstos:** Linux y Windows mediante WSL  
**Base de conocimiento:** `base_maestra.xlsx`

---

# 1. ¿Qué es este programa?

El **Asistente Molecular Nanopore** es una aplicación de apoyo para seleccionar y evaluar estrategias de identificación molecular de microorganismos a partir de una base maestra taxonómica y de primers.

El programa permite:

- buscar microorganismos por nombre completo, fragmentos del nombre o términos aproximados;
- recuperar su clasificación taxonómica;
- mostrar los marcadores moleculares recomendados definidos en la Base Maestra;
- seleccionar primers compatibles con la especie, género, familia u orden;
- identificar si un primer o panel es **SAG oficial**;
- identificar si un primer está **disponible físicamente en el laboratorio**;
- mostrar secuencias 5'→3', tamaño esperado del amplicón, Tm calculada y Ta bibliográfica cuando existe;
- advertir cuando una especie pertenece a un complejo taxonómico difícil de discriminar por amplicones;
- proponer paneles reforzados para esas especies difíciles sin agregar primers fuera del catálogo existente;
- realizar validaciones in silico bajo demanda contra NCBI;
- tratar primers degenerados mediante matching IUPAC;
- diferenciar resultados positivos, negativos fuertes y resultados **no concluyentes**;
- ejecutar validación masiva de todos los paneles recomendados;
- integrar evidencia SAG, bibliográfica e in silico en una valoración global;
- exportar resultados y tablas resumen.

El programa es una **herramienta de apoyo a la decisión**. No reemplaza una validación experimental ni debe interpretar automáticamente una coincidencia bioinformática como identificación definitiva cuando el grupo taxonómico es complejo.

---

# 2. Archivos principales

La carpeta del programa debe contener, como mínimo:

```text
Identificador de Marcadores/
├── app.py
├── base_maestra.xlsx
├── requirements.txt
├── INICIAR_LINUX.sh
├── INICIAR_WINDOWS_WSL.bat
└── README.md
```

## `app.py`

Aplicación principal de Streamlit. Contiene la interfaz, búsqueda, reglas de selección, validación NCBI, matching IUPAC y generación de resultados.

## `base_maestra.xlsx`

Es la fuente principal de conocimiento. Incluye taxonomía, marcadores, catálogo de primers, secuencias, fuentes, SAG, inventario del laboratorio, dificultad de discriminación y reglas de compatibilidad.

**No renombrar este archivo** salvo que también se modifique el código.

## `requirements.txt`

Dependencias Python utilizadas actualmente:

```text
streamlit>=1.40
pandas>=2.0
openpyxl>=3.1
requests>=2.31
regex>=2024.0
```

## `INICIAR_LINUX.sh`

Lanzador recomendado en Linux y dentro de WSL.

## `INICIAR_WINDOWS_WSL.bat`

Lanzador de un clic para Windows. Ejecuta la aplicación dentro de WSL y abre el navegador de Windows cuando el servidor está listo.

---

# 3. Requisitos de hardware

No se requiere un computador de alto rendimiento para la operación normal.

### Mínimo razonable

- CPU: 2 núcleos
- RAM: 4 GB
- Espacio libre: 2 GB
- Conexión a internet: necesaria para las validaciones remotas NCBI

### Recomendado

- CPU: 4 núcleos o más
- RAM: 8 GB o más
- SSD
- 5 GB o más de espacio libre
- conexión estable a internet

Las búsquedas normales sobre el Excel son locales y rápidas. Las validaciones NCBI dependen de la disponibilidad y velocidad de los servidores externos.

---

# 4. Requisitos de software

## Linux

Recomendado:

- Ubuntu 22.04, 24.04 o equivalente moderno;
- Python 3.10–3.12;
- `python3-venv`;
- `python3-pip`;
- navegador web moderno.

En Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

Python 3.12 ha sido utilizado durante el desarrollo en WSL.

## Windows

La versión actual está pensada para correr mediante **WSL**.

Requisitos:

- Windows 10/11 con WSL habilitado;
- una distribución Linux instalada en WSL, preferentemente Ubuntu;
- Python instalado dentro de WSL;
- navegador de Windows.

Para comprobar WSL, abrir PowerShell o CMD:

```powershell
wsl --status
```

Si WSL no está instalado, desde PowerShell como administrador:

```powershell
wsl --install
```

Reiniciar cuando Windows lo solicite.

Después, dentro de Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

---

# 5. Instalación recomendada

## 5.1 Windows + WSL

1. Extraer completamente el ZIP del programa.
2. Mantener juntos todos los archivos de la carpeta.
3. Hacer doble clic en:

```text
INICIAR_WINDOWS_WSL.bat
```

El lanzador:

1. comprueba que WSL esté disponible;
2. comprueba que estén `app.py`, `base_maestra.xlsx`, `requirements.txt` e `INICIAR_LINUX.sh`;
3. convierte la ruta de Windows a una ruta WSL;
4. crea o reutiliza el entorno Python compartido;
5. instala dependencias solo cuando `requirements.txt` cambia;
6. inicia Streamlit;
7. espera a que el servidor responda;
8. abre automáticamente `http://localhost:8501` en Windows.

**No cerrar la ventana de consola mientras se esté usando la aplicación.**

## 5.2 Linux

En la carpeta del proyecto:

```bash
bash INICIAR_LINUX.sh
```

Luego abrir:

```text
http://localhost:8501
```

Normalmente Streamlit permanecerá activo hasta presionar:

```text
Ctrl+C
```

---

# 6. Entorno virtual compartido y rendimiento

Para evitar la lentitud observada con WSL + `/mnt/c` + OneDrive, el programa **no instala las dependencias dentro de la carpeta de Windows**.

El entorno se almacena en:

```text
~/.asistente_molecular/venv
```

La caché se guarda en:

```text
~/.asistente_molecular/cache
```

El hash de dependencias se guarda en:

```text
~/.asistente_molecular/requirements.sha256
```

Esto permite que futuras versiones reutilicen el mismo entorno.

### Primera ejecución

Puede tardar varios minutos porque Python debe crear el entorno e instalar las dependencias.

### Ejecuciones posteriores

Deben ser considerablemente más rápidas, porque la instalación se omite si `requirements.txt` no cambió.

---

# 7. Inicio manual para diagnóstico

Si se necesita depurar un problema:

```bash
cd "/ruta/al/proyecto"
bash INICIAR_LINUX.sh
```

También puede ejecutarse manualmente usando el entorno compartido:

```bash
~/.asistente_molecular/venv/bin/python -m streamlit run app.py \
  --server.headless true \
  --server.fileWatcherType none
```

Abrir después:

```text
http://localhost:8501
```

---

# 8. Organización de la interfaz V10.10

La interfaz se divide en tres pestañas para agilizar el trabajo.

## Pestaña 1 — `1–5 · Identificación y flujo`

Incluye:

1. descripción del microorganismo sospechoso;
2. candidatos del catálogo;
3. identificación taxonómica de referencia;
4. complejidad de identificación;
5. flujo molecular recomendado.

## Pestaña 2 — `6–7 · Primers y SAG`

Incluye:

6. cobertura marcador → primer;
7. paneles SAG oficiales aplicables por taxonomía.

## Pestaña 3 — `8+ · Validación y salida`

Incluye:

8. validación remota NCBI;
9. resumen operacional;
10. trazabilidad y salida;
11. validación masiva de paneles;
12. profundización genómica cuando corresponde;
13. exportación de resultados.

---

# 9. Uso paso a paso

## Paso 1 — Buscar el microorganismo

En la barra principal escribir el nombre o parte del nombre.

Ejemplos válidos:

```text
Escherichia coli
coli
velez
velezenzis
Trichoderma harz
Pseudomonas
```

La búsqueda es flexible y da mayor peso a especie y sinonimia.

No es necesario escribir el nombre completo correctamente para obtener candidatos.

---

## Paso 2 — Revisar los candidatos

El programa genera una lista ordenada de microorganismos compatibles con la búsqueda.

Seleccionar el organismo que corresponda a la sospecha de laboratorio.

La búsqueda **no constituye identificación molecular**. Solo selecciona la entrada de referencia sobre la cual se construirá el flujo.

---

## Paso 3 — Revisar taxonomía

La aplicación muestra, según disponibilidad:

```text
Grupo
Clado
Clase
Orden
Familia
Género
Especie
```

Revisar especialmente sinonimias o nombres taxonómicos históricos, ya que algunos grupos han sufrido reclasificaciones importantes.

---

## Paso 4 — Revisar dificultad de discriminación

La app clasifica cada entrada aproximadamente como:

### 🟢 Estándar

No existe una advertencia importante específica dentro de la base.

Esto **no significa que cualquier marcador sea suficiente**. Significa que no se ha definido un problema especial de discriminación para esa entrada.

### 🟠 Alta

La especie pertenece a un grupo donde un solo barcode puede ser insuficiente.

Suele recomendarse multilocus o un marcador secundario más discriminante.

### 🔴 Muy alta

Existe un complejo taxonómico, especies crípticas o una proximidad genómica que hace inseguro confirmar especie con un solo amplicón.

Ejemplos típicos:

- complejo *Bacillus subtilis*;
- grupo *B. amyloliquefaciens / B. velezensis / B. siamensis*;
- *Bacillus cereus* sensu lato;
- complejo *Trichoderma harzianum*;
- *Pseudomonas fluorescens* complex;
- *Rhizobium leguminosarum* species complex;
- *Enterobacter cloacae* complex;
- Glomeromycota con heterogeneidad de rDNA.

En estos casos deben seguirse los paneles reforzados y la recomendación de escalamiento.

---

## Paso 5 — Interpretar el flujo molecular recomendado

La aplicación conserva dos conceptos separados:

### Marcadores del Excel original

Son los loci que fueron definidos originalmente para esa especie/grupo.

### Marcadores de refuerzo

Pueden añadirse para especies de alta dificultad **solo si ya existen en el catálogo de primers autorizado**.

No se agregan arbitrariamente primers nuevos durante la operación.

La aplicación puede mostrar algo como:

```text
Paso 1: TEF1
Paso 2: ACT1 + CAL
Apoyo: RPB2 + TUB2
Filtro: ITS
```

La secuencia representa un flujo de decisión, no necesariamente la obligación de amplificar todos los loci desde el comienzo.

---

# 10. Cómo interpretar la sección de primers

Cada panel puede contener:

- marcador;
- nombre del panel;
- primer Forward;
- primer Reverse;
- secuencias 5'→3';
- tamaño esperado del amplicón;
- Tm calculada;
- Ta bibliográfica;
- taxón de aplicación;
- fuente;
- condición SAG;
- disponibilidad en laboratorio;
- estado de validación.

## 🧪 EN LABORATORIO

Significa que las secuencias de los oligos coinciden con el inventario registrado como disponible físicamente.

La coincidencia se realiza por **secuencia**, no solamente por nombre.

Esto es importante porque existen distintas variantes con nombres como `27F`, `1492R`, etc.

## 🇨🇱 SAG OFICIAL

Significa que el par aparece dentro de la metodología oficial SAG incorporada a la Base Maestra para el contexto taxonómico indicado.

Un panel puede ser simultáneamente:

```text
🧪 EN LABORATORIO · 🇨🇱 SAG OFICIAL
```

---

# 11. Tm y Ta: no son lo mismo

## Tm calculada

La **Tm** es una estimación de la temperatura de fusión de cada oligo individual.

La app puede mostrar:

```text
Tm F: 58.4 °C
Tm R: 60.1 °C
```

## Ta bibliográfica

La **Ta** es la temperatura de annealing utilizada en un protocolo PCR publicado.

Ejemplo:

```text
Ta bibliográfica: 55 °C
```

No debe asumirse que:

```text
Ta = Tm
```

La Ta depende además de:

- polimerasa;
- buffer;
- Mg²⁺;
- concentración de primers;
- cantidad/calidad del ADN;
- presencia de degeneraciones;
- programa térmico.

Cuando existe una Ta bibliográfica, debe considerarse un punto de partida experimental, no una condición universal garantizada.

---

# 12. Primers degenerados

Un primer puede contener bases IUPAC:

```text
R = A/G
Y = C/T
N = A/C/G/T
D = A/G/T
H = A/C/T
etc.
```

Ejemplo:

```text
GAYGGNYTNAARCCNGTNCA
```

Representa muchas secuencias posibles.

Por esta razón, la app no trata los primers altamente degenerados igual que un oligo convencional en BLAST.

Para estos casos se utiliza matching IUPAC sobre secuencias NCBI recuperadas temporalmente.

---

# 13. Validación remota NCBI

La validación in silico es **bajo demanda**. No se mantiene una gran base genómica local.

El usuario selecciona un panel y ejecuta la validación.

Dependiendo del primer, el programa utiliza:

### BLAST corto

Preferido para primers poco o no degenerados.

### Matching IUPAC

Preferido para primers degenerados.

La app evalúa, cuando los datos lo permiten:

- presencia de sitio F;
- presencia de sitio R;
- orientación;
- distancia entre sitios;
- tamaño del producto;
- mismatches;
- especies del catálogo con producto compatible.

---

# 14. ¿Qué significa “Cobertura”?

La cobertura mostrada intenta responder:

> ¿En cuántas de las especies objetivo de la Base Maestra se observó un producto in silico compatible con este par de primers?

Ejemplo:

```text
Especies objetivo: 4
Especies con producto compatible: 3
Cobertura observada: 75 %
```

La cobertura **no equivale a poder discriminatorio**.

Un primer puede tener 100 % de cobertura y amplificar todas las especies, pero producir secuencias demasiado similares para distinguirlas.

Se deben separar siempre dos preguntas:

### Cobertura

> ¿Amplifica?

### Discriminación

> ¿El amplicón permite separar las especies relevantes?

---

# 15. ¿Qué significa “No concluyente”?

**No concluyente NO significa 0 % de cobertura.**

Significa que la información disponible no es suficiente para afirmar ni que el panel funciona ni que falla.

Puede ocurrir por ejemplo cuando:

- las secuencias NCBI del locus son parciales;
- contienen el sitio Forward pero no alcanzan el Reverse;
- NCBI no tiene suficientes secuencias del marcador;
- los registros recuperados no representan adecuadamente el locus;
- la recuperación genómica fue insuficiente;
- los datos taxonómicos no pudieron mapearse de forma segura.

La app intenta distinguir:

### ✅ Producto observado

Se encontraron F y R en orientación y distancia compatibles.

### ❌ Negativo in silico fuerte

Existe evidencia suficiente de que se examinó la región pertinente y no se obtuvo producto compatible.

### ⚠️ No concluyente

Los datos no permiten evaluar correctamente el par.

Nunca debe convertirse automáticamente un **No concluyente** en “primer no válido”.

---

# 16. Profundización genómica

Cuando la primera validación queda no concluyente, la aplicación puede ofrecer:

```text
🧬 Profundizar usando genomas completos
```

Esta función intenta buscar evidencia en secuencias genómicas NCBI.

Debe interpretarse con cuidado.

Un registro etiquetado como genómico puede corresponder a:

- cromosoma completo;
- assembly fragmentado;
- scaffold;
- contig;
- mitocondria;
- otra secuencia parcial.

Por ello, la ausencia de hits solo es un negativo fuerte cuando la cantidad y naturaleza de la secuencia recuperada son suficientes para evaluar el locus.

---

# 17. Evidencia documental vs evidencia in silico

Desde V10.9 la aplicación separa explícitamente varias capas de evidencia.

## Evidencia SAG

Un método oficial SAG constituye evidencia documental importante para el uso indicado.

## Evidencia bibliográfica

Puede incluir:

- publicación original del primer;
- PCR demostrada;
- secuenciación del producto;
- filogenia o discriminación demostrada;
- uso posterior reproducido por otros estudios.

## Evidencia in silico

Es una evidencia adicional basada en los datos actualmente recuperables desde NCBI.

Un resultado NCBI no concluyente **no anula** automáticamente un primer con fuerte respaldo experimental.

Ejemplo conceptual:

```text
SAG oficial: Sí
PCR publicada: Sí
Amplicón secuenciado: Sí
NCBI in silico: No concluyente
Valoración global: alta confianza documental; validar experimentalmente en el laboratorio
```

---

# 18. Valoración global del panel

El programa intenta integrar:

- SAG;
- bibliografía;
- evidencia experimental publicada;
- disponibilidad en laboratorio;
- resultado in silico;
- complejidad taxonómica.

Si la evidencia documental fuerte y el análisis in silico entran en conflicto, debe aparecer una advertencia del tipo:

```text
Revisar conflicto de evidencia
```

La respuesta correcta es entonces realizar validación experimental, no escoger automáticamente una de las dos fuentes.

---

# 19. Cómo se valida experimentalmente un primer

La validación definitiva debe incluir, idealmente:

1. control positivo conocido;
2. ADN de buena calidad;
3. PCR en condiciones publicadas o gradiente de annealing;
4. banda del tamaño esperado;
5. control negativo;
6. purificación del amplicón;
7. secuenciación Sanger o Nanopore;
8. confirmación de que el amplicón corresponde al locus esperado;
9. evaluación de si la secuencia realmente discrimina las especies objetivo;
10. repetibilidad entre cepas cuando corresponda.

Una banda de tamaño esperado por sí sola **no demuestra** identidad del locus.

---

# 20. Validación masiva de paneles

La aplicación permite ejecutar:

```text
🧪 Validar TODOS los paneles recomendados
```

La función:

1. reúne todos los paneles aplicables;
2. elimina duplicados;
3. consulta primero la caché;
4. valida únicamente lo que falta;
5. utiliza BLAST o IUPAC según el tipo de primer;
6. crea una tabla comparativa.

La tabla puede incluir:

- Panel;
- Marcador;
- Primer F;
- Primer R;
- Motor;
- Cobertura;
- Especies cubiertas;
- producto observado;
- hits F/R;
- productos compatibles;
- SAG;
- laboratorio;
- caché;
- evidencia documental;
- evidencia in silico;
- valoración global.

Los resultados se pueden descargar en CSV/XLSX.

### Tiempo de ejecución

Una primera validación de muchos paneles puede tardar varios minutos porque las consultas se realizan de forma conservadora para no abusar de los servicios públicos NCBI.

Las repeticiones suelen ser mucho más rápidas por la caché.

---

# 21. Caché

La caché evita repetir consultas NCBI idénticas.

Ubicación predeterminada:

```text
~/.asistente_molecular/cache
```

La aplicación ha cambiado varias veces el formato/algoritmo de validación. Las versiones nuevas pueden invalidar automáticamente cachés anteriores cuando es necesario.

Si se sospecha un resultado antiguo o inconsistente, puede forzarse una consulta nueva desde la interfaz o eliminar la caché manualmente:

```bash
rm -rf ~/.asistente_molecular/cache/*
```

Esto no elimina la Base Maestra ni el entorno Python.

---

# 22. Interpretación en taxones difíciles

## *Bacillus amyloliquefaciens / B. velezensis / B. siamensis*

No confirmar especie únicamente mediante 16S o un único housekeeping gene cuando la conclusión sea crítica.

Preferir concordancia multilocus y escalar a WGS/ANI cuando exista implicancia regulatoria, contractual o legal.

## *Bacillus cereus* sensu lato

La separación de *B. cereus*, *B. thuringiensis* y relacionados es especialmente compleja. Los elementos plasmidiales y genes funcionales pueden ser relevantes.

## *Trichoderma harzianum* complex

ITS puede ser insuficiente. TEF1 y loci adicionales como ACT/CAL pueden aportar mayor resolución.

## *Pseudomonas fluorescens* complex

16S suele ser insuficiente. `rpoD` y otros housekeeping genes pueden ser mucho más discriminantes.

## Rizobios

`recA`, `atpD`, `glnII`, `gyrB`, `rpoB` u otros loci pueden ser necesarios en combinación.

## Glomeromycota

Existe variabilidad intragenómica de rDNA. La interpretación debe ser filogenética y no limitarse a “mejor BLAST = especie”.

---

# 23. Actualización de la Base Maestra

Antes de modificar `base_maestra.xlsx`, realizar una copia de seguridad.

La aplicación depende de nombres de hojas y columnas concretos.

No cambiar arbitrariamente:

- nombres de hojas;
- identificadores de panel;
- nombres de columnas;
- secuencias de primers;
- campos usados para SAG/laboratorio;
- marcadores normalizados.

Una secuencia de primer debe mantenerse asociada a su fuente y alcance taxonómico.

No debe ampliarse el alcance de un primer de una especie/familia a todo un orden únicamente porque comparta el mismo locus.

---

# 24. Solución de problemas

## Error: `No module named regex`

Normalmente significa que se ejecutó:

```bash
streamlit run app.py
```

con el Python global en vez del entorno del proyecto.

Solución recomendada:

```bash
bash INICIAR_LINUX.sh
```

Comprobar:

```bash
~/.asistente_molecular/venv/bin/python -c "import regex; print(regex.__version__)"
```

---

## Error: falta `requirements.txt`

Se extrajo un paquete incompleto o se copiaron solo algunos archivos.

Confirmar:

```bash
ls
```

Deben existir:

```text
app.py
base_maestra.xlsx
requirements.txt
INICIAR_LINUX.sh
```

---

## Streamlit inicia pero aparece `gio: ... Operation not supported`

No es un fallo del servidor. WSL intentó abrir un navegador Linux.

La versión actual usa modo headless y el lanzador de Windows abre el navegador de Windows automáticamente.

Si es necesario abrir manualmente:

```text
http://localhost:8501
```

---

## La aplicación tarda mucho en iniciar en Windows

Evitar crear `.venv` dentro de:

```text
/mnt/c/...
```

y especialmente dentro de OneDrive.

La versión actual usa:

```text
~/.asistente_molecular/venv
```

Si la primera ejecución tarda, es normal. Si todas tardan, comprobar que no se esté eliminando `~/.asistente_molecular` entre sesiones.

---

## NCBI tarda mucho

Puede deberse a:

- carga de servidores públicos;
- muchas especies objetivo;
- primers degenerados;
- validación masiva;
- recuperación de referencias genómicas.

Esperar o repetir posteriormente. No interpretar un timeout como fallo biológico del primer.

---

## Aparece cobertura 0 pero existen hits

Revisar:

- si ambos primers aparecen en la misma referencia;
- orientación;
- tamaño del producto;
- mapeo taxonómico;
- si la información corresponde a una caché antigua;
- si el resultado debería ser “No concluyente”.

La cobertura requiere **producto compatible**, no simplemente hits independientes de F y R.

---

## Solo aparece F o solo aparece R

Puede significar:

1. incompatibilidad real del segundo primer; o
2. referencia parcial que no contiene el segundo sitio.

La app debe favorecer **No concluyente** cuando no puede demostrar que la referencia cubre toda la región esperada.

---

# 25. Uso responsable de NCBI

Las consultas se realizan secuencialmente y bajo demanda para no sobrecargar servicios públicos.

Evitar lanzar repetidamente validaciones masivas idénticas forzando una consulta nueva sin necesidad.

La caché existe precisamente para reducir tráfico y tiempo de ejecución.

---

# 26. Historial de versiones

## Prototipo inicial / V1

- Lectura de Base Maestra Excel.
- Búsqueda de microorganismo.
- Taxonomía y flujo molecular básico.
- Asociación de marcadores y primers.

## V2

- Priorización de primers por taxón.
- Más de una alternativa por locus.
- Separación entre primers específicos y generales.

## V3

- Hoja `Compatibilidad_taxon_primer`.
- Cada marcador recomendado debía terminar en primer compatible o brecha explícita.
- Corrección de omisiones como `glnII`, `mdh` e `infB`.

## V4

- Incorporación del inventario físico del laboratorio.
- Marcado de primers por coincidencia exacta de secuencia.
- Indicador de panel completo disponible en laboratorio.

## V5

- Integración de primers oficiales SAG.
- Columnas específicas de SAG, contexto, tabla, referencia y URL.
- Conservación separada de primers SAG que no pertenecían a los marcadores originales.

## V6

- Incorporación de Tm calculada.
- Incorporación de Ta bibliográfica cuando estaba disponible.
- Fuentes específicas de condiciones PCR.

## V7

- Capa de dificultad taxonómica.
- Clasificación estándar / alta / muy alta.
- Complejos taxonómicos y riesgo de interpretación.
- Paneles reforzados para especies difíciles.
- Regla estricta: no agregar primers nuevos.

## V8

- Validación remota de cobertura bajo demanda.
- Integración de NCBI BLAST.
- Caché de resultados.
- Enlace/flujo de apoyo hacia Primer-BLAST.

## V9

- Corrección para primers degenerados.
- Motor IUPAC sobre referencias NCBI temporales.
- Diagnóstico de F, R, accesiones compartidas y productos.

## V10

- Búsqueda textual flexible.
- Fragmentos y errores leves: `coli`, `velez`, etc.
- Lanzadores Linux y Windows+WSL.

## V10.1

- Corrección del paquete de distribución.
- Inclusión correcta de `requirements.txt` y `base_maestra.xlsx`.
- Arranque headless para WSL.

## V10.2

- Corrección de mapeo taxonómico de hits NCBI.
- Uso de `definition` como respaldo cuando el campo organism estaba vacío.

## V10.3

- Versionado de caché para evitar reutilizar resultados calculados con algoritmos antiguos.
- Mapeo explícito especie ↔ accesión.

## V10.4

- Optimización de rendimiento Windows + WSL.
- Entorno compartido en `~/.asistente_molecular/venv`.
- Caché fuera de OneDrive `/mnt/c`.
- Instalación solo cuando cambia `requirements.txt`.
- Streamlit sin file watcher.

## V10.5

- Botón para validar todos los paneles recomendados.
- Tabla resumen y ranking por cobertura.
- Descarga CSV/XLSX.

## V10.6

- Sinónimos de locus en consultas NCBI.
- Ej.: TEF1 / EF1-alpha; TUB2 / BenA.
- Mayor recuperación de registros específicos del locus.
- SAG, bibliografía e in silico separados.

## V10.7

- Tratamiento explícito de referencias parciales.
- F sin R o R sin F puede producir “No concluyente” en vez de falso 0 %.
- Diagnóstico por referencia.

## V10.8

- Profundización opcional con referencias genómicas para resultados no concluyentes.
- Matching IUPAC sobre referencias genómicas recuperadas temporalmente.

## V10.9

- Evaluación integrada de evidencia.
- Evidencia SAG + bibliografía + in silico + disponibilidad en laboratorio.
- Conflictos de evidencia marcados para validación experimental.
- Hoja `Evaluacion_evidencia_panel`.

## V10.10

- Reorganización completa de la interfaz en tres pestañas:
  - puntos 1–5;
  - puntos 6–7;
  - punto 8 en adelante.
- No modifica la lógica molecular de V10.9; mejora agilidad y navegación.

---

# 27. Flujo recomendado de trabajo real

Para una muestra sospechosa:

```text
1. Buscar especie/género sospechoso
        ↓
2. Confirmar taxonomía de referencia
        ↓
3. Revisar dificultad de discriminación
        ↓
4. Revisar marcadores originales
        ↓
5. Revisar panel reforzado si corresponde
        ↓
6. Priorizar panel SAG y/o disponible en laboratorio
        ↓
7. Revisar amplicón, Tm, Ta y referencias
        ↓
8. Validar in silico si aporta información
        ↓
9. Si no concluyente, mantener evidencia documental y decidir si profundizar
        ↓
10. PCR experimental
        ↓
11. Secuenciar amplicón
        ↓
12. Confirmar locus y taxonomía
        ↓
13. Escalar a multilocus o WGS cuando la especie sea compleja
```

---

# 28. Qué NO debe hacer el programa

El programa no debe:

- inventar primers;
- declarar un primer universal solo porque amplifica algunas especies;
- reemplazar evidencia experimental sólida por un fallo de recuperación de NCBI;
- interpretar “No concluyente” como “No amplifica”;
- confirmar una especie compleja por un único locus cuando la literatura exige multilocus/genómica;
- asumir que mejor BLAST = especie en grupos con especies crípticas o heterogeneidad intragenómica;
- considerar Tm calculada como Ta PCR garantizada;
- tratar disponibilidad de un primer en el laboratorio como prueba de validez científica.

---

# 29. Mantenimiento y respaldo

Antes de actualizar versión:

1. conservar una copia del ZIP anterior;
2. conservar una copia de `base_maestra.xlsx`;
3. no borrar `~/.asistente_molecular/venv` salvo que sea necesario;
4. mantener la caché salvo que exista una razón para invalidarla;
5. registrar cualquier nuevo primer con secuencia exacta, fuente y alcance taxonómico.

Para reconstruir completamente el entorno:

```bash
rm -rf ~/.asistente_molecular/venv
rm -f ~/.asistente_molecular/requirements.sha256
bash INICIAR_LINUX.sh
```

Para limpiar solo validaciones NCBI:

```bash
rm -rf ~/.asistente_molecular/cache/*
```

---

# 30. Resumen rápido

### Windows

```text
Extraer ZIP → doble clic INICIAR_WINDOWS_WSL.bat
```

### Linux / WSL manual

```bash
bash INICIAR_LINUX.sh
```

### Abrir app

```text
http://localhost:8501
```

### Detener

```text
Ctrl+C
```

### Regla principal de interpretación

> **La app organiza evidencia y ayuda a decidir qué analizar; la identificación final debe ser proporcional a la dificultad taxonómica y a la calidad de la evidencia experimental.**

