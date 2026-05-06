FROM python:3-slim

ARG HOST=0.0.0.0
ARG PORT=9600
ARG TRANSPORT="http"

ENV HOST=${HOST} \
    PORT=${PORT} \
    TRANSPORT=${TRANSPORT} \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:${PATH}" \
    UV_HTTP_TIMEOUT=3600 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1

RUN apt-get update \
    && apt-get install -y ripgrep tree fd-find curl nano \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && curl -sS https://starship.rs/install.sh | sh -s -- --yes \
    && mkdir -p /root/.config \
    && echo 'eval "$(starship init bash)"' >> /root/.bashrc \
    && uv pip install --system --upgrade --verbose --no-cache --break-system-packages --prerelease=allow scholarx[all]>=0.3.0

COPY starship.toml /root/.config/starship.toml

CMD ["scholarx-mcp"]
