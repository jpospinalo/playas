# Desarrollo y revisión de cambios

## Ramas y responsabilidades

Esta entrega se prepara en `corpus`; `main` conserva la versión de producción.

Para cada tarea, acordar el commit base de `corpus` actualizada y crear una rama
temporal; por ejemplo, `backend/validacion`, `frontend/busqueda` o
`infrastructure/arranque`. Cada rama contiene el repositorio completo: el prefijo
describe el trabajo, no restringe los archivos modificables.

Publicar los cambios en esa rama y abrir un pull request (PR) con `corpus` como
rama de destino. Antes de integrar, comprobar que los cinco trabajos de CI
finalicen correctamente y revisar el diff. La integración de `corpus` en `main`
requiere revisión y autorización separadas.

Retirar la rama de trabajo al completar la integración y confirmar que nadie la
sigue utilizando.
No eliminar ramas divergentes por su antigüedad: revisar sus commits exclusivos
y conservar una referencia recuperable antes de descartarlos.

## Alcance y criterios de diseño

- Preservar contratos API, datos, prompts y compatibilidad fuera de la tarea.
- Reutilizar módulos existentes; añadir una abstracción solo si resuelve un
  problema actual y verificable. No separar archivos únicamente por su longitud.
- Mantener ingesta, servicio y frontend en sus entornos respectivos.
- No mezclar limpieza documental, cambios funcionales y operaciones AWS.
- No ejecutar ingesta, reindexación, evaluación con LLM ni despliegues para
  comprobar una limpieza: tienen efectos o costos externos.
- Mantener documentación del comportamiento actual cerca del componente;
  conservar planes e informes de ejecución fuera del árbol de fuentes. El
  historial de código permanece en Git.

## Puntos de control

1. **Antes:** comprobar rama, commit base y cambios pendientes. Identificar los
   archivos permitidos y guardar el resultado de las pruebas iniciales. No
   sobrescribir trabajo ajeno ni actualizar dependencias incidentalmente.
2. **Durante:** probar cada corrección con casos deterministas, sin servicios
   reales cuando sea posible. Si solo cambian comentarios o formato Python,
   verificar también la equivalencia del AST ejecutable.
3. **Antes de integrar:** revisar `git diff --check`, archivos modificados,
   links documentales y pruebas del componente. No ocultar fallos preexistentes
   con skips ni eliminar pruebas vigentes para obtener un resultado verde.
4. **Cierre:** declarar qué se verificó, qué quedó fuera y cualquier limitación.
   Hacer pruebas de humo autorizadas si el cambio afecta flujos reales. No hacer
   commit, push, borrar ramas remotas ni operar AWS sin la autorización correspondiente.

## Controles locales

Utilizar Python 3.12 y uv 0.13.4, el perfil declarado en CI. Los locks se
versionan. Ejecutar `make install` desde `ingesta/` o `rag/`: primero comprueba
su frescura con `uv lock --check` sin `UV_FROZEN` y después sincroniza las
dependencias de desarrollo con `uv sync --frozen` (todo el workspace en RAG).
El comando modifica el entorno local y debe conservar el lock. Puede consultar
el registro y descargar dependencias; no es un control estrictamente offline.
`--frozen` conserva el lock durante la sincronización, pero no comprueba por
sí solo que corresponda a los manifiestos actuales.

En `ingesta/`: `make lint`, `make format-check`, `make test` y
`make test-integration`. Esta última suite comprueba contratos offline entre
etapas; no procesa el corpus ni utiliza AWS/LLM. `make typecheck` existe, pero
no forma parte de CI: registrar sus fallos por separado, sin suprimirlos.

En `rag/`: `make quality` reúne lint, formato, tipos, pruebas Python y controles
del frontend. Incluye un build y genera artefactos locales. Para evitar que
`uv run` modifique el lock durante los controles, usar `UV_FROZEN=1 make quality`
(o los targets individuales). Los comandos del frontend necesitan Bun.
`UV_FROZEN=1` impide actualizar el lock, pero no impide sincronizar el entorno
ni acceder a la red. Un control estrictamente offline debe usar dependencias
ya preparadas y declarar qué comandos ejecutó y qué artefactos generó.

Las pruebas de humo del RAG requieren configuración y servicios desplegados;
ver [SMOKE_TESTS.md](rag/docs/SMOKE_TESTS.md). La CI y los controles locales no
son necesariamente idénticos: consultar sus definiciones actuales.

## Nombres Unicode en macOS

Si Git muestra documentos con tildes como nuevos después de actualizar, no
borrarlos ni hacer `git add` masivo. Contrastar ruta normalizada y contenido
con el índice. `git -c core.precomposeunicode=false status --short` permite
diagnosticar este caso sin guardar una configuración. Solo ajustar la opción
local del repositorio si la equivalencia está verificada; no cambiar la
configuración global ni renombrar el corpus para ocultar diferencias.
