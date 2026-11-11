# Referencia OCR: métricas y FASE 1

U es la transcripción automática de Unlimited-OCR mediante una conversión MLX
bf16 no oficial. **No está verificada.** Este procedimiento compara extracciones
automáticas; no establece fidelidad frente al contenido visible del PDF.

## Ejecución local

Desde la raíz del repositorio, en PowerShell:

```powershell
& ingesta/benchmarks/fidelidad/trabajo/venv/Scripts/python.exe -I -B ingesta/benchmarks/ocr_referencia/validar_u.py --calibrar
& ingesta/benchmarks/fidelidad/trabajo/venv/Scripts/python.exe -I -B ingesta/benchmarks/ocr_referencia/validar_u.py
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& ingesta/.venv/Scripts/python.exe -I -B -m pytest -p no:cacheprovider --confcutdir=ingesta/tests/unit --basetemp=ingesta/benchmarks/ocr_referencia/trabajo/pytest_fase1_local ingesta/tests/unit/test_ocr_referencia.py
& ingesta/.venv/Scripts/python.exe -I -B -m ruff check --no-cache ingesta/benchmarks/ocr_referencia/metricas.py ingesta/benchmarks/ocr_referencia/validar_u.py ingesta/tests/unit/test_ocr_referencia.py
& ingesta/.venv/Scripts/python.exe -I -B -m ruff format --check --no-cache ingesta/benchmarks/ocr_referencia/metricas.py ingesta/benchmarks/ocr_referencia/validar_u.py ingesta/tests/unit/test_ocr_referencia.py
```

`-I` aísla Python; `-B` evita bytecode fuera de las rutas de escritura. Las
pruebas no cargan el `conftest.py` general ni complementos de servicios. Su
directorio temporal es propio y está dentro de este benchmark. El programa
solo importa la biblioteca hermana y PyMuPDF local, sin red, LLM ni AWS. Nunca
ejecuta contenido de entrada. El modo `--calibrar` no abre entrada ni PDFs.
La FASE 1 termina con código 1 si hay discrepancias de integridad, después de
guardar los informes; no modifica los datos para hacer pasar la validación.

Las lecturas de corpus se limitan a `entrada/descomprimido/{mapping.csv,
paginas.csv,run_info.json,texto/,crudo/}`, al mapa de originales de fidelidad y
a sus PDFs por prefijo SHA256. No se accede a `data/`, `ingesta/ingest/` ni a
revisiones visuales. Los campos de mapping no pueden introducir rutas externas.

## Normalización compartida

`metricas.normalizar()` se aplica por igual a U y a la capa de texto, y puede
usarse en la FASE 3. Convierte a NFC, elimina CR, pasa a minúsculas y colapsa
espacios Unicode. Conserva puntuación textual, dígitos, tildes, viñetas privadas
y números aislados. No aplica NFKC ni arregla ligaduras o supuestos errores.

La unión de guiones se decide **antes de minúsculas**: entre letras, si después
del salto viene minúscula, elimina guion y salto (`protec-\nción`); si viene
mayúscula conserva el guion (`NACIONAL-\nARMANDA` → `nacional-armanda`). No une
rangos numéricos. Es una heurística, no un diccionario: puede unir un compuesto
real ante minúscula o conservar un corte tipográfico ante mayúscula. Se aplica
igual a todas las fuentes y no intenta adivinar palabras.

Elimina comentarios de página, form feed, etiquetas completas de paginación
en línea propia, y `Página N de M` en cualquier posición. Aplana HTML con un
analizador inerte: decodifica entidades, separa celdas y bloques por espacios,
mantiene el orden de las celdas y elimina etiquetas. Las imágenes se eliminan.
Solo se interpretan etiquetas completas de vocabulario HTML conocido con
atributos sintácticamente válidos. Se conserva como texto la puntuación literal
`<`, `>` y fragmentos defectuosos como `<A la policía…` sin cierre: no se deja
que un analizador HTML incompleto consuma el resto de una página de capa PDF.
Retira delimitadores comunes de Markdown (encabezados, negrita, cursiva,
tachado, código, citas, viñetas, reglas y separadores de tabla); de los enlaces
conserva la etiqueta. `|` se convierte siempre en espacio. No pretende ser un
renderizador completo de todas las extensiones de Markdown.

Los superíndices Unicode, HTML y LaTeX numéricos quedan como números aparte:
`2008³` → `2008 3`. Si la capa extrae `20083` no se corrige: se conserva esa
discrepancia. No se eliminan encabezados/pies del texto usado para CER/WER.

## Métricas y denominadores

- CER = distancia Levenshtein exacta entre caracteres / caracteres de referencia
  normalizada; WER usa palabras separadas por espacios. Pueden superar el 100%
  ante muchas inserciones o una capa parcial. La implementación Myers procede
  de `fidelidad/comparar.py` y se contrasta con un oráculo dinámico independiente.
- Recuperación y precisión de palabras usan la intersección de multiconjuntos,
  dividida respectivamente por palabras de referencia e hipótesis. Las copias
  adicionales no se consideran recuperaciones adicionales.
- Orden: LCS exacta de trigramas de palabras solapados y normalizados, dividida
  por trigramas de referencia; también se entrega su precisión inversa. Para
  textos cortos n=min(3, longitudes), con mínimo 1. El orden no es invariante
  ante errores/omisiones: un LCS bajo es solo indicio. No usa `difflib`.
- Críticos: regex para números, fechas numéricas y «N de mes de AAAA», radicados
  segmentados o de 21–23 dígitos, Artículo/Art. N, Ley N de AAAA y Decreto N de
  AAAA. Por categoría entrega recall en ambos sentidos, totales y listas de
  faltantes con multiplicidad. Las categorías se solapan: un año también es
  número. La coincidencia es textual normalizada; no equipara citas diferentes
  ni valida calendarios o validez jurídica.
- Ruido: multiconjunto de palabras sobrantes. Separa candidatos a encabezado/pie
  recurrente (líneas de hasta 250 caracteres, entre primeras/últimas 3 líneas
  no vacías, en al menos 3 páginas y el 30% del documento). Las etiquetas
  `Página N [de M]` se registran antes de eliminarlas; no se suman de nuevo a
  los extras. «Repetido» es una heurística de ubicación y frecuencia.
- Un denominador vacío produce `null`/celda vacía, nunca un cero o uno ficticio.

## Exclusiones y sospechas

Las páginas con `tope_alcanzado` o `repeticion` se declaran **NO CONFIABLES**,
aunque el detector adicional no las encuentre. Los marcadores ausentes o
ambiguos también impiden incluir una página; no se desplaza la numeración.

Detector adicional conservador, con evidencia exportada:

1. Línea normalizada de al menos 20 caracteres, al menos 5 copias y al menos
   30% de los caracteres de líneas no vacías de esa página.
2. Al menos 80 palabras; unión de posiciones cubiertas por n-gramas de 8 palabras
   con al menos 6 apariciones >=40% del texto. Además debe haber al menos 6
   copias consecutivas de un período de 1 a 80 palabras cubriendo >=40% del
   texto. Las ventanas solapadas no inflan la cobertura. La condición de
   consecutividad protege catálogos de circulares con fórmulas recurrentes.

Es un filtro de triaje: puede omitir bucles largos/dispersos o señalar contenido
repetitivo legítimo. No identifica con certeza truncamientos sin señal del
generador. La calibración incluye bucles con/sin saltos y controles de cita
duplicada, vocabulario diverso, fórmula jurídica y catálogo repetitivo.

Sospecha en páginas digitales: recuperación <85% (posible omisión), precisión
<85% (posible adición), o recall LCS <65% (posible desorden/errores). Se incluye
la igualdad en el lado aceptado. Un valor no definido también genera aviso.
Son umbrales operativos documentados; no están entrenados contra una revisión
visual ni estiman sensibilidad/especificidad real. No se ajustan a resultados
de revisión visual. Las siete páginas marcadas se conservan como exclusiones.

## Población y bootstrap

Páginas digitales: `caracteres_capa_texto_pdf >= 80` según `paginas.csv`. Se usa
`page.get_text()` sin reordenar columnas, y se registra también su longitud
actual y cualquier diferencia con el CSV. No se fuerza coincidencia entre
versiones de extracción. Las páginas sin capa suficiente quedan fuera del
contraste, incluidas muchas escaneadas; no se extrapolan estos resultados a ellas.

La capa también puede tener llamadas de nota pegadas a números, viñetas U+F0B7,
tablas extraídas por columnas o texto parcial. Una precisión baja puede deberse
a que U recupera contenido que falta en la capa; **no demuestra invención**.
Una coincidencia alta tampoco verifica la exactitud de ambas fuentes.

Los agregados son cocientes de sumas (micro), retirando páginas no confiables
y la fila con `duplicado_de`. El duplicado se contrasta y se entrega en el CSV
por página, pero jamás pesa dos veces. Sus metadatos de página se toman del
original declarado porque no tiene ejecución OCR propia.

Se estratifica por jurisprudencia/normativa, presencia de tabla HTML en U y
sus cruces. Se entregan IC95 percentil para CER, WER, recuperación y precisión:
2.000 remuestreos con reemplazo, semilla 27102026. En el bootstrap por página
se remuestrean páginas completas; por documento se remuestrean clústeres con
todas sus páginas elegibles del estrato. Numerador y denominador permanecen
juntos. Los percentiles interpolan linealmente entre posiciones. No son IC de
«verdad OCR» ni corrigen sesgo de selección o errores comunes entre fuentes.

## Calibración obligatoria

`--calibrar` y las pruebas sustituyen exactamente el entero más próximo al
0,5/1/3% de los caracteres normalizados. Seleccionan posiciones no blancas,
pero la dosis se calcula sobre TODOS los caracteres. U+FFFD debe estar ausente
del original y evita cambios de longitud o colapso de espacios; CER debe
recuperar exactamente la dosis efectiva. Se informa el redondeo. El borrado
de todos los dígitos debe generar CER positivo y recall crítico cero en las
seis categorías presentes. Se guardan esperados, observados y faltantes.

## Salidas

- `resultados/integridad.json`: huellas, páginas, correspondencia de archivos,
  secuencia de marcas, igualdad del duplicado y discrepancias sin reparación.
- `resultados/paginas_excluidas.csv`: página, motivo y evidencia del filtro.
- `resultados/u_vs_capa_texto.csv`: páginas digitales, incluido el duplicado y
  las excluidas, con columnas explícitas de inclusión, críticos y ruido en JSON.
- `resultados/u_sospechosas.csv`: avisos sin duplicados, con su condición de
  inclusión en los agregados; puede contener páginas ya excluidas.
- `resultados/resumen.json`: agregados, IC, umbrales, incidencias de longitudes
  de capa y diez peores páginas incluidas por CER descendente, desempate por WER.
- `resultados/informe_fase1.md`: informe legible con tablas y exclusiones.
- `resultados/calibracion.json`: evidencia reproducible de la calibración.
