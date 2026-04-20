# =============================================================================
# Stage 1: Builder - Instalação de dependências Python
# =============================================================================
FROM python:3.11-slim AS builder

# Instala dependências do sistema necessárias para compilar pacotes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cria diretório de trabalho
WORKDIR /build

# Copia apenas requirements.txt primeiro (melhor cache)
COPY requirements.txt .

# Cria virtualenv e instala dependências
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Instala dependências Python (incluindo OTel)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Instala auto-instrumentação OTel (baixa instrumentações automaticamente)
RUN opentelemetry-bootstrap -a install

# =============================================================================
# Stage 2: Final - Imagem de produção mínima
# =============================================================================
FROM python:3.11-slim

# Instala apenas as bibliotecas runtime necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário e grupo não-root para segurança
RUN groupadd -r -g 1001 appgroup && \
    useradd -r -u 1001 -g appgroup -m -s /sbin/nologin appuser

# Copia o virtualenv do stage anterior
COPY --from=builder --chown=appuser:appgroup /opt/venv /opt/venv

# Define PATH para usar o virtualenv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ===== Configuração OpenTelemetry via variáveis de ambiente =====
ENV OTEL_SERVICE_NAME="flag-service" \
    OTEL_RESOURCE_ATTRIBUTES="service.namespace=togglemaster,deployment.environment=production,service.version=1.0.0" \
    OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector-opentelemetry-collector.monitoring.svc.cluster.local:4317" \
    OTEL_EXPORTER_OTLP_INSECURE="true" \
    OTEL_EXPORTER_OTLP_PROTOCOL="grpc" \
    OTEL_TRACES_EXPORTER="otlp" \
    OTEL_METRICS_EXPORTER="otlp" \
    OTEL_LOGS_EXPORTER="otlp" \
    OTEL_PYTHON_LOG_CORRELATION="true"

# Define diretório de trabalho
WORKDIR /app

# Copia o código da aplicação
COPY --chown=appuser:appgroup app.py .
COPY --chown=appuser:appgroup db/ ./db/

# Muda para usuário não-root
USER appuser

# Expõe a porta da aplicação
EXPOSE 8002

# Healthcheck para verificar se o serviço está respondendo
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8002/health || exit 1

# Comando: usa opentelemetry-instrument para auto-instrumentar o gunicorn
CMD ["opentelemetry-instrument", "gunicorn", "--bind", "0.0.0.0:8002", "--workers", "4", "--timeout", "60", "app:app"]
