# Learn Haskell

Juez automático en Django para aprender programación funcional en Haskell: colecciones
de problemas, envíos con veredicto, clasificaciones y estadísticas. Está basado en el
juez de SQL [LearnSQL](https://github.com/emartinm/lsql) y se sirve bajo la ruta `/haskell/`
de su dominio, de modo que puede compartirlo con otras aplicaciones.

La compilación y ejecución segura del código de los alumnos la hace un servicio aparte,
[haskell-test-executor](https://github.com/emartinm/haskell-test-executor), al que el
juez llama por un socket Unix.

## Funcionalidad

- **Alumnos**: colecciones de problemas con su progreso y podio, página de problema con
  editor (CodeMirror 6) que marca los errores de GHC, tests de ejemplo, historial de
  envíos con la retroalimentación completa y clasificación por grupo.
- **Profesores**: administración de Django para colecciones y problemas (con enunciado
  en varios idiomas, tests visibles y ocultos, extensiones y límites), importación de
  problemas desde ZIP, clasificación con filtro de fechas y descarga ODS, estadísticas
  y alta masiva de alumnos desde el CSV de la UCM.
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
  feedback.py           mensajes al alumno y diagnósticos para el editor
  problem_io.py         validación de problemas e importación de ZIP
  queries.py            consultas agregadas (progreso, podio, clasificación, estadísticas)
  views.py, admin.py    vistas y administración
  management/commands/create_users.py   alta de alumnos desde CSV
  tests/                pruebas (el ejecutor se simula)
editor/                 fuente del editor CodeMirror 6 y script para generarlo
```

## Desarrollo

Requisitos: Python 3.13 o posterior, Docker y la imagen `haskell-test-executor`
(constrúyela desde su repositorio) para poder enviar soluciones.

```sh
python3 -m venv venv && venv/bin/pip install -r requirements.txt
source config.sh                 # entorno, PostgreSQL (puerto 9010) y ejecutor en Docker
cd lhaskell
python manage.py migrate
python manage.py createsuperuser
cd .. && ./launch.sh             # http://localhost:8000/haskell/
```

`config.sh` crea la primera vez `.env.dev` con una clave y una contraseña aleatorias
(no se sube al repositorio).

Calidad (lo mismo que comprueba la integración continua):

```sh
./tests.sh       # pruebas con cobertura (debe ser 100 %); solo necesita PostgreSQL
./ruff.sh        # estilo y formato
./bandit.sh      # análisis de seguridad
```

El editor está precompilado en `lhaskell/judge/static/judge/js/haskell-editor.min.js`.
Para actualizarlo (cambiar versiones en `editor/package.json`): `editor/build.sh`
(usa la imagen oficial de Node en Docker; no hace falta instalar Node).

## Problemas

Se crean desde la administración (`/haskell/admin/`) o se importan en ZIP desde una
colección (campo «Añadir problemas desde ZIP»: un ZIP de problema o un ZIP con varios).
El ZIP con varios problemas puede incluir también un `collection.json` con
`{"name": "...", "description": "...", "position": 3}` (descripción en Markdown y posición,
opcionales): al importarlo, el nombre, la descripción y la posición de la colección se toman de
ahí, aunque en el formulario se haya escrito otra cosa.

Formato del ZIP de un problema (todo en UTF-8):

| Fichero | Contenido |
|---|---|
| `problem.json` | `{"title": "Suma" \| {"es": "Suma", "en": "Sum"}, "position": 1, "extensions": ["LambdaCase"], "limits": {"time_per_test_ms": 1000}}` (solo `title` es obligatorio) |
| `statement.md` | Enunciado en español (Markdown) |
| `statement.en.md` | Enunciado en otro idioma (opcional) |
| `definitions.hs` | Definiciones del profesor que importa la solución del alumno (opcional) |
| `template.hs` | Código inicial del editor (opcional) |
| `solution.hs` | Solución de referencia: debe superar todos los tests |
| `tests.json` | `[{"expr": "total [1,2,3]", "expected": "6", "hidden": false}, ...]` |

- Cada test compara con `==` una expresión con su valor esperado (de una sola línea).
- Si el alumno redefine un nombre del Prelude, el test debe cualificarlo: `Student.sum [1,2]`.
- Límites admitidos (vacío = valor por defecto del ejecutor): `time_per_test_ms`
  (100–10000), `alloc_per_test_mb` (10–40000), `heap_mb` (16–1024), `stack_mb`
  (1–1024), `run_time_s` (0,1–60).

## Alumnos

```sh
cd lhaskell
python manage.py create_users alumnos.csv "Grupo A"          # simulación
python manage.py create_users alumnos.csv "Grupo A" --save   # crea los usuarios
```

El CSV de la UCM debe tener las columnas `NOMBRE COMPLETO` («Apellidos, Nombre»),
`DOCUMENTO` y `CORREO`, separadas por comas (las demás columnas se ignoran). El usuario es la
parte del correo anterior a `@ucm.es` y la contraseña inicial, el documento. Los usuarios
existentes solo se añaden al grupo (no cambia su contraseña), así que se puede repetir la
importación o importar a un alumno en varios grupos. Los grupos son las «clases»: los
profesores también deben pertenecer a sus grupos.

En producción, con el usuario del juez. El CSV contiene los documentos de identidad: déjalo
legible solo por ese usuario y bórralo al terminar.

```sh
sudo install -o <usuario> -m 600 alumnos.csv <base>/alumnos.csv
sudo -u <usuario> <base>/app/deploy/manage.sh create_users <base>/alumnos.csv "Grupo A"          # simulación
sudo -u <usuario> <base>/app/deploy/manage.sh create_users <base>/alumnos.csv "Grupo A" --save   # crea los usuarios
sudo rm <base>/alumnos.csv
```

Para cambiar la contraseña de un alumno: administración → Usuarios → el alumno → «Cambiar
contraseña». Los alumnos pueden cambiarla ellos mismos desde su menú.

## Despliegue

Requisitos: Python 3.12 o posterior, PostgreSQL, un proxy inverso con TLS (nginx) y
[haskell-test-executor](https://github.com/emartinm/haskell-test-executor) instalado en la
misma máquina. Las plantillas están en `deploy/`; en los ejemplos, `<usuario>` es el usuario
del sistema que ejecuta el juez y `<base>` su directorio, con esta estructura:

```
<base>/app    este repositorio
<base>/venv   entorno virtual
<base>/env    configuración (deploy/env.example), legible solo por <usuario>
```

1. **Usuario** del sistema, sin sesión ni contraseña:
   ```sh
   sudo adduser --system --group --home <base> --shell /usr/sbin/nologin <usuario>
   ```
2. **Configuración** con claves aleatorias (completa los valores de `deploy/env.example`:
   nombre del servidor, puerto local de gunicorn y conexión a PostgreSQL):
   ```sh
   sudo -u <usuario> sh -c 'umask 077; cat > <base>/env' <<EOF
   ALLOWED_HOSTS=...
   GUNICORN_BIND=127.0.0.1:...
   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
   PG_DB=lhaskell
   PG_USER=lhaskell
   PG_PASS=$(openssl rand -hex 24)
   PG_SERVER=...
   PG_PORT=...
   EXECUTOR_SOCKET=/run/haskell-test-executor/executor.sock
   SENTRY_DSN=
   JUDGE_BETA=1
   EOF
   ```
   `JUDGE_BETA=1` muestra el aviso de versión beta en la barra de menú, el título de las
   páginas y la ayuda; con `JUDGE_BETA=0` (y reiniciando el servicio) desaparece.
3. **Base de datos**: crea en PostgreSQL el usuario `lhaskell`, con la contraseña `PG_PASS`
   del fichero anterior, y la base de datos `lhaskell` cuyo propietario sea ese usuario.
4. **Código y entorno virtual**:
   ```sh
   sudo -u <usuario> git clone https://github.com/emartinm/haskell-judge.git <base>/app
   sudo -u <usuario> python3 -m venv <base>/venv
   sudo -u <usuario> <base>/venv/bin/pip install -r <base>/app/requirements.txt
   ```
5. **Base de datos, estáticos y comprobaciones** (`deploy/manage.sh` ejecuta `manage.py` con la
   configuración de `<base>/env`):
   ```sh
   sudo -u <usuario> <base>/app/deploy/manage.sh migrate
   sudo -u <usuario> <base>/app/deploy/manage.sh collectstatic --noinput
   sudo -u <usuario> <base>/app/deploy/manage.sh check --deploy
   sudo -u <usuario> <base>/app/deploy/manage.sh createsuperuser
   ```
6. **Servicio**: adapta `deploy/haskell-judge.service.example` (usa `deploy/gunicorn.conf.py`
   y da acceso al socket del ejecutor), cópialo a `/etc/systemd/system/haskell-judge.service` y
   `sudo systemctl daemon-reload && sudo systemctl enable --now haskell-judge`.
7. **nginx**: añade `deploy/nginx.conf.example`, adaptado, al bloque `server` de HTTPS del
   dominio y después `sudo nginx -t && sudo systemctl reload nginx`.

**Actualizar** a una versión nueva: `sudo <base>/app/deploy/update.sh` hace todos los pasos
(solo si hay commits nuevos; `--force` para repetirlos) y comprueba que el juez responde. A mano:
```sh
sudo -u <usuario> git -C <base>/app pull
sudo -u <usuario> <base>/venv/bin/pip install -r <base>/app/requirements.txt
sudo -u <usuario> <base>/app/deploy/manage.sh migrate
sudo -u <usuario> <base>/app/deploy/manage.sh collectstatic --noinput
sudo systemctl restart haskell-judge
```

Las cookies (`haskell_sessionid`, `haskell_csrftoken`, con ruta `/haskell/`) tienen nombres
propios, así que no interfieren con otras aplicaciones Django del mismo dominio.

## Licencia

[MIT](LICENSE)
