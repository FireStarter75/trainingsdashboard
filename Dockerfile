# meerfasen: eerst de webapp bouwen (node), dan de bekende python-runtime.
FROM node:22-slim AS web
WORKDIR /build
COPY webapp/package.json webapp/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY webapp/ .
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/
COPY --from=web /build/dist /app/webapp_dist
EXPOSE 8080
CMD ["gunicorn","-b","0.0.0.0:8080","--workers","2","--threads","4","--timeout","180","app:app"]
