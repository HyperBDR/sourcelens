FROM python:3.12-slim

ARG APT_MIRROR_URL=https://deb.debian.org/debian
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

WORKDIR /opt/lensnode

RUN set -eux; \
    echo "Using Debian mirror: ${APT_MIRROR_URL}"; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
            /etc/apt/sources.list; \
        sed -i "s|https://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
            /etc/apt/sources.list; \
    fi; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
            /etc/apt/sources.list.d/debian.sources; \
        sed -i "s|https://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
            /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ripgrep; \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY lensnode ./lensnode
COPY docker/entrypoint.sh /entrypoint.sh

RUN set -eux; \
    echo "Installing uv from ${PIP_INDEX_URL}"; \
    pip install \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST" \
        --timeout 120 \
        --retries 5 \
        uv; \
    echo "Using Python index: ${PIP_INDEX_URL}"; \
    uv pip install \
        --system \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST" \
        .; \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["lensnode"]
