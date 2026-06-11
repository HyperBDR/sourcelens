# Use official Python 3.12 on Ubuntu 24.04 LTS
FROM ubuntu:24.04 AS backend

SHELL ["/bin/bash", "-c"]

ARG DEV_MODE=0
ARG APT_MIRROR_URL=http://archive.ubuntu.com/ubuntu
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    DEV_MODE=${DEV_MODE} \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

# Install ca-certificates first to avoid SSL certificate issues
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates

# Setup mirrors before installing the rest of the packages
RUN set -eux; \
    echo "Using Ubuntu mirror: ${APT_MIRROR_URL}"; \
    printf '%s\n' \
        "deb ${APT_MIRROR_URL} noble main restricted universe multiverse" \
        "deb ${APT_MIRROR_URL} noble-updates main restricted universe multiverse" \
        "deb ${APT_MIRROR_URL} noble-backports main restricted universe multiverse" \
        "deb ${APT_MIRROR_URL} noble-security main restricted universe multiverse" \
        > /etc/apt/sources.list; \
    apt-get update

# Install Python 3.12, pip and system dependencies in one step
# libmagic is for python-magic which is a library for file type detection
# gettext is for Django i18n (makemessages, compilemessages)
# postgresql-client is for PostgreSQL database support
RUN apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3-pip \
    build-essential \
    git \
    curl \
    libpq-dev \
    postgresql-client \
    pkg-config \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libmagic1 \
    libmagic-dev \
    gettext \
    procps \
    htop \
    net-tools \
    iputils-ping \
    dnsutils \
    # PostgreSQL is the recommended database (postgresql-client, libpq-dev)
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Disable externally-managed-environment restriction for container environment
RUN rm -f /usr/lib/python3.12/EXTERNALLY-MANAGED

# Set working directory
WORKDIR /opt/backend

# Copy project files
COPY backend /opt/backend
COPY pyproject.toml /opt/backend/

# Install uv and project dependencies using the preselected index settings
RUN set -eux; \
    echo "Installing uv from ${PIP_INDEX_URL}"; \
    pip install \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST" \
        --timeout 120 \
        --retries 5 \
        uv; \
    echo 'export PATH="/root/.local/bin:$PATH"' >> /root/.bashrc; \
    export PATH="/root/.local/bin:$PATH"; \
    if [ "$DEV_MODE" = "1" ]; then \
        sed -i \
            -e 's#agentcore-metering @ git+https://github.com/cloud2ai/agentcore-metering.git#agentcore-metering @ file:///opt/backend/agentcore/agentcore-metering#' \
            -e 's#agentcore-task @ git+https://github.com/cloud2ai/agentcore-task.git#agentcore-task @ file:///opt/backend/agentcore/agentcore-task#' \
            -e 's#agentcore-notifier @ git+https://github.com/cloud2ai/agentcore-notifier.git#agentcore-notifier @ file:///opt/backend/agentcore/agentcore-notifier#' \
            pyproject.toml; \
    fi; \
    echo "Using Python index: ${PIP_INDEX_URL}"; \
    uv pip compile pyproject.toml -o requirements.txt --index-url "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST"; \
    uv pip install --system -r requirements.txt --index-url "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST"

# In dev mode, reinstall agentcore packages as editable so that volume-mapped
# source changes are picked up without rebuilding the image.
RUN set -eux; \
    if [ "$DEV_MODE" = "1" ]; then \
        export PATH="/root/.local/bin:$PATH"; \
        for d in /opt/backend/agentcore/*/; do \
            if [ -f "${d}pyproject.toml" ]; then \
                echo "Dev mode: installing ${d} as editable"; \
                (cd "$d" && uv pip install --system -e . --index-url "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST"); \
            fi; \
        done; \
    fi

# Compile Django message catalogs (.po -> .mo) so runtime gettext works
RUN python manage.py compilemessages -l zh_Hans -l en

# Create necessary directories
RUN mkdir -p /var/log/gunicorn /var/log/celery /var/cache/sourcelens

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set default command
ENTRYPOINT ["/entrypoint.sh"]
