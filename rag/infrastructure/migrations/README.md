# Migraciones de la base de datos (Postgres de ECS)

El backend no usa Alembic: al arrancar corre `Base.metadata.create_all`, que
crea las tablas que falten pero **nunca altera una tabla que ya existe**.
Estas migraciones hacen explícito y revisable lo que el backend crearía solo,
para correrlo antes del deploy, con copia de seguridad y con vuelta atrás.

## 2026-10-30_ejercicio_validacion

Lleva una base con el esquema de `main` (5 tablas: `users`, `conversations`,
`messages`, `feedback`, `message_feedback`) al esquema del panel y del
ejercicio de validación (19 tablas). **Solo agrega** 14 tablas y 7 índices; no
toca ni una columna de las 5 tablas existentes.

| Tabla nueva | Para qué |
|---|---|
| `exercise_profile` | Número de participante (P001…), tipo de usuario de playa, sede, organización |
| `account_status` | Cuenta activa o desactivada por el admin |
| `practice_account` | Cuentas de práctica que no cuentan para nada |
| `privacy_consent` | Autorización de datos (Ley 1581) |
| `validator_profile` | Comité: validación jurídica o costera |
| `question_number` | Número fijo de cada pregunta |
| `question_assignment` | Qué evaluador califica qué pregunta |
| `question_evaluation` | Calificación de la planilla (F1-F3, Ct, Cv, total, válida) |
| `evaluation_review`, `evaluation_comment` | Validación del comité y conversación con el evaluador |
| `pertinence_review` | Pertinencia marcada por gestión costera |
| `award_decision` | Ganadora elegida por el comité cuando hay empate |
| `exercise_setting` | Calendario y cierre del ejercicio |
| `admin_audit` | Historial de cambios del admin |

Las encuestas nuevas guardan `clarity` y dejan `tone`/`length` en `null`
dentro del JSON `feedback.ratings`: eso no cambia el esquema.

### Cómo se probó (local, 30-oct-2026)

Base con el esquema exacto de `main` (creada por el backend de `main`) y datos
sintéticos (3 usuarios, 4 conversaciones, 8 mensajes, 2 encuestas, 4 opiniones):

1. `up.sql` → esquema idéntico al que crea la rama desde cero (19 tablas, 0
   diferencias en columnas, tipos, nulos, índices y llaves). Datos viejos intactos.
2. `up.sql` otra vez → sin error (idempotente).
3. `down.sql` → esquema idéntico al de `main`, datos viejos intactos. También
   probado con las tablas nuevas llenas (2 calificaciones, 5 perfiles).
4. La rama corriendo encima de la base migrada: 45 llamadas a la API (panel,
   cuentas, aviso de datos, encuesta nueva, calificación, validación, premios,
   Excel y CSV), 0 fallas.

### Cómo correrla en producción (Camilo)

```bash
cd rag/infrastructure
./scripts/export_postgres.sh --bucket <bucket>          # 1. copia completa antes de nada
./migrations/aplicar_migracion.sh verificar migrations/2026-10-30_ejercicio_validacion   # 2. ver qué hay
./migrations/aplicar_migracion.sh up migrations/2026-10-30_ejercicio_validacion          # 3. crear tablas
./migrations/aplicar_migracion.sh verificar migrations/2026-10-30_ejercicio_validacion   # 4. deben ser 19
# 5. después, deploy normal con la imagen nueva (push_images.sh + deploy.sh)
```

Vuelta atrás: `aplicar_migracion.sh down ...` (pide escribir BORRAR). Borra
solo las 14 tablas nuevas y sus datos; las 5 originales quedan como estaban.

**Ojo con volver el código a `main` sin bajar nada:** el backend de `main` da
error 500 en `GET /api/admin/feedback` cuando ya hay encuestas del front nuevo
(sin tono ni largo). El resto de `main` sigue funcionando. Si hay rollback de
código, hay que contar con eso.

Para regenerar el SQL si cambian los modelos:
`cd rag && PYTHONPATH=backend uv run python infrastructure/migrations/generar_sql.py infrastructure/migrations/<carpeta>`
