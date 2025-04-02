import os
import time
import json
import requests
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

# Carregando variáveis de ambiente do .env
KAFKA_BROKER = os.getenv("KAFKA_BROKER")
TOPICS = os.getenv("TOPICS").split(",")
OPAL_SERVER_URL = os.getenv("OPAL_SERVER_URL")  # Concatenamos aqui como na versão original
OPAL_DATASOURCE_TOKEN = os.getenv("OPAL_DATASOURCE_TOKEN")

# URL do OPA, com valor padrão caso não esteja no .env
OPA_BASE_URL = os.getenv("OPA_BASE_URL", "http://opal_client:8181")

def wait_for_kafka(broker, retries=10, delay=5):
    """
    Tenta se conectar ao broker Kafka algumas vezes antes de falhar.
    """
    for i in range(retries):
        try:
            consumer = KafkaConsumer(bootstrap_servers=broker)
            consumer.close()
            print("Conectado ao Kafka!")
            return
        except NoBrokersAvailable:
            print(f"Broker {broker} não disponível. Tentando novamente em {delay}s...")
            time.sleep(delay)
    raise Exception("Kafka não está disponível após várias tentativas.")

def safe_deserializer(x: bytes):
    """
    Se x for None (mensagem tombstone), retorna None.
    Caso contrário, decodifica como JSON.
    """
    if x is None:
        return None
    return json.loads(x.decode('utf-8'))

def does_user_exist_in_opa(user_id):
    """
    Faz GET em /v1/data/employees/{user_id} para checar se já existe no OPA.
    Retorna True se o status_code == 200, False se 404 ou erro.
    """
    url = f"{OPA_BASE_URL}/v1/data/employees/{user_id}"
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            return True
        elif resp.status_code == 404:
            return False
        else:
            print(f"⚠️  GET {url} retornou {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"⚠️  Erro ao contatar OPA: {e}")
        return False

def build_patch_from_event(event):
    """
    Monta o JSON Patch para CREATE (c), UPDATE (u), DELETE (d),
    usando /employees/{id} como chave.
    Faz "upsert" para update: se existe, replace; caso contrário, add.
    """
    payload = event.get("payload", {})
    op_type = payload.get("op")
    after = payload.get("after")
    before = payload.get("before")

    if not after and not before:
        return None

    primary_key = "id"

    if op_type == "c":  # CREATE
        if not after or after.get(primary_key) is None:
            return None
        user_id = after.get(primary_key)
        return [{
            "op": "add",
            "path": f"/{user_id}",
            "value": after
        }]

    elif op_type == "u":  # UPDATE
        if not after or after.get(primary_key) is None:
            return None
        user_id = after.get(primary_key)
        if does_user_exist_in_opa(user_id):
            return [{
                "op": "replace",
                "path": f"/{user_id}",
                "value": after
            }]
        else:
            return [{
                "op": "add",
                "path": f"/{user_id}",
                "value": after
            }]

    elif op_type == "d":  # DELETE
        if not before or before.get(primary_key) is None:
            return None
        user_id = before.get(primary_key)
        return [{
            "op": "remove",
            "path": f"/{user_id}"
        }]

    return None

def notify_opal(patch, reason="Debezium event -> incremental patch"):
    """
    Envia o JSON Patch para o OPAL Server, que repassa ao OPA.
    """
    if not patch:
        print("⚠️  Patch vazio ou inválido, nada enviado ao OPAL.")
        return

    payload = {
        "id": "unique-update-id-1234",
        "entries": [
            {
                "url": "",
                "config": {},
                "topics": ["policy_data"],
                "dst_path": "/employees",
                "save_method": "PATCH",
                "data": patch
            }
        ],
        "reason": reason,
        "callback": {"callbacks": []}
    }

    headers = {
        "Authorization": f"Bearer {OPAL_DATASOURCE_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(OPAL_SERVER_URL, headers=headers, json=payload)
        print(f"🔔 Servidor OPAL notificado. Resposta: {resp.status_code}, {resp.text}")
    except Exception as e:
        print(f"Erro ao notificar o servidor OPAL: {e}")

def consume_kafka():
    """
    Inicia o consumidor, escuta os tópicos, trata tombstones (value=None)
    e constrói patches para o OPAL.
    """
    consumer = KafkaConsumer(
        *TOPICS,
        bootstrap_servers=KAFKA_BROKER,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=safe_deserializer
    )
    print(f"🎧 Escutando eventos nos tópicos: {TOPICS}")

    for message in consumer:
        event = message.value
        if event is None:
            print("📭 Mensagem tombstone recebida (value=None). Ignorando...")
            continue

        print(f"📥 Novo evento recebido no tópico {message.topic}: {event}")
        patch = build_patch_from_event(event)
        if patch:
            op = event.get('payload', {}).get('op')
            user_id = (event.get('payload', {}).get('after') or
                       event.get('payload', {}).get('before') or
                       {}).get('id')
            reason = f"Atualizando usuário (op={op}, id={user_id})"
            notify_opal(patch, reason=reason)

if __name__ == "__main__":
    wait_for_kafka(KAFKA_BROKER)
    consume_kafka()