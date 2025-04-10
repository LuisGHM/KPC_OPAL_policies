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
from requests.exceptions import RequestException, ConnectionError, Timeout
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

# Cache para armazenar os IDs já verificados no OPA
user_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)

def exponential_backoff(retry_count: int, base_delay: int = RETRY_DELAY_SECONDS) -> int:
    """
    Calcula o tempo de espera usando backoff exponencial
    """
    return min(base_delay * (2 ** retry_count), 60)  # máximo de 60 segundos

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
    """
    Desserializa mensagens do Kafka com tratamento de erros
    """
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

def does_user_exist_in_opa(user_id: str) -> bool:
    """
    Verifica se um usuário existe no OPA, usando cache local
    """
    # Primeiro verifica no cache
    if user_id in user_cache:
        logger.debug(f"📋 Cache hit para usuário {user_id}")
        return user_cache[user_id]
    
    # Se não estiver no cache, consulta o OPA
    url = f"{OPA_BASE_URL}/v1/data/employees/{user_id}"
    
    for retry in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=5)
            
            if resp.status_code == 200:
                # Atualiza o cache e retorna
                user_cache[user_id] = True
                return True
            elif resp.status_code == 404:
                user_cache[user_id] = False
                return False
            else:
                logger.warning(f"⚠️ GET {url} retornou {resp.status_code}: {resp.text}")
                
                if retry < MAX_RETRIES - 1:
                    delay = exponential_backoff(retry)
                    logger.info(f"🔄 Tentando novamente em {delay}s... (tentativa {retry+1}/{MAX_RETRIES})")
                    time.sleep(delay)
                    continue
                    
                return False
                
        except (ConnectionError, Timeout) as e:
            logger.warning(f"⚠️ Erro de conexão ao OPA: {e}")
            if retry < MAX_RETRIES - 1:
                delay = exponential_backoff(retry)
                logger.info(f"🔄 Tentando novamente em {delay}s... (tentativa {retry+1}/{MAX_RETRIES})")
                time.sleep(delay)
            else:
                return False
        except Exception as e:
            logger.error(f"❌ Erro ao contatar OPA: {e}")
            return False

def validate_event(event: Dict[str, Any]) -> bool:
    """
    Valida se o evento tem a estrutura esperada
    """
    if not isinstance(event, dict):
        logger.error("❌ Evento não é um dicionário válido")
        return False
    
    if 'payload' not in event:
        logger.error("❌ Evento não contém campo 'payload'")
        return False
    
    payload = event.get('payload', {})
    if not isinstance(payload, dict):
        logger.error("❌ Payload não é um dicionário válido")
        return False
    
    if 'op' not in payload:
        logger.error("❌ Payload não contém campo 'op'")
        return False
    
    op_type = payload.get('op')
    if op_type not in ('c', 'u', 'd'):
        logger.warning(f"⚠️ Tipo de operação desconhecido: {op_type}")
        return False
    
    # Para operações create e update, precisamos do 'after'
    if op_type in ('c', 'u') and 'after' not in payload:
        logger.error(f"❌ Operação {op_type} sem dados 'after'")
        return False
    
    # Para operações delete, precisamos do 'before'
    if op_type == 'd' and 'before' not in payload:
        logger.error("❌ Operação delete sem dados 'before'")
        return False
    
    return True

def build_patch_from_event(event: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Constrói um JSON Patch a partir do evento Debezium
    """
    if not validate_event(event):
        return None
    
    payload = event.get("payload", {})
    op_type = payload.get("op")
    after = payload.get("after", {})
    before = payload.get("before", {})
    primary_key = "id"

    # Garante que estamos lidando com objetos válidos
    if not isinstance(after, dict) and not isinstance(before, dict):
        logger.error("❌ Dados 'after' e 'before' inválidos")
        return None

    if op_type == "c":  # CREATE
        if not after or primary_key not in after:
            logger.error("❌ Operação CREATE sem ID válido")
            return None
        
        user_id = after.get(primary_key)
        return [{
            "op": "add",
            "path": f"/{user_id}",
            "value": after
        }]

    elif op_type == "u":  # UPDATE
        if not after or primary_key not in after:
            logger.error("❌ Operação UPDATE sem ID válido")
            return None
        
        user_id = after.get(primary_key)
        if does_user_exist_in_opa(user_id):
            logger.info(f"ℹ️ Atualizando usuário existente: {user_id}")
            return [{
                "op": "replace",
                "path": f"/{user_id}",
                "value": after
            }]
        else:
            logger.info(f"ℹ️ Usuário não encontrado no OPA, criando: {user_id}")
            return [{
                "op": "add",
                "path": f"/{user_id}",
                "value": after
            }]

    elif op_type == "d":  # DELETE
        if not before or primary_key not in before:
            logger.error("❌ Operação DELETE sem ID válido")
            return None
        
        user_id = before.get(primary_key)
        # Invalidar o cache para este usuário
        if user_id in user_cache:
            del user_cache[user_id]
            
        return [{
            "op": "remove",
            "path": f"/{user_id}"
        }]

    return None

def notify_opal(patch: List[Dict[str, Any]], reason: str = "Debezium event -> incremental patch") -> bool:
    """
    Envia o JSON Patch para o OPAL Server com retry e backoff
    """
    if not patch:
        logger.warning("⚠️ Patch vazio ou inválido, nada enviado ao OPAL.")
        return False

    payload = {
        "id": f"update-{datetime.now().isoformat()}",
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

    for retry in range(MAX_RETRIES):
        try:
            resp = requests.post(OPAL_SERVER_URL, headers=headers, json=payload, timeout=10)
            
            if resp.status_code in (200, 201, 202, 204):
                logger.info(f"✅ Servidor OPAL notificado com sucesso. Status: {resp.status_code}")
                return True
            else:
                logger.warning(f"⚠️ Erro ao notificar OPAL. Status: {resp.status_code}, Resposta: {resp.text}")
                
                if retry < MAX_RETRIES - 1:
                    delay = exponential_backoff(retry)
                    logger.info(f"🔄 Tentando novamente em {delay}s... (tentativa {retry+1}/{MAX_RETRIES})")
                    time.sleep(delay)
                else:
                    logger.error(f"❌ Falha ao notificar OPAL após {MAX_RETRIES} tentativas.")
                    return False
                    
        except (ConnectionError, Timeout) as e:
            logger.warning(f"⚠️ Erro de conexão ao OPAL: {e}")
            if retry < MAX_RETRIES - 1:
                delay = exponential_backoff(retry)
                logger.info(f"🔄 Tentando novamente em {delay}s... (tentativa {retry+1}/{MAX_RETRIES})")
                time.sleep(delay)
            else:
                logger.error(f"❌ Falha ao contatar OPAL após {MAX_RETRIES} tentativas.")
                return False
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao notificar o servidor OPAL: {e}")
            return False
    
    return False

def process_message(message):
    """
    Processa uma mensagem do Kafka
    """
    event = message.value
    if event is None:
        logger.info("📭 Mensagem tombstone recebida (value=None). Ignorando...")
        return

    logger.info(f"📥 Novo evento recebido no tópico {message.topic}")
    logger.debug(f"Conteúdo do evento: {json.dumps(event, indent=2)}")
    
    patch = build_patch_from_event(event)
    if patch:
        op = event.get('payload', {}).get('op')
        user_id = (event.get('payload', {}).get('after') or 
                   event.get('payload', {}).get('before') or 
                   {}).get('id')
        
        operation_types = {
            'c': 'CREATE',
            'u': 'UPDATE',
            'd': 'DELETE'
        }
        
        op_name = operation_types.get(op, 'UNKNOWN')
        reason = f"OPAL Patch: {op_name} usuário id={user_id}"
        notify_opal(patch, reason=reason)

def graceful_shutdown_handler(consumer, stop_event):
    """
    Handler para graceful shutdown
    """
    logger.info("⏹️ Iniciando shutdown graceful...")
    stop_event.set()
    # Esperamos mais 5 segundos para qualquer processamento em andamento
    time.sleep(5)
    consumer.close(autocommit=True)
    logger.info("⏹️ Consumer fechado. Serviço encerrado com sucesso.")

def consume_kafka():
    """
    Loop principal do consumer
    """
    stop_event = threading.Event()
    
    # Configurar signal handler para SIGTERM e SIGINT
    def signal_handler(sig, frame):
        logger.info(f"Sinal recebido: {sig}")
        stop_event.set()
    
    # Em um ambiente real, importaríamos o signal e configuráriamos handlers
    # import signal
    # signal.signal(signal.SIGTERM, signal_handler)
    # signal.signal(signal.SIGINT, signal_handler)
    
    try:
        consumer = KafkaConsumer(
            *TOPICS,
            bootstrap_servers=KAFKA_BROKER,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=safe_deserializer,
            group_id=os.getenv("KAFKA_GROUP_ID", "opal_consumer_group"),
            max_poll_interval_ms=300000,  # 5 minutos
            session_timeout_ms=30000,     # 30 segundos
            heartbeat_interval_ms=10000   # 10 segundos
        )
        
        logger.info(f"🎧 Escutando eventos nos tópicos: {TOPICS}")
        
        # Thread para graceful shutdown
        shutdown_thread = threading.Thread(
            target=graceful_shutdown_handler,
            args=(consumer, stop_event),
            daemon=True
        )
        
        while not stop_event.is_set():
            # Polling com timeout para permitir checagem do stop_event
            messages = consumer.poll(timeout_ms=1000, max_records=10)
            
            for tp, msgs in messages.items():
                for message in msgs:
                    process_message(message)
            
            # Commit explícito para garantir processamento
            consumer.commit()
            
    except KeyboardInterrupt:
        logger.info("👋 Recebido sinal de interrupção. Encerrando...")
        stop_event.set()
        
    except Exception as e:
        logger.critical(f"❌ Erro fatal no consumer: {e}", exc_info=True)
        stop_event.set()
        
    finally:
        if 'consumer' in locals():
            logger.info("🛑 Fechando consumer...")
            consumer.close(autocommit=True)

if __name__ == "__main__":
    logger.info("🚀 Iniciando Kafka Consumer para OPAL")
    
    try:
        wait_for_kafka(KAFKA_BROKER)
        consume_kafka()
    except Exception as e:
        logger.critical(f"❌ Erro fatal: {e}", exc_info=True)
        exit(1)