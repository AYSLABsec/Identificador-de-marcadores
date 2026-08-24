# Asistente molecular Nanopore - Streamlit

Prototipo que utiliza `base_maestra.xlsx` como única autoridad para taxonomía, marcadores moleculares y primers.

## Qué hace

- Acepta una descripción libre de un microorganismo sospechoso.
- Busca taxones dentro de las 331 entradas de la base maestra.
- Permite filtrar por grupo, clado, orden y familia.
- Muestra Grupo → Clado → Clase → Orden → Familia → Género → Especie.
- Recupera únicamente los marcadores que estaban autorizados en el Excel original.
- Muestra secuencias 5'→3' y enlaces a las referencias presentes en `Catalogo_partidores`.
- No propone un primer de una familia distinta solo porque amplifique el mismo locus.
- Permite descargar un resumen del flujo en TXT.

## Ejecutar

```bash
python -m pip install -r requirements.txt
streamlit run Identificador_Marcadores.py
```

La aplicación espera que `base_maestra.xlsx` esté en la misma carpeta. También permite cargar otra versión compatible desde la barra lateral.

## Importante

La base actual no contiene un repertorio fenotípico completo (Gram, pigmentación, hospedero, síntomas, metabolismo, etc.). Por eso el texto libre sirve principalmente para detectar nombres taxonómicos y sinónimos presentes en el catálogo. Para inferir taxones desde fenotipo se necesitará una tabla adicional de rasgos o un módulo de conocimiento explícitamente validado.

Las secuencias de primers se muestran solo cuando existen en `Catalogo_partidores`. Un primer publicado no se etiqueta como validado para toda una familia salvo que la base lo indique; la cobertura final debe verificarse in silico y experimentalmente.
