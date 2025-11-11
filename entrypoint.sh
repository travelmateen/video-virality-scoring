#!/usr/bin/env bash
set -e

# Allow overriding via env
APP_TYPE="${APP_TYPE:-streamlit}"
PORT="${PORT:-8501}"
WORKDIR="/app/ui"

cd ${WORKDIR} || exit 1

echo "Starting app (type=${APP_TYPE}, port=${PORT})"

if [ "${APP_TYPE}" = "streamlit" ]; then
  # Streamlit: expects a file like app.py — run streamlit with network binding
  # --server.enableCORS false is often needed when embedding or dev
  exec streamlit run app.py --server.port ${PORT} --server.address 0.0.0.0 --server.enableCORS false

elif [ "${APP_TYPE}" = "fastapi" ]; then
  # FastAPI: expects ASGI app in variable APP_MODULE (e.g. app:app)
  # Use uvicorn with --host 0.0.0.0
  exec uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT} --proxy-headers

elif [ "${APP_TYPE}" = "flask" ]; then
  # Flask: expects FLASK_APP env or APP_MODULE; use gunicorn for production
  # If you want the dev server change this line, but gunicorn is recommended
  # APP_MODULE example: app:app (module:file + variable)
  WORKERS=${GUNICORN_WORKERS:-2}
  exec gunicorn --bind 0.0.0.0:${PORT} --workers ${WORKERS} ${APP_MODULE}

else
  echo "Unknown APP_TYPE: ${APP_TYPE}. Supported: streamlit, fastapi, flask"
  exit 2
fi
