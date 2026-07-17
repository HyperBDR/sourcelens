# syntax=docker/dockerfile:1.6

# -----------------------------------------------------------------------------
# LensNode builder image
# -----------------------------------------------------------------------------

FROM python:3.12-slim-bookworm AS builder

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /opt/lensnode

RUN pip install \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST" \
        --timeout 120 \
        --retries 5 \
        uv \
    && python -m venv --without-pip /opt/venv

COPY pyproject.toml ./
COPY lensnode ./lensnode

RUN uv pip install \
        --python /opt/venv/bin/python \
        --index-url "$PIP_INDEX_URL" \
        --trusted-host "$PIP_TRUSTED_HOST" \
        . \
    && rm -rf /root/.cache /tmp/* \
    && find /opt/venv -type d -name __pycache__ -prune \
        -exec rm -rf {} +

# -----------------------------------------------------------------------------
# LensNode runtime image
# -----------------------------------------------------------------------------

FROM python:3.12-slim-bookworm AS runtime

ARG APT_MIRROR_URL=https://deb.debian.org/debian
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_NO_CACHE_DIR=1 \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv

WORKDIR /opt/lensnode

RUN set -eux; \
    sed -i \
        -e "s|http://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
        -e "s|https://deb.debian.org/debian|${APT_MIRROR_URL}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ripgrep; \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

COPY --from=builder /opt/venv /opt/venv
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["lensnode"]
