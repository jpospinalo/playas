# Fase 1 · Defecto 1: llamadas numéricas en páginas digitales

**Decisión: adoptar.** La validación confirma mejoras de CER, WER y recall
crítico, incluido número/año. Los IC95 de las diferencias pareadas excluyen
cero. No empeora el CER agregado ni el de ningún documento evaluado. Hay tres
páginas de validación con pequeños aumentos de CER frente a U; se detallan abajo.

Rama de trabajo: `feat/ingesta-autonoma`. Sin commits ni push.

## Implementación y fidelidad

- `EXTRACTOR_VERSION = "pymupdf-tesseract-spa-4"`.
- Solo en páginas digitales, spans con `flags & 1` y contenido exclusivamente
  numérico ASCII, admitiendo blancos en sus extremos. Los dígitos pasan a
  `⁰¹²³⁴⁵⁶⁷⁸⁹`, sin insertar blancos. Se usa el flag de PyMuPDF; no se añade
  la heurística de tamaño/línea base. Los 704 spans detectados se mapean completos.
- `rawdict` localiza los caracteres por bloque, línea y caja de palabra. La
  correspondencia textual debe ser exacta; una palabra ambigua se conserva.
- No se reconstruyen líneas desde `dict`: esa concatenación difiere del texto
  actual en **922/1.224 páginas**. Se reutiliza el ordenador de palabras de
  PyMuPDF mediante una vista con las mismas coordenadas, índices y longitudes
  Unicode. Su salida **sin sustituciones es byte-idéntica en 1.224/1.224 páginas**
  a `page.get_text("text", sort=True)`, con PyMuPDF **1.26.5**, fijado en el proyecto.
- En ejecución, cada página con candidatos exige esa igualdad previa y comprueba
  después que todas las diferencias sean sustituciones dígito→superíndice 1:1.
  Si falla una comprobación, conserva el texto previo. Sin candidatos devuelve
  directamente el texto actual. La selección y el procesamiento de OCR no cambian.

Se conservan los superíndices en **silver y gold**. NFC no los convierte en
dígitos ordinarios; se mantiene una posición Unicode por carácter y la limpieza
existente sigue produciendo su `offset_map`. Se comprueban todos los caracteres
de un ejemplo y los intervalos de sus chunks. Buscar la subcadena `2002` sigue
encontrando `2002⁴⁴`; `re.findall(r"\d+", "2002⁴⁴")` devuelve solo `2002`.
Los offsets del proyecto son posiciones Unicode, no posiciones de bytes UTF-8.

En Python los superíndices sí pertenecen a `\w`: no bastaba con confiar en `\d`.
Se adaptaron los límites de año/fecha, las llamadas en encabezados normativos y
las citas de artículos en `legal_metadata.py`, conservando evidencia literal del
bronce. Las llamadas quedan fuera de las capturas numéricas. `ARTICLE_RE` sigue
capturando `15` en `Artículo 15¹`. Se incrementó también la versión de metadatos
a `legal-metadata-4` para invalidar su caché; el normalizador no cambia.

## Auditoría del corpus completo

| Comprobación | Resultado |
|---|---:|
| PDF únicos / páginas | 53 / 1.224 |
| Ordenador sin sustituciones idéntico al extractor anterior | 1.224 / 1.224 |
| Páginas digitales | 920 |
| Digitales cambiadas | **322** |
| Digitales sin candidatos, byte-idénticas a runA | **598 / 598** |
| Spans numéricos / dígitos detectados y sustituidos | 704 / **1.259 de 1.259** |
| Páginas OCR byte-idénticas a runA | **304 / 304** |
| Cambios ajenos a dígito→superíndice, blancos incluidos | **0** |

Las comparaciones de bronce se hacen con `read_bytes()` y separadores binarios
de página, sin traducción de CRLF. También se verifica que la clasificación OCR
y las páginas con fallo OCR sean iguales entre ambas corridas.

## Medición contra U

Antes: `trabajo/corridas/runA/pdf/capas/bronze`.
Después: `C:/Users/Migue/Desktop/playas/.offline/d1/capas/bronze`.
OCR servido por la caché sembrada de runA para v4, sin invocar Tesseract.

Se usa `evaluar_fase5.py --paginas digital`, modo contenido del arnés existente,
**sin modificar `metricas.py` ni su normalización**. Se añade únicamente el
agregado de la categoría existente `numero`, que incluye años y llamadas.
Es recall de esa categoría completa, no un subconjunto nuevo de años elegido
después de observar resultados. Cada tasa suma numeradores y denominadores.
IC95 por remuestreo de documentos, 2.000 repeticiones, semilla **20261110**.
División fijada en `division_ajuste_validacion.json`; cobertura completa de las
páginas elegibles: ajuste **318/318**, validación **600/600**. Las otras dos
páginas digitales del corpus están excluidas por el arnés.

La decisión sobre el detector se tomó con ajuste. Se mantuvo el criterio del
flag y se ejecutó validación sin cambios posteriores al detector.

Todas las cifras de tasas e intervalos siguientes están expresadas en **%**.

| Conjunto | Métrica | Antes [IC95 documento] | Después [IC95 documento] |
|---|---|---:|---:|
| Ajuste: 318 páginas, 14 documentos | CER | 2,1669 [1,2203; 2,9801] | **2,1178 [1,1797; 2,9238]** |
| Ajuste | WER | 2,7615 [1,8489; 3,5489] | **2,2441 [1,4659; 2,9286]** |
| Ajuste | Recall crítico total | 92,5480 [89,2194; 95,8648] | **96,6835 [93,3034; 98,9616]** |
| Ajuste | Recall número/año | 92,2279 [88,4564; 95,6940] | **96,2829 [92,3106; 98,8976]** |
| Validación: 600 páginas, 20 documentos | CER | 0,5114 [0,2827; 0,7957] | **0,4765 [0,2425; 0,7552]** |
| Validación | WER | 1,4607 [1,1383; 1,8520] | **1,1004 [0,7369; 1,4941]** |
| Validación | Recall crítico total | 95,2459 [93,2751; 97,0914] | **98,2032 [96,8686; 98,9471]** |
| Validación | Recall número/año | 95,7204 [93,7665; 97,4806] | **98,6063 [97,4515; 99,2028]** |

Para decidir se calcula además la diferencia pareada **después − antes**:
se remuestrean los mismos documentos para ambas variantes y se mantienen sus
denominadores comunes. Los siguientes cambios e IC están en **puntos porcentuales**.

| Conjunto | Δ CER [IC95] | Δ WER [IC95] | Δ recall crítico [IC95] | Δ recall número/año [IC95] |
|---|---:|---:|---:|---:|
| Ajuste | −0,0492 [−0,0657; −0,0291] | −0,5174 [−0,6968; −0,3000] | +4,1355 [+2,2047; +5,6968] | +4,0550 [+2,2140; +5,4863] |
| Validación | **−0,0350 [−0,0549; −0,0151]** | **−0,3603 [−0,5696; −0,1569]** | **+2,9573 [+1,3614; +4,4846]** | **+2,8859 [+1,3147; +4,4141]** |

En número/año: ajuste pasa de **7.642/8.286** a **7.978/8.286**; validación,
de **13.599/14.207** a **14.009/14.207**, 410 coincidencias adicionales.
Las ediciones de caracteres de validación bajan de **8.630 a 8.040** sobre
1.687.465 caracteres de referencia.

La mejora no es uniforme por página: en ajuste, CER mejora en 119, queda igual
en 195 y empeora en 4; en validación, mejora en 180, queda igual en 417 y
empeora en 3. **Ningún documento empeora su CER agregado.** Las tres páginas
de validación con aumento son `93f6:24` (2→4 ediciones), `93f6:39` (4→5) y
`ea75:28` (20→21). U transcribe allí algunas llamadas como `”46`, `”54`, `”55`
o `”57`, sin marcado de superíndice; el número separado por la normalización
añade espacios frente a esa referencia. No se retocó U ni se añadieron
excepciones al detector para esos casos.

## Ejemplos verificables

Documento `39b9b682861845800f858579e6523aea2663612a56837b3c4811476681be0c3d`
(`…Lemus Orozco…`, conjunto de ajuste):

| Página | Antes | Después |
|---|---|---|
| 24 | `11 de enero de 200244.` | `11 de enero de 2002⁴⁴.` |
| 24 | `realizada en la misma fecha42.` | `realizada en la misma fecha⁴².` |
| 1 | `Gerardo Antenor Lemus Orozco1,` | `Gerardo Antenor Lemus Orozco¹,` |
| 26 | `entre el año 1992-200256.` | `entre el año 1992-2002⁵⁶.` |

`auditoria.json` conserva el resultado página a página y todos los ejemplos
de sustituciones; los JSON de evaluación conservan los conteos por página.

## Pruebas y reproducción

- PDF sintético real de PyMuPDF: fuente 12 para `2002`, fuente 7 y línea base
  elevada 4 puntos para `44`; la extracción anterior produce `200244` y el
  bronce corregido produce exactamente `2002⁴⁴`, con los demás bytes intactos.
  Desactivando `digital_text` en memoria, ese test **falla** con `200244` frente
  a `2002⁴⁴`; con la corrección pasa.
- Identidad binaria sin notas, con dígitos pequeños sobre la línea base y con
  superíndices no numéricos; dos apariciones iguales en distintas posiciones;
  exclusión de OCR; silver/gold, búsqueda y offsets; fecha, año, número y artículos.
- Suite completa Windows: **870 pasan, 12 omitidos, 5 fallos**. Los cinco son
  los conocidos: dos `ModuleNotFoundError: rag`, dos entrypoints bash y el test
  que exige Tesseract. Última ejecución focalizada: **508/508**.
- Calibración original: **64/64**, controles de bucles **12/12**. Ruff sin errores
  en los seis archivos Python modificados o añadidos.

Comandos PowerShell, desde `C:/Users/Migue/Desktop/playas`, con un directorio
de corrida nuevo y vacío. Se utilizó `.offline/d1` porque el entorno solo permite
escribir dentro del espacio de trabajo y temporales; esta ruta también evita
el problema de longitud de las rutas Windows. No se escribió en `herramientas`.

```powershell
$py = 'C:/Users/Migue/herramientas/venv-intake/Scripts/python.exe'
$b = 'ingesta/benchmarks/ocr_referencia'
$run = 'C:/Users/Migue/Desktop/playas/.offline/d1'
$out = "$b/resultados/defecto1"

& $py -I -X utf8 "$b/sembrar_cache_ocr.py" --referencia "$b/trabajo/corridas/runA/pdf/capas" --cache "$run/cache"
& $py -I -X utf8 "$b/capas_completas.py" --entrada C:/Users/Migue/r --layers-root "$run/capas" --cache "$run/cache" --extension pdf --cache-ocr-sembrada

# Ejecutar ajuste, fijar criterio; después ejecutar validación.
& $py -I -X utf8 "$b/evaluar_fase5.py" --conjunto ajuste --paginas digital --variante antes=bronce:trabajo/corridas/runA/pdf/capas/bronze --variante "despues=bronce:$run/capas/bronze" --salida $out
& $py -I -X utf8 "$b/evaluar_fase5.py" --conjunto validacion --paginas digital --variante antes=bronce:trabajo/corridas/runA/pdf/capas/bronze --variante "despues=bronce:$run/capas/bronze" --salida $out

& $py -I -X utf8 "$b/auditar_defecto1.py" --entrada C:/Users/Migue/r --antes "$b/trabajo/corridas/runA/pdf/capas" --despues "$run/capas" --salida "$out/auditoria.json" --metricas $out

Push-Location ingesta
& $py -X utf8 -m pytest -q --basetemp "$env:TEMP/d1-suite" -p no:cacheprovider
Pop-Location
```

La auditoría con `--metricas` también reproduce
`diferencias_pareadas.json` y ejecuta la calibración existente. Los artefactos
de medición no requieren conservar la caché local para su revisión.
