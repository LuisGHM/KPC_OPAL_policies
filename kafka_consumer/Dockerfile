FROM python:3.9-slim

WORKDIR /app

# Usar usuário não-root para segurança
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copiar apenas os arquivos de requisitos primeiro para aproveitar o cache de camadas
COPY requirements.txt ./

# Instalar dependências, mas reduzir o tamanho da imagem removendo caches
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copiar o código da aplicação
COPY kafka_consumer.py ./

# Mudar para usuário não-root
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Variável de ambiente para indicar ambiente de execução
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "kafka_consumer.py"]