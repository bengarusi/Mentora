# One image, one service: the React build is baked in and served by FastAPI.
# See backend/app/asgi.py for why the API sits under /api and the SPA at /.

# ---- stage 1: build the SPA ----
FROM node:22-alpine AS frontend

WORKDIR /build

# Copied before the sources so a source-only change reuses the install layer.
# `npm ci` installs devDependencies too — vite and tsc are both build-time.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---- stage 2: the runtime ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Same layering reason as above: dependencies change far less often than code.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# The SPA lives outside the source tree in the image, so asgi.py is told where.
ENV FRONTEND_DIST_DIR=/srv/frontend/dist

# alembic.ini resolves its script location relative to the working directory.
WORKDIR /srv/backend

EXPOSE 8000
CMD ["/srv/docker-entrypoint.sh"]
