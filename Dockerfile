FROM ghcr.io/astral-sh/uv:python3.13-alpine

EXPOSE 8000

WORKDIR /app

# TODO: copy only the necessary files
COPY . /app/

RUN uv sync

# Set the top-level directory to serve files from
# This is an example
ENV K0SNGIN_TOP_LEVEL=/app/example

CMD ["/app/.venv/bin/uvicorn", "k0sngin.main:app", "--port", "8000", "--host", "0.0.0.0"]
