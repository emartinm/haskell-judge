# Guía de desarrollo

## Requisitos

- **Python 3.13** o posterior (es la versión de la integración continua).
- **Docker**, para ejecutar PostgreSQL y el ejecutor en contenedores desechables.
- La imagen **`haskell-test-executor`**, construida desde
  [su repositorio](https://github.com/emartinm/haskell-test-executor), para poder enviar
  soluciones y guardar problemas (que se validan con el ejecutor). Sin ella, el juez funciona
  pero muestra que el evaluador no está disponible. Las pruebas no la necesitan.

## Entorno

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
source config.sh
```

`config.sh` activa el entorno virtual, carga las variables de entorno y arranca, si no lo
están, dos contenedores:

- `hj-postgres`: PostgreSQL 16 en el puerto 9010 de localhost.
- `hj-executor`: el ejecutor, con los mismos permisos que en producción, escuchando en
  `/tmp/hj-executor/executor.sock` (solo si existe la imagen `haskell-test-executor`).

La primera vez crea `.env.dev` con una clave y una contraseña aleatorias (está en `.gitignore`,
no se sube al repositorio). Toda la configuración se lee de variables de entorno
(`lhaskell/lhaskell/settings_shared.py`, `settings_dev.py` y `settings_deploy.py`): con
`DJANGO_DEVELOPMENT` definida se usa la de desarrollo; sin ella, la de despliegue.

## Lanzar el servidor en local

```sh
source config.sh
cd lhaskell
python manage.py migrate
python manage.py createsuperuser
cd .. && ./launch.sh             # http://localhost:8000/haskell/
```

Para tener problemas con los que probar, crea una colección en la administración
(`/haskell/admin/`) e importa un ZIP de problemas (formato en el [README](README.md#problemas)),
o carga una copia de las colecciones con `import_collections` (ver
[DEPLOYMENT.md](DEPLOYMENT.md#copia-de-las-colecciones)).

## Calidad

Lo mismo que comprueba la integración continua:

```sh
./tests.sh       # pruebas con cobertura (debe ser 100 %); solo necesita PostgreSQL
./ruff.sh        # estilo y formato
./bandit.sh      # análisis de seguridad
```

Las pruebas simulan el ejecutor, así que no necesitan la imagen. La integración continua también
comprueba que no faltan migraciones (`makemigrations --check`).

## Editor

El editor (CodeMirror 6) está precompilado en
`lhaskell/judge/static/judge/js/haskell-editor.min.js`, generado a partir de `editor/`. Para
actualizarlo (por ejemplo, tras cambiar versiones en `editor/package.json`):

```sh
editor/build.sh      # usa la imagen oficial de Node en Docker; no hace falta instalar Node
```

En los PR de Dependabot no hace falta: la acción `Editor bundle` lo regenera y lo añade al propio
PR. En el resto de PR y en `main` comprueba que el fichero coincide con `editor/` y falla si se
ha olvidado regenerarlo.
