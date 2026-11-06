# Learn Haskell

Juez automático en Django para aprender programación funcional en Haskell: colecciones
de problemas, envíos con veredicto, clasificaciones y estadísticas. Está basado en el
juez de SQL [LearnSQL](https://github.com/emartinm/lsql) y se sirve bajo la ruta `/haskell/`
de su dominio, de modo que puede compartirlo con otras aplicaciones.

La compilación y ejecución segura del código de los estudiantes la hace un servicio aparte,
[haskell-test-executor](https://github.com/emartinm/haskell-test-executor), al que el
juez llama por un socket Unix.

Documentación relacionada:
- [DEVELOPMENT.md](DEVELOPMENT.md): entorno de desarrollo, pruebas y editor.
- [DEPLOYMENT.md](DEPLOYMENT.md): despliegue, actualización, copias de seguridad y alta de
  estudiantes en producción.

## Funcionalidad

- **Estudiantes**: colecciones de problemas con su progreso y podio, página de problema con
  editor (CodeMirror 6) que marca los errores de GHC, tests de ejemplo, historial de
  envíos con la retroalimentación completa y clasificación por grupo.
- **Profesores**: administración de Django para colecciones y problemas (con enunciado
  en varios idiomas, tests visibles y ocultos, extensiones y límites), importación de
  problemas desde ZIP, clasificación con filtro de fechas y descarga ODS, estadísticas
  y alta masiva de estudiantes desde el CSV de la UCM.
- **Validación al guardar**: un problema solo se guarda si su solución de referencia
  supera todos los tests en el ejecutor.
- Los fallos del ejecutor (parado, cola llena…) no se guardan como envíos: no cuentan
  como intentos.

## Estructura

```
lhaskell/lhaskell/      configuración de Django (settings_shared/dev/deploy, urls)
lhaskell/judge/         la aplicación
  models.py             Collection, Problem, Statement, ProblemTest, Submission
  executor.py           cliente de haskell-test-executor
  feedback.py           mensajes al estudiante y diagnósticos para el editor
  problem_io.py         validación de problemas e importación/exportación de ZIP
  queries.py            consultas agregadas (progreso, podio, clasificación, estadísticas)
  views.py, admin.py    vistas y administración
  management/commands/create_users.py         alta de estudiantes desde CSV
  management/commands/export_collections.py   copia de seguridad de las colecciones
  management/commands/import_collections.py   restauración de esa copia
  tests/                pruebas (el ejecutor se simula)
editor/                 fuente del editor CodeMirror 6 y script para generarlo
deploy/                 scripts y plantillas de despliegue (ver DEPLOYMENT.md)
```

## Desarrollo

Requisitos: Python 3.13 o posterior, Docker y la imagen `haskell-test-executor`
(constrúyela desde su repositorio) para poder enviar soluciones. Los detalles están en
[DEVELOPMENT.md](DEVELOPMENT.md).

```sh
python3 -m venv venv && venv/bin/pip install -r requirements.txt
source config.sh                 # entorno, PostgreSQL y ejecutor en Docker
cd lhaskell
python manage.py migrate
python manage.py createsuperuser
cd .. && ./launch.sh             # http://localhost:8000/haskell/
```

Calidad (lo mismo que comprueba la integración continua):

```sh
./tests.sh       # pruebas con cobertura (debe ser 100 %); solo necesita PostgreSQL
./ruff.sh        # estilo y formato
./bandit.sh      # análisis de seguridad
```

## Problemas

Se crean desde la administración (`/haskell/admin/`) o se importan en ZIP desde una
colección (campo «Añadir problemas desde ZIP»: un ZIP de problema o un ZIP con varios).
El ZIP con varios problemas puede incluir también un `collection.json` con
`{"name": "...", "description": "...", "position": 3, "visible": true}` (descripción en Markdown,
posición y visibilidad, opcionales): al importarlo, el nombre, la descripción, la posición y la
visibilidad de la colección se toman de ahí, aunque en el formulario se haya escrito otra cosa.

Formato del ZIP de un problema (todo en UTF-8):

| Fichero | Contenido |
|---|---|
| `problem.json` | `{"title": "Suma" \| {"es": "Suma", "en": "Sum"}, "position": 1, "extensions": ["LambdaCase"], "limits": {"time_per_test_ms": 1000}}` (solo `title` es obligatorio) |
| `statement.md` | Enunciado en español (Markdown) |
| `statement.en.md` | Enunciado en otro idioma (opcional) |
| `definitions.hs` | Definiciones del profesor que importa la solución del estudiante (opcional) |
| `template.hs` | Código inicial del editor (opcional) |
| `solution.hs` | Solución de referencia: debe superar todos los tests |
| `tests.json` | `[{"expr": "total [1,2,3]", "expected": "6", "hidden": false}, ...]` |

- Cada test compara con `==` una expresión con su valor esperado (de una sola línea).
- Si el estudiante redefine un nombre del Prelude, el test debe cualificarlo: `Student.sum [1,2]`.
- Límites admitidos (vacío = valor por defecto del ejecutor): `time_per_test_ms`
  (100–10000), `alloc_per_test_mb` (10–40000), `heap_mb` (16–1024), `stack_mb`
  (1–1024), `run_time_s` (0,1–60).

Para hacer una copia de todas las colecciones en este formato y restaurarla, ver
`export_collections` e `import_collections` en [DEPLOYMENT.md](DEPLOYMENT.md#copia-de-las-colecciones).

## Despliegue

Requisitos: Python 3.12 o posterior, PostgreSQL, un proxy inverso con TLS (nginx) y
[haskell-test-executor](https://github.com/emartinm/haskell-test-executor) en la misma máquina.
La instalación, la actualización (`deploy/update.sh`), las copias de seguridad
(`deploy/backup.sh` y `deploy/restore.sh`) y el alta de estudiantes desde el CSV de la UCM están
en [DEPLOYMENT.md](DEPLOYMENT.md).

## Licencia

[MIT](LICENSE)
