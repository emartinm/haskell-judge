# Despliegue

Learn Haskell se sirve bajo la ruta `/haskell/` de su dominio, detrás de un proxy inverso con TLS
(nginx) y con gunicorn gestionado por systemd. Puede compartir dominio y servidor con otras
aplicaciones Django (por ejemplo, [LearnSQL](https://github.com/emartinm/lsql) bajo `/sql/`).

Requisitos:
- Python 3.12 o posterior.
- PostgreSQL (datos del juez: problemas, usuarios, envíos…).
- [haskell-test-executor](https://github.com/emartinm/haskell-test-executor) instalado en la
  misma máquina (ver su `DEPLOYMENT.md`): el juez le envía el código por un socket Unix.
- Docker (para el ejecutor y para las copias de seguridad) y nginx.

Las plantillas están en `deploy/`. En los ejemplos, `<usuario>` es el usuario del sistema que
ejecuta el juez y `<base>` su directorio, con esta estructura:

```
<base>/app      este repositorio
<base>/venv     entorno virtual
<base>/env      configuración (deploy/env.example), legible solo por <usuario>
<base>/backups  copias de seguridad (deploy/backup.sh)
```

## Instalación

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
   - El formato es el de `EnvironmentFile` de systemd: `CLAVE=valor`, sin `export` ni comillas.
   - `JUDGE_BETA=1` muestra el aviso de versión beta en la barra de menú, el título de las
     páginas y la ayuda; con `JUDGE_BETA=0` (y reiniciando el servicio) desaparece.
3. **Base de datos**: crea en PostgreSQL el usuario `lhaskell`, con la contraseña `PG_PASS`
   del fichero anterior, y la base de datos `lhaskell` cuyo propietario sea ese usuario. Puede ser
   el mismo servidor de PostgreSQL que usen otras aplicaciones (con otra base de datos).
4. **Código y entorno virtual**:
   ```sh
   sudo -u <usuario> git clone https://github.com/emartinm/haskell-judge.git <base>/app
   sudo -u <usuario> python3 -m venv <base>/venv
   sudo -u <usuario> <base>/venv/bin/pip install --upgrade pip
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

## Actualizar

```sh
sudo <base>/app/deploy/update.sh            # solo si hay commits nuevos
sudo <base>/app/deploy/update.sh --force    # aunque no los haya
```

Hace `git pull`; si ha cambiado `requirements.txt`, actualiza `pip` e instala las dependencias;
aplica las migraciones, `collectstatic` y `check --deploy`; reinicia el servicio y comprueba que
la página de entrada responde. A mano:

```sh
sudo -u <usuario> git -C <base>/app pull
sudo -u <usuario> <base>/venv/bin/pip install --upgrade pip
sudo -u <usuario> <base>/venv/bin/pip install -r <base>/app/requirements.txt
sudo -u <usuario> <base>/app/deploy/manage.sh migrate
sudo -u <usuario> <base>/app/deploy/manage.sh collectstatic --noinput
sudo systemctl restart haskell-judge
```

## Copias de seguridad

### Copia completa

`deploy/backup.sh` guarda todo lo necesario para reconstruir el juez: la base de datos completa
(colecciones, problemas, usuarios, grupos, envíos…) volcada con `pg_dump`, la configuración
`<base>/env` y el commit desplegado. El juez sigue funcionando mientras tanto.

```sh
sudo <base>/app/deploy/backup.sh      # → <base>/backups/haskell-judge-<fecha>_<hora>.tar
```

- `pg_dump` y `pg_restore` se ejecutan en un contenedor temporal de la imagen `postgres:16`
  (variable `PG_IMAGE`: debe ser de la misma versión principal que el servidor de PostgreSQL),
  conectado con el usuario y la contraseña de `<base>/env`.
- Borra las copias de más de 92 días (`KEEP_DAYS`). El directorio se cambia con `BACKUP_DIR`.
- La copia contiene los secretos de `<base>/env` y datos personales de los estudiantes: solo la
  puede leer `BACKUP_OWNER` (por defecto, el usuario que ejecuta `sudo`), que puede llevársela a
  otra máquina, por ejemplo con `rsync`. Una copia que solo está en el servidor no sirve si
  falla el servidor.
- Se puede programar con cron (como root, indicando `BACKUP_OWNER`); termina con error si algo
  falla.

`deploy/restore.sh` **sustituye** la base de datos del juez por la de una copia. Antes guarda una
copia del estado actual (si tiene datos), pide confirmación (salvo con `--yes`), para el
servicio, carga el volcado, aplica las migraciones del código instalado y vuelve a arrancar y
comprobar el juez:

```sh
sudo <base>/app/deploy/restore.sh <base>/backups/haskell-judge-<fecha>_<hora>.tar
```

En un servidor nuevo: pasos 1 y 4 de la instalación (usuario, código y entorno virtual) y el
ejecutor; después `restore.sh`, que restaura `<base>/env` desde la copia y se detiene si no
puede conectar con la base de datos; paso 3 con la contraseña `PG_PASS` de ese `<base>/env`;
`restore.sh` de nuevo y, por último, los pasos 6 y 7 (servicio y nginx) y `collectstatic`.

### Copia de las colecciones

Solo los problemas, en el formato de importación del [README](README.md#problemas), para
llevarlos a otra instalación o restaurar alguna colección:

```sh
cd lhaskell
python manage.py export_collections colecciones.zip                                 # copia
python manage.py import_collections colecciones.zip                                 # simulación
python manage.py import_collections colecciones.zip --save --author <profesor>      # restaura
```

Genera un ZIP con un ZIP por colección (`01_<nombre>.zip`, `02_<nombre>.zip`…, en el orden de
la lista de colecciones), cada uno con su `collection.json` y un ZIP por problema con sus
enunciados, definiciones, plantilla, solución, tests (también los ocultos), extensiones y
límites. No incluye usuarios, grupos ni envíos.

`import_collections` carga todas las colecciones de la copia. Como en la administración, valida
antes cada solución de referencia con el ejecutor (también en la simulación) y no guarda nada si
alguna falla. Las colecciones cuyo nombre ya existe se omiten, así que se puede repetir. Con
`--author`, las colecciones y los problemas quedan a nombre de ese profesor (así aparecen en el
filtro de sus clases); sin él, no tienen autor. Para restaurar solo una colección, también se
puede descomprimir la copia e importar el ZIP de esa colección desde la administración.

Contiene las soluciones de referencia y los tests ocultos, así que el fichero se crea legible
solo por su propietario. En producción, con una ruta absoluta (`manage.sh` se ejecuta desde
`<base>/app/lhaskell`):

```sh
sudo -u <usuario> <base>/app/deploy/manage.sh export_collections <base>/colecciones-$(date +%F).zip
sudo -u <usuario> <base>/app/deploy/manage.sh import_collections <base>/colecciones-<fecha>.zip --save --author <profesor>
```

## Estudiantes

```sh
cd lhaskell
python manage.py create_users estudiantes.csv "Grupo A"          # simulación
python manage.py create_users estudiantes.csv "Grupo A" --save   # crea los usuarios
```

El CSV de la UCM debe tener las columnas `NOMBRE COMPLETO` («Apellidos, Nombre»),
`DOCUMENTO` y `CORREO`, separadas por comas (las demás columnas se ignoran). El usuario es la
parte del correo anterior a `@ucm.es` y la contraseña inicial, el documento. Los usuarios
existentes solo se añaden al grupo (no cambia su contraseña), así que se puede repetir la
importación o importar a un estudiante en varios grupos. Los grupos son las «clases»: los
profesores también deben pertenecer a sus grupos.

En producción, con el usuario del juez. El CSV contiene los documentos de identidad: déjalo
legible solo por ese usuario y bórralo al terminar.

```sh
sudo install -o <usuario> -m 600 estudiantes.csv <base>/estudiantes.csv
sudo -u <usuario> <base>/app/deploy/manage.sh create_users <base>/estudiantes.csv "Grupo A"          # simulación
sudo -u <usuario> <base>/app/deploy/manage.sh create_users <base>/estudiantes.csv "Grupo A" --save   # crea los usuarios
sudo rm <base>/estudiantes.csv
```

Para cambiar la contraseña de un estudiante: administración → Usuarios → el estudiante → «Cambiar
contraseña». Los estudiantes pueden cambiarla ellos mismos desde su menú.

## Convivencia con otras aplicaciones en el mismo dominio

Cada aplicación tiene su usuario del sistema, su directorio, su entorno virtual, su servicio, su
puerto local de gunicorn y su base de datos. Las cookies del juez (`haskell_sessionid`,
`haskell_csrftoken`, con ruta `/haskell/`) tienen nombres propios, así que no interfieren con
las de otras aplicaciones Django del mismo dominio.
