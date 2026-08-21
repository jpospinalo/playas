# Pruebas de humo de la API

Estas pruebas validan el despliegue real sin crear conversaciones, modificar
Chroma ni reindexar documentos. Usan consultas independientes contra
`/api/query` y lecturas de `/api/health`.

Variables requeridas:

```bash
export RAG_SMOKE_API_URL="http://direccion-del-api"
export RAG_SMOKE_TOKEN="token-de-un-usuario-de-pruebas"
```

Ejecución:

```bash
uv run pytest tests/integration/test_api_smoke.py -m integration
```

El conjunto verifica rechazo de preguntas ajenas, aceptación de pesca y
turismo relacionados con playas, recuperación de fuentes y citas válidas.
