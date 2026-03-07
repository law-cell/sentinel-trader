# Stage 1: Build frontend
FROM node:20-slim AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim AS backend
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY run_api.py .
COPY rules.json .

# Copy frontend build from stage 1
COPY --from=frontend /app/web/dist ./web/dist

EXPOSE 8000
CMD ["python", "run_api.py"]
