# Demo: ingreso autónomo de un documento nuevo (5 a 7 minutos)

Para quien presenta. No hace falta saber programar: cada paso es un comando que se
copia en la terminal (Git Bash en Windows o cualquier terminal en Linux/macOS),
desde la carpeta `ingesta/demo/`.

> Honestidad: el sistema compara su OCR con otro OCR (no con una transcripción humana)
> y nada de esto está validado por abogados. Las decisiones de la política son
> automáticas y conservadoras: ante la duda, el documento va a revisión humana.

## Qué se muestra

Un PDF escaneado que el sistema no conoce entra por un buzón en S3, pasa solo por
**bronce** (texto con OCR), **silver** (limpieza y metadatos con evidencia), **gold**
(fragmentos con cabecera), **embeddings** y **publicación**; una política decide si
es seguro publicarlo y, si lo es, la búsqueda lo encuentra con su cita. Un documento
defectuoso no entra: va a revisión o se rechaza con su motivo.

## Antes del día (una vez)

1. `cp demo.env.example demo.env` y revisar los valores (instancias, bucket, ruta de
   la clave `labsuser.pem` del laboratorio).
2. `python preparar_archivos.py --raw ../../data/documents/raw` (crea `archivos/`).
3. Ensayar todo el guion una vez (ver «Plan B»).

## El día del demo: lista de comprobación

- [ ] Laboratorio AWS iniciado («Start Lab») y credenciales nuevas en `~/.aws/credentials`.
- [ ] `./start_demo.sh` termina con «Listo» (enciende Ollama y el worker; 2–4 min).
- [ ] `./status.sh` muestra `atlas_demo_base = N fragmentos` y el buzón vacío.
- [ ] Si hay restos de un ensayo: `./reset_demo.sh --frio` (vuelve a la línea base y en frío).
- [ ] Ventana del plan B abierta (`reporte_demo.html`).

## Guion (tiempos reales medidos)

| Paso | Qué decir / hacer | Comando | Tiempo |
|---|---|---|---|
| 1 | Estado inicial: cuántos fragmentos tiene la colección | `./status.sh` | 10 s |
| 2 | Preguntar algo que solo cubre el documento nuevo: no aparece | `./preguntar.sh "¿Qué trámite deben seguir las solicitudes de concesión portuaria según el Decreto 474 de 2015?"` | 15 s |
| 3 | Subir el escaneado nuevo | `./upload.sh "archivos/Decreto 474 de 2015 - concesiones portuarias.pdf"` | 5 s |
| 4 | Ver en vivo las fases y la decisión con sus motivos | `./seguir.sh` (Ctrl+C al terminar) | ~40–60 s |
| 5 | Repetir la pregunta: ahora aparece el decreto con su cita | `./preguntar.sh "…"` | 15 s |
| 6 | Subir un documento defectuoso: va a revisión / se rechaza y NO entra | `./upload.sh "archivos/Escaneo degradado.pdf"` y `./seguir.sh` | ~20 s |
| 7 | Volver al estado inicial | `./reset_demo.sh` | 30 s |

Tiempos de referencia de la prueba real (OCR Tesseract y embeddings de Ollama en CPU,
sin caché): una norma digital de 17 fragmentos tarda ~21 s; una sentencia escaneada de
33 páginas y 110 fragmentos, ~3,5 min; los embeddings rinden 0,8–1,0 por segundo. Por
eso el demo en vivo usa un decreto escaneado de 3 páginas (~16 fragmentos).

Último ensayo completo (`ensayo_4.log`, en frío, tras los arreglos de revisión): arranque
23 s; decreto publicado con 16 fragmentos en 28,1 s de procesamiento (bronce/OCR 8,3 s,
embeddings 16,0 s), 45 s contando el sondeo de S3; escaneo degradado a revisión humana en
6,3 s (página OCR con confianza 51,9 < 70); reset de vuelta a 943 fragmentos en 18 s.
Guion completo, de `start_demo.sh` al reset: ~2 min 45 s.

**Caché:** `reset_demo.sh` sin opciones conserva las cachés de OCR y embeddings: volver
a subir el mismo PDF tarda segundos y NO es tiempo real. Para que el paso 4 sea en frío,
reiniciar con `./reset_demo.sh --frio` antes de empezar. La base de la colección se
construyó con una caché de embeddings calculada antes (es preparación, no parte del demo).

## Plan B (si algo tarda o falla en directo)

Mostrar `reporte_demo.html` (en esta carpeta, autocontenido, sin conexión): es una
corrida real del mismo guion con sus fases, decisiones, motivos y tiempos, y el log
completo en `ensayo_*.log`. Decir explícitamente que es una ejecución grabada.

## Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| «Credenciales AWS caducadas o ausentes» | El laboratorio expiró | Reiniciar el laboratorio y copiar las credenciales nuevas en `~/.aws/credentials` |
| «Cuenta … inesperada» | Credenciales de otra cuenta | Revisar `~/.aws/credentials`; el demo solo funciona en la cuenta del sandbox |
| `start_demo.sh` se queda esperando | Instancias detenidas por fin del laboratorio | Esperar 2–3 min; si no, `./status.sh` y repetir `./start_demo.sh` |
| «Ollama no responde» | El servicio de Ollama aún carga el modelo | Esperar 1 min y `./status.sh`; el worker reintenta solo |
| El documento no sale del buzón | El worker está parado o sin Tesseract | `./status.sh`; en el worker: `sudo systemctl restart atlas-intake`; `tesseract --list-langs` debe mostrar `spa` |
| `ssh` pide confirmar o falla | IP nueva del worker tras encender | Es normal la primera vez; la ruta de la clave está en `demo.env` |

## Qué NO hace el demo

No toca la aplicación desplegada ni sus colecciones (`rag_playas`): el worker publica
en su propio Chroma local, en colecciones `atlas_demo_*`. Integrar la colección ampliada
en la aplicación es una decisión aparte (ver `ingesta/docs/INTAKE.md`, «Despliegue
permanente en AWS»).
