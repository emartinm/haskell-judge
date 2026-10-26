# Development environment. Use it with "source config.sh":
#   - activates the virtualenv (venv/)
#   - loads the environment variables (development values in .env.dev, created the
#     first time and ignored by git: no secrets in the repository)
#   - starts PostgreSQL 16 (port 9010) and haskell-test-executor in Docker if needed

cd "$(dirname "${BASH_SOURCE[0]}")" || return

if [ ! -f .env.dev ]; then
    cat > .env.dev <<EOF
export DJANGO_DEVELOPMENT=1
export SECRET_KEY='$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")'
export PG_DB=postgres
export PG_USER=postgres
export PG_PASS='$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")'
export PG_SERVER=localhost
export PG_PORT=9010
export EXECUTOR_SOCKET=/tmp/hj-executor/executor.sock
EOF
    echo "Created .env.dev"
fi
. ./.env.dev
. venv/bin/activate

if ! docker ps --format '{{.Names}}' | grep -qx hj-postgres; then
    docker rm -f hj-postgres >/dev/null 2>&1
    echo "Starting PostgreSQL on port ${PG_PORT}..."
    docker run -d --name hj-postgres -e POSTGRES_PASSWORD="$PG_PASS" -p "127.0.0.1:${PG_PORT}:5432" postgres:16 >/dev/null
    until docker exec hj-postgres pg_isready -q; do sleep 1; done
fi

if ! docker ps --format '{{.Names}}' | grep -qx hj-executor; then
    if docker image inspect haskell-test-executor >/dev/null 2>&1; then
        docker rm -f hj-executor >/dev/null 2>&1
        echo "Starting haskell-test-executor on $EXECUTOR_SOCKET..."
        mkdir -p "$(dirname "$EXECUTOR_SOCKET")"
        # Same capabilities as in production (see docker/haskell-test-executor.service of the executor)
        docker run -d --name hj-executor --network none --cap-drop ALL \
            --cap-add SYS_ADMIN --cap-add NET_ADMIN --cap-add SETUID --cap-add SETGID --cap-add CHOWN \
            --cap-add DAC_OVERRIDE --cap-add FOWNER --cap-add SYS_CHROOT --security-opt apparmor=unconfined \
            -v "$(dirname "$EXECUTOR_SOCKET"):/run/haskell-test-executor" haskell-test-executor >/dev/null
    else
        echo "WARNING: no haskell-test-executor image; build it from its repository to submit solutions"
    fi
fi
