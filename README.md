# ATLAS — Orientación normativa y jurisprudencial sobre playas

Sistema agéntico de orientación normativa y jurisprudencial sobre playas en Colombia.

Para consultar o evaluar la colección Gold A, empezar por
[Usar Gold A en ATLAS](rag/docs/DESPLIEGUE.md#usar-gold-a-en-atlas).

## Organización y documentación

| Directorio | Responsabilidad | Documentación |
|---|---|---|
| `rag/` | API, agente, frontend y evaluación | [RAG](rag/README.md) |
| `ingesta/` | Conversión, seccionado y enriquecimiento de documentos | [Ingesta](ingesta/README.md) |
| `vector-infraestructura/` | EC2 de ChromaDB y Ollama | [Infraestructura vectorial](vector-infraestructura/README.md) |
| `rag/infrastructure/` | ECS, ALB, ECR y EFS de la aplicación | [Infraestructura RAG](rag/infrastructure/README.md) |
| `ingesta/infrastructure/` | Bucket S3 de las capas del pipeline | [Scripts de ingesta](ingesta/docs/SCRIPTS.md#infraestructura-responsabilidades) |
| `data/` | Corpus versionado, inventario, campos de Gold y respaldos de ChromaDB | [Corpus y datos](data/README.md) |
| `scripts/` | Herramientas que coordinan varios componentes | [Despliegue desde bastion](rag/infrastructure/README.md#desplegar-desde-un-bastion) |

`rag/` e `ingesta/` son proyectos Python independientes, con sus propios
entornos y locks. El frontend utiliza Bun dentro del workspace de `rag/`.
No se necesita mover carpetas ni compartir un entorno para trabajar en ellos.
Para desarrollo local, empezar por el README del componente. Ver
[CONTRIBUTING.md](CONTRIBUTING.md) para ramas, alcance y controles de cambios.

## Operación en AWS

Los pasos de despliegue, encendido, apagado y respaldo de PostgreSQL están
reunidos en [Infraestructura RAG](rag/infrastructure/README.md).
La [recuperación de Gold A](data/chroma-releases/README.md) describe el
paquete, el perfil de embeddings y la verificación de la colección.

## Evaluación de calidad

La calidad de ATLAS se mide con [RAGAS](https://docs.ragas.io/) contra el ground truth del equipo jurídico. Resultados, informe para el equipo jurídico y registro de evaluaciones: [`rag/evaluation/README.md`](rag/evaluation/README.md#resultados-sobre-el-ground-truth-v02).

**Línea base vigente (corpus congelado, 2026-11-01, infraestructura local):** 52 de 65 respuestas correctas según el juez, fidelidad 0,88, evidencia recuperada 0,85, Factual F1 0,66 y Answer Accuracy 0,73. Frente a la corrida anterior no hay cambios medibles. El punto débil sigue siendo la normativa: REMAC 5 y Decreto 2324 no llegan a los 4 fragmentos en ninguno de 18 casos con la pregunta original. Detalle de la corrida y de la prueba en AWS con Claude en [`rag/evaluation/README.md`](rag/evaluation/README.md#prueba-en-aws-con-claude-no-reemplaza-la-línea-base).

### Qué se hizo en la rama `julian-rincon/evaluacion-ragas-linea-base`

Rama de trabajo sobre evaluación y recuperación, a partir de la línea base anterior. Todo se midió sobre los 66 casos del ground truth v0.2 con las métricas fijas sin LLM (`evaluation/metricas_sin_llm.py`); las notas del juez RAGAS de la tabla anterior son las de la línea base del 2026-11-01.

1. **Herramientas de evaluación:** ground truth v0.2 desde el Excel del equipo jurídico, métricas fijas sin LLM con IC 95 % y comparación contra la línea base, caché de generación reanudable, RAGAS con gpt-5-nano y registro versionado de cada corrida.
2. **Recuperación** (`core/retriever.py`, `core/territorio.py`): tokenizador español para BM25, fusión RRF c=2 con pesos 0,8 BM25 / 0,2 vectores, varias consultas fusionadas (original, autosuficiente y enriquecida), un fragmento por sentencia, prioridad territorial (no traer normas locales de otra ciudad) y jerarquía normativa (la norma antes que la jurisprudencia).
3. **Respuestas:** el prompt prohíbe nombrar normas que no estén en el contexto y ordena norma → jurisprudencia; las respuestas sin recuperación guían al usuario con ejemplos y con los datos que faltan (lugar, actividad, autoridad).
4. **Gold A corregido** (rama `corpus`, colección `rag_playas_gold_a_cc7bf44b54a9`) fusionado en la rama.
5. **QA y carga:** ~6.000 peticiones sin LLM (hasta 200 simultáneas) sin errores 5xx, validación y entradas hostiles correctas, y corrección de un agotamiento del pool de conexiones que producía 500 con más de 15 consultas simultáneas.
6. **`main` al día (2026-11-12):** se fusionó el registro con tipo de usuario y, al hacerlo, se corrigió que la columna nueva `users.user_type` no se creaba en bases ya existentes (login y endpoints autenticados daban 500); `init_db` ahora agrega las columnas opcionales que falten.

| Indicador (66 casos) | Línea base 2026-11-01 | Esta rama |
|---|---:|---:|
| Documento esperado en el top-4 de la búsqueda | 0,586 | **0,741** |
| Documento esperado en los fragmentos que llegan al modelo | 0,53 | **0,75–0,79** |
| Normativa en el top-4 con la pregunta original | 0 de 18 | **8 de 18** |
| Fuga territorial (norma local de otra ciudad) | 0,045 | **0** |
| Respuestas con referencias sin respaldo (generador Claude) | 12,3 % | **3,1 %** |

- **Gold A corregido:** con el mismo código y el mismo modelo, la búsqueda da exactamente lo mismo que con el Gold anterior; las respuestas cambian dentro del ruido del modelo local.
- **k=6 frente a k=4:** más evidencia hacia el modelo (0,754 → 0,786; artículos esperados 0,147 → 0,206) y, con Claude como generador y juez, 16 respuestas correctas frente a 11. El valor por defecto sigue en k=4.
- **Sigue débil:** multas y sanciones responden «evidencia insuficiente» por falta de cobertura en el corpus.

Cifras, condiciones y comandos de cada medición: [`rag/evaluation/README.md`](rag/evaluation/README.md#estado-al-2026-11-11-gold-a-corregido-mejoras-de-recuperación-y-qa-sin-juez). Arquitectura actual: [`rag/docs/ARCHITECTURE.md`](rag/docs/ARCHITECTURE.md).

![Indicadores de la línea base: corpus anterior frente a corpus congelado](rag/docs/img/linea-base/01-indicadores.png)

