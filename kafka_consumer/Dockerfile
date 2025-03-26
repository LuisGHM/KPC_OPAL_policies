FROM python:3.9

WORKDIR /app

COPY kafka_consumer.py requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "kafka_consumer.py"]
