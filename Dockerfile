# syntax=docker/dockerfile:1.6

# -----------------------------------------------------------------------------
# Backend builder image
# -----------------------------------------------------------------------------

FROM python:3.12-slim-bookworm AS backend-builder

SHELL ["/bin/bash", "-c"]

ARG APT_MIRROR_URL=https://deb.debian.org/debian
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Build tools and development headers stay in this disposable stage.
# gettext is required to compile Django message catalogs.
RUN set -eux; \
    sed -i \
        -e "s|http://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
        -e "s|https://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        gettext \
        libmagic-dev \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        pkg-config \
        zlib1g-dev; \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

RUN pip install \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST" \
        --timeout 120 \
        --retries 5 \
        uv \
    && python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv

WORKDIR /opt/backend

COPY backend /opt/backend
COPY pyproject.toml /opt/backend/

# Always install agentcore from the bundled, pinned submodules so image builds
# cannot drift to an unpinned Git ref.
RUN set -eux; \
    sed -i \
        -e 's#agentcore-metering @ git+https://github.com/cloud2ai/agentcore-metering.git#agentcore-metering @ file:///opt/backend/agentcore/agentcore-metering#' \
        -e 's#agentcore-task @ git+https://github.com/cloud2ai/agentcore-task.git#agentcore-task @ file:///opt/backend/agentcore/agentcore-task#' \
        -e 's#agentcore-notifier @ git+https://github.com/cloud2ai/agentcore-notifier.git#agentcore-notifier @ file:///opt/backend/agentcore/agentcore-notifier#' \
        pyproject.toml; \
    uv pip compile \
        pyproject.toml \
        -o requirements.txt \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST"; \
    uv pip install \
        --python /opt/venv/bin/python \
        -r requirements.txt \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST"

# In dev mode, overlay editable agentcore installs so volume-mounted source
# changes are picked up without rebuilding the image.
ARG DEV_MODE=0
RUN set -eux; \
    if [ "$DEV_MODE" = "1" ]; then \
        for d in /opt/backend/agentcore/*/; do \
            if [ -f "${d}pyproject.toml" ]; then \
                echo "Dev mode: installing ${d} as editable"; \
                (cd "$d" && uv pip install \
                    --python /opt/venv/bin/python \
                    --index-url "$PIP_INDEX_URL" \
                    --trusted-host "$PIP_TRUSTED_HOST" \
                    -e .); \
            fi; \
        done; \
    fi

# DJANGO_DEBUG is scoped to this build step because production-only settings
# require secrets that are unavailable while the image is built.
RUN DJANGO_DEBUG=true python manage.py compilemessages -l zh_Hans -l en \
    && rm -rf /root/.cache /tmp/* \
    && find /opt/venv -type d -name __pycache__ -prune \
        -exec rm -rf {} + \
    && find /opt/backend -type d -name __pycache__ -prune \
        -exec rm -rf {} + \
    && find /opt/backend/agentcore -type d -name build -prune \
        -exec rm -rf {} +

# -----------------------------------------------------------------------------
# Backend runtime image
# -----------------------------------------------------------------------------

FROM python:3.12-slim-bookworm AS backend

SHELL ["/bin/bash", "-c"]

ARG APT_MIRROR_URL=https://deb.debian.org/debian
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_NO_CACHE_DIR=1 \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv

# Keep only runtime tools and shared libraries. Git is used by datasource
# synchronization, curl by container health checks, and psql by operations.
RUN set -eux; \
    sed -i \
        -e "s|http://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
        -e "s|https://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        libmagic1 \
        postgresql-client; \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

ARG DEV_MODE=0
ENV DEV_MODE=${DEV_MODE}

WORKDIR /opt/backend

COPY --from=backend-builder /opt/venv /opt/venv
COPY --from=backend-builder /opt/backend /opt/backend

RUN mkdir -p \
        /var/cache/sourcelens \
        /var/log/celery \
        /var/log/gunicorn

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Keep the version stamp last so version-only changes reuse expensive layers.
ARG APP_VERSION=0.0.0
LABEL com.oneprocloud.sourcelens.version=$APP_VERSION

ENTRYPOINT ["/entrypoint.sh"]
