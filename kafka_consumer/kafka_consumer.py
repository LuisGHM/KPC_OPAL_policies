import os
import time
import json
import logging
import requests
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from requests.exceptions import ConnectionError, Timeout
from cachetools import TTLCache

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(process)d] - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("kafka_consumer")

# Carregando variáveis de ambiente
KAFKA_BROKER = os.getenv("KAFKA_BROKER")
TOPICS = os.getenv("TOPICS", "").split(",")
OPAL_SERVER_URL = os.getenv("OPAL_SERVER_URL")
OPAL_DATASOURCE_TOKEN = os.getenv("OPAL_DATASOURCE_TOKEN")
OPA_BASE_URL = os.getenv("OPA_BASE_URL", "http://opal_client:8181")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", "5"))
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutos

# Caches em memória
# Para entidades OPA
entity_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)
# Para relacionamento device -> roles
device_roles_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)
# Para armazenar estado completo de cada device vindo de Debezium
devices_cache: Dict[int, Dict[str, Any]] = {}


def exponential_backoff(retry_count: int, base_delay: int = RETRY_DELAY_SECONDS) -> int:
    """
    Calcula o tempo de espera usando backoff exponencial
    """
    return min(base_delay * (2 ** retry_count), 60)


def wait_for_kafka(broker: str, retries: int = 10) -> None:
    """
    Tenta se conectar ao broker Kafka usando backoff exponencial
    """
    for i in range(retries):
        try:
            consumer = KafkaConsumer(bootstrap_servers=broker)
            consumer.close()
            logger.info("✅ Conectado ao Kafka com sucesso!")
            return
        except NoBrokersAvailable:
            delay = exponential_backoff(i)
            logger.warning(f"⚠️ Broker {broker} não disponível. Tentando novamente em {delay}s... (tentativa {i+1}/{retries})")
            time.sleep(delay)
    raise Exception("❌ Kafka não está disponível após várias tentativas.")


def safe_deserializer(x: bytes) -> Optional[Dict[str, Any]]:
    if x is None:
        return None
    try:
        return json.loads(x.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erro ao desserializar mensagem: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao processar mensagem: {e}")
        return None


def determine_entity_type(topic: str) -> str:
    if "Devices_devices" in topic and "Devices_devices_roles" not in topic:
        return "devices"
    elif "Devices_devices_roles" in topic:
        return "devices_roles"
    return "employees"


def process_device_role_event(event: Dict[str, Any]) -> None:
    if not validate_event(event):
        return
    payload = event.get("payload", {})
    op_type = payload.get("op")
    if op_type in ("c", "u"):
        after = payload.get("after", {})
        device_id = after.get("devices_id")
        role_id = after.get("role_id")
        if not device_id or not role_id:
            logger.warning(f"⚠️ Evento devices_roles sem device_id ou role_id válidos: {after}")
            return
        device_roles_cache.setdefault(device_id, set()).add(role_id)
        logger.info(f"✅ Adicionada role {role_id} ao device {device_id} no cache")
        threading.Timer(1.0, update_device_in_opal, args=[device_id]).start()
    elif op_type == "d":
        before = payload.get("before", {})
        device_id = before.get("devices_id")
        role_id = before.get("role_id")
        if not device_id or not role_id:
            logger.warning(f"⚠️ Evento DELETE sem device_id ou role_id válidos: {before}")
            return
        if device_id in device_roles_cache and role_id in device_roles_cache[device_id]:
            device_roles_cache[device_id].remove(role_id)
            logger.info(f"✅ Removida role {role_id} do device {device_id} no cache")
            threading.Timer(1.0, update_device_in_opal, args=[device_id]).start()


def update_device_in_opal(device_id: int) -> None:
    try:
        device_data = devices_cache.get(device_id)
        if not device_data:
            logger.warning(f"⚠️ Estado de device {device_id} não está em cache, pulando update")
            return
        roles = list(device_roles_cache.get(device_id, []))
        data = device_data.copy()
        data["roles"] = roles
        logger.info(f"✅ Atualizando device {device_id} no OPAL com roles: {roles}")
        patch = [{
            "op": "replace",
            "path": f"/{device_id}",
            "value": data
        }]
        patch_data = {"patch": patch, "entity_type": "devices"}
        reason = f"OPAL Patch: UPDATE device {device_id} roles - Automatic update"
        notify_opal(patch_data, reason=reason)
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar device {device_id} no OPAL: {e}")


def fetch_device_roles(device_id: int) -> List[int]:
    return list(device_roles_cache.get(device_id, []))


def does_entity_exist_in_opa(entity_id: str, entity_type: str) -> bool:
    cache_key = f"{entity_type}:{entity_id}"
    if cache_key in entity_cache:
        return entity_cache[cache_key]
    url = f"{OPA_BASE_URL}/v1/data/{entity_type}/{entity_id}"
    for retry in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                entity_cache[cache_key] = True
                return True
            elif resp.status_code == 404:
                entity_cache[cache_key] = False
                return False
            if retry < MAX_RETRIES - 1:
                time.sleep(exponential_backoff(retry))
                continue
            return False
        except (ConnectionError, Timeout) as e:
            if retry < MAX_RETRIES - 1:
                time.sleep(exponential_backoff(retry))
            else:
                return False
        except Exception:
            return False
    return False


def validate_event(event: Dict[str, Any]) -> bool:
    if not isinstance(event, dict) or 'payload' not in event:
        return False
    payload = event['payload']
    if not isinstance(payload, dict) or payload.get('op') not in ('c','u','d'):
        return False
    if payload['op'] in ('c','u') and 'after' not in payload:
        return False
    if payload['op'] == 'd' and 'before' not in payload:
        return False
    return True


def build_patch_from_event(event: Dict[str, Any], topic: str) -> Optional[Dict[str, Any]]:
    if not validate_event(event):
        return None
    payload = event['payload']
    op_type = payload['op']
    after = payload.get('after', {})
    before = payload.get('before', {})
    primary_key = 'id'
    entity_type = determine_entity_type(topic)
    if entity_type == 'devices_roles':
        process_device_role_event(event)
        return None
    # Para devices, atualizar cache e injetar roles do cache
    if entity_type == 'devices' and op_type in ('c','u'):
        device_id = after.get(primary_key)
        if device_id:
            devices_cache[device_id] = after.copy()
            roles = fetch_device_roles(device_id)
            after['roles'] = roles
            logger.info(f"✅ Adicionadas {len(roles)} roles ao device {device_id}")
    patch_list = None
    if op_type == 'c' and after.get(primary_key) is not None:
        entity_id = after[primary_key]
        patch_list = [{"op": "add", "path": f"/{entity_id}", "value": after}]
    elif op_type == 'u' and after.get(primary_key) is not None:
        entity_id = after[primary_key]
        if does_entity_exist_in_opa(entity_id, entity_type):
            patch_list = [{"op": "replace", "path": f"/{entity_id}", "value": after}]
        else:
            patch_list = [{"op": "add", "path": f"/{entity_id}", "value": after}]
    elif op_type == 'd' and before.get(primary_key) is not None:
        entity_id = before[primary_key]
        cache_key = f"{entity_type}:{entity_id}"
        if cache_key in entity_cache:
            del entity_cache[cache_key]
        patch_list = [{"op": "remove", "path": f"/{entity_id}"}]
    if patch_list:
        return {"patch": patch_list, "entity_type": entity_type}
    return None


def notify_opal(patch_data: Dict[str, Any], reason: str = "Debezium event -> incremental patch") -> bool:
    if not patch_data or 'patch' not in patch_data:
        return False
    payload = {
        'id': f"update-{datetime.now().isoformat()}",
        'entries': [{
            'url': '',
            'config': {},
            'topics': ['policy_data'],
            'dst_path': f"/{patch_data['entity_type']}",
            'save_method': 'PATCH',
            'data': patch_data['patch']
        }],
        'reason': reason,
        'callback': {'callbacks': []}
    }
    headers = {
        'Authorization': f"Bearer {OPAL_DATASOURCE_TOKEN}",
        'Content-Type': 'application/json'
    }
    for retry in range(MAX_RETRIES):
        try:
            resp = requests.post(OPAL_SERVER_URL, headers=headers, json=payload, timeout=10)
            if resp.status_code in (200,201,202,204):
                logger.info(f"✅ Servidor OPAL notificado com sucesso para {patch_data['entity_type']}. Status: {resp.status_code}")
                return True
            if retry < MAX_RETRIES - 1:
                time.sleep(exponential_backoff(retry))
            else:
                logger.error(f"❌ Falha ao notificar OPAL após {MAX_RETRIES} tentativas.")
                return False
        except (ConnectionError, Timeout):
            if retry < MAX_RETRIES - 1:
                time.sleep(exponential_backoff(retry))
            else:
                return False
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao notificar OPAL: {e}")
            return False
    return False


def process_message(message) -> None:
    event = message.value
    if event is None:
        return
    topic = message.topic
    entity_type = determine_entity_type(topic)
    if entity_type == 'devices_roles':
        process_device_role_event(event)
        return
    patch_data = build_patch_from_event(event, topic)
    if patch_data:
        op = event['payload']['op']
        entity_id = (event['payload'].get('after') or event['payload'].get('before') or {}).get('id')
        operation_types = {'c':'CREATE','u':'UPDATE','d':'DELETE'}
        reason = f"OPAL Patch: {operation_types.get(op,'UNKNOWN')} {patch_data['entity_type']} id={entity_id}"
        notify_opal(patch_data, reason=reason)


def consume_kafka() -> None:
    stop_event = threading.Event()
    def signal_handler(sig, frame):
        stop_event.set()
    all_topics = TOPICS.copy() if isinstance(TOPICS, list) else TOPICS.split(',')
    rel_topic = 'EventNotifier.public.Devices_devices_roles'
    if rel_topic not in all_topics:
        all_topics.append(rel_topic)
    consumer = KafkaConsumer(
        *all_topics,
        bootstrap_servers=KAFKA_BROKER,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=safe_deserializer,
        group_id=os.getenv("KAFKA_GROUP_ID","opal_consumer_group"),
        max_poll_interval_ms=300000,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000
    )
    while not stop_event.is_set():
        messages = consumer.poll(timeout_ms=1000, max_records=10)
        for tp, msgs in messages.items():
            for message in msgs:
                process_message(message)
        consumer.commit()
    consumer.close(autocommit=True)

if __name__ == "__main__":
    logger.info("🚀 Iniciando Kafka Consumer para OPAL")
    try:
        wait_for_kafka(KAFKA_BROKER)
        consume_kafka()
    except Exception as e:
        logger.critical(f"❌ Erro fatal: {e}", exc_info=True)
        exit(1)
