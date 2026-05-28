#!/bin/bash
set -e

# -----------------------------------------------------------------------------
# Project Entrypoint Script
# -----------------------------------------------------------------------------
# This script manages database health checks, migrations, static collection,
# and process startup for Django, Celery, Gunicorn, etc.
# -----------------------------------------------------------------------------

# --- Change to project directory ---
cd /opt/backend || { echo "Error: Cannot change to /opt/backend directory"; exit 1; }

# --- Global Variables ---
export PYTHONPATH=/opt/backend
export DJANGO_SETTINGS_MODULE=core.settings

LOG_BASE_DIR="/var/log/gunicorn"
ACCESS_LOG="${LOG_BASE_DIR}/gunicorn_access.log"
ERROR_LOG="${LOG_BASE_DIR}/gunicorn_error.log"
CELERY_LOG="/var/log/celery/celery.log"

WORKERS=${WORKERS:-1}
THREADS=${THREADS:-1}
REDIS_URL=${REDIS_URL:-redis://redis:6379/0}
DB_ENGINE=${DB_ENGINE:-sqlite}

# --- Ensure log directories exist ---
mkdir -p $LOG_BASE_DIR /var/log/celery
chmod -R 755 $LOG_BASE_DIR /var/log/celery


# --- Logging Helper ---
log() { echo -e "\033[1;36m[entrypoint]\033[0m $*"; }

# --- Database Health Check ---
wait_for_db() {
    log "Waiting for database engine: $DB_ENGINE"
    case "$DB_ENGINE" in
        mysql)
            HOST=${MYSQL_HOST:-localhost}
            PORT=${MYSQL_PORT:-3306}
            log "Waiting for MySQL at $HOST:$PORT..."
            until mysqladmin ping -h "$HOST" -P "$PORT" --silent; do
                sleep 2
            done
            log "MySQL is ready!"
            ;;
        postgresql|postgres)
            # In Docker Compose, use service name 'postgresql' as default host
            # For local development, use 'localhost'
            HOST=${POSTGRES_HOST:-postgresql}
            PORT=${POSTGRES_PORT:-5432}
            USER=${POSTGRES_USER:-postgres}
            DB=${POSTGRES_DB:-postgres}
            log "Waiting for PostgreSQL at $HOST:$PORT..."
            # pg_isready doesn't require authentication, just checks if server is accepting connections
            until pg_isready -h "$HOST" -p "$PORT" > /dev/null 2>&1; do
                sleep 2
            done
            log "PostgreSQL is ready!"
            ;;
        *)
            log "Using SQLite (no health check required)."
            ;;
    esac
}

# --- Django Management Tasks ---
run_migrations() {
    log "Running Django migrations..."
    python manage.py migrate --noinput

    log "Ensuring superuser exists..."
    DJANGO_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME:-admin}
    DJANGO_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-admin@example.com}
    DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-adminpassword}

    # Export environment variables for createsuperuser command
    # Django 3.0+ supports DJANGO_SUPERUSER_PASSWORD, DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL
    export DJANGO_SUPERUSER_USERNAME
    export DJANGO_SUPERUSER_EMAIL
    export DJANGO_SUPERUSER_PASSWORD

    # Use Django's createsuperuser command with --noinput flag
    # If user already exists, the command will fail (exit code != 0) and we ignore it
    # This ensures password won't be reset on container restart
    set +e
    python manage.py createsuperuser \
        --username "$DJANGO_SUPERUSER_USERNAME" \
        --email "$DJANGO_SUPERUSER_EMAIL" \
        --noinput > /dev/null 2>&1
    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log "Superuser \"$DJANGO_SUPERUSER_USERNAME\" created successfully"
    else
        log "Superuser \"$DJANGO_SUPERUSER_USERNAME\" already exists, skipping creation"
    fi
    set -e

    log "Registering periodic tasks to django_celery_beat..."
    python manage.py register_periodic_tasks || true
}

collect_static() {
    log "Collecting static files..."
    python manage.py collectstatic --noinput
}

# --- Process Starters ---
start_gunicorn() {
    log "Starting Gunicorn..."
    exec gunicorn core.wsgi:application \
        --name backend \
        --bind 0.0.0.0:8000 \
        --workers $WORKERS \
        --threads $THREADS \
        --worker-class gthread \
        --log-level info \
        --access-logfile $ACCESS_LOG \
        --error-logfile $ERROR_LOG
}

start_celery_worker() {
    log "Starting Celery worker..."

    # Get CPU count for default concurrency
    # For I/O-bound tasks, we can use higher concurrency
    CPU_COUNT=$(nproc 2>/dev/null || echo 4)

    # Default concurrency: use CPU count for I/O-bound tasks
    # Can be overridden by CELERY_CONCURRENCY environment variable
    DEFAULT_CONCURRENCY=${CELERY_CONCURRENCY:-$CPU_COUNT}

    log "Celery worker concurrency: $DEFAULT_CONCURRENCY (CPUs: $CPU_COUNT)"
    log "Graceful shutdown enabled: worker will wait for running tasks to complete (up to stop_grace_period)"

    # Celery worker will gracefully shutdown when receiving SIGTERM:
    # - Stops accepting new tasks
    # - Waits for currently running tasks to complete
    # - Docker stop_grace_period (600s) allows time for tasks to finish
    # - CELERY_TASK_ACKS_LATE=True ensures tasks are only acknowledged after completion
    exec celery -A core worker \
        --loglevel=${CELERY_LOG_LEVEL:-INFO} \
        --concurrency=$DEFAULT_CONCURRENCY \
        --max-tasks-per-child=${CELERY_MAX_TASKS_PER_CHILD:-1000} \
        --max-memory-per-child=${CELERY_MAX_MEMORY_PER_CHILD:-256000} \
        --logfile=/var/log/celery/worker.log
}

start_celery_beat() {
    log "Starting Celery beat with DatabaseScheduler..."
    exec celery -A core beat \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler \
        --loglevel=${CELERY_LOG_LEVEL:-INFO} \
        --logfile=/var/log/celery/beat.log
}

start_flower() {
    log "Starting Flower..."
    exec celery -A core flower \
        --port=${FLOWER_PORT:-5555} \
        --address=0.0.0.0 \
        --broker="$REDIS_URL" \
        --loglevel=${CELERY_LOG_LEVEL:-INFO} \
        --logfile=/var/log/celery/flower.log
}

start_development() {
    log "Starting Django development server (runserver)..."
    exec python manage.py runserver 0.0.0.0:8000
}

# --- Main Entrypoint ---
case "$1" in
    gunicorn)
        wait_for_db
        run_migrations
        collect_static
        start_gunicorn
        ;;
    celery)
        wait_for_db
        start_celery_worker
        ;;
    celery-beat)
        wait_for_db
        start_celery_beat
        ;;
    flower)
        start_flower
        ;;
    development)
        wait_for_db
        run_migrations
        collect_static
        start_development
        ;;
    *)
        exec "$@"
        ;;
esac
