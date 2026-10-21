# Maquetas de diseño v2 (estáticas)

Tres direcciones visuales para el rediseño del front de ATLAS, para elegir una antes de tocar la app real. No forman parte de la app: Next no las sirve ni las compila.

| Archivo | Dirección | Idea |
|---|---|---|
| `d1-valla-de-playa.html` | Valla de playa | Señalización de seguridad (verde = puede, azul = información/obligación, rojo = no puede). La respuesta es una valla. |
| `d2-carta-nautica.html` | Carta náutica | Código de color de las cartas náuticas; se entra eligiendo la playa en un esquema de la costa de Santa Marta. |
| `d3-tramite-guiado.html` | Trámite guiado | Patrón de servicio público (una pregunta por pantalla, veredicto grande, un aviso, pasos). |

Cada archivo muestra el inicio y, con `?estado=respuesta`, la respuesta. El contenido legal es de ejemplo.

Para verlas desde `rag/frontend` (las rutas al logo son relativas a `public/brand`):

```bash
python3 -m http.server 8194
# http://localhost:8194/maquetas/v2/d1-valla-de-playa.html
```
