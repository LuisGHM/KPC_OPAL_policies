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
API_BASE_URL = os.getenv("API_BASE_URL", "http://host.docker.internal:8000")

# Cache para armazenar os IDs já verificados no OPA
entity_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)
# Cache para armazenar relações de device-roles
device_roles_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)

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

def determine_entity_type(topic: str) -> str:
    """
    Determina o tipo de entidade com base no tópico Kafka
    """
    if "Devices_devices" in topic and "Devices_devices_roles" not in topic:
        return "devices"
    elif "Devices_devices_roles" in topic:
        return "devices_roles"
    return "employees"  # Valor padrão

def process_device_role_event(event: Dict[str, Any]) -> None:
    """
    Processa eventos da tabela de relacionamento Devices_devices_roles
    e atualiza o cache local e o OPAL
    """
    if not validate_event(event):
        return
    
    payload = event.get("payload", {})
    op_type = payload.get("op")
    
    if op_type == "c" or op_type == "u":  # CREATE ou UPDATE
        after = payload.get("after", {})
        if not after:
            return
        
        device_id = after.get("devices_id")  # Corrigido de device_id para devices_id
        role_id = after.get("role_id")
        
        if not device_id or not role_id:
            logger.warning(f"⚠️ Evento devices_roles sem device_id ou role_id válidos: {after}")
            return
        
        # Adicionar ao cache
        if device_id not in device_roles_cache:
            device_roles_cache[device_id] = set()
        
        device_roles_cache[device_id].add(role_id)
        logger.info(f"✅ Adicionada role {role_id} ao device {device_id} no cache")
        
        # Atualizar a entidade no OPAL com um pequeno delay para garantir que todos os roles sejam processados
        threading.Timer(1.0, update_device_in_opal, args=[device_id]).start()
        
    elif op_type == "d":  # DELETE
        before = payload.get("before", {})
        if not before:
            return
        
        device_id = before.get("devices_id")  # Corrigido de device_id para devices_id
        role_id = before.get("role_id")
        
        if not device_id or not role_id:
            logger.warning(f"⚠️ Evento devices_roles DELETE sem device_id ou role_id válidos: {before}")
            return
        
        # Remover do cache
        if device_id in device_roles_cache and role_id in device_roles_cache[device_id]:
            device_roles_cache[device_id].remove(role_id)
            logger.info(f"✅ Removida role {role_id} do device {device_id} no cache")
            
            # Atualizar a entidade no OPAL
            threading.Timer(1.0, update_device_in_opal, args=[device_id]).start()

def update_device_in_opal(device_id: int) -> None:
    """
    Força uma atualização do dispositivo no OPAL com as roles atualizadas
    """
    try:
        # Buscar os dados atuais do dispositivo
        device_url = f"{API_BASE_URL}/devices/{device_id}/"
        response = requests.get(device_url, timeout=5)
        
        if response.status_code != 200:
            logger.warning(f"⚠️ Não foi possível obter dados do device {device_id}: {response.status_code}")
            return
        
        device_data = response.json()
        
        # Adicionar as roles do cache ao dispositivo
        roles = list(device_roles_cache.get(device_id, set()))
        device_data["roles"] = roles
        
        logger.info(f"✅ Atualizando device {device_id} no OPAL com roles: {roles}")
        
        # Criar o patch para o OPAL
        patch = [{
            "op": "replace",
            "path": f"/{device_id}",
            "value": device_data
        }]
        
        patch_data = {
            "patch": patch,
            "entity_type": "devices"
        }
        
        # Notificar o OPAL
        reason = f"OPAL Patch: UPDATE device {device_id} roles - Automatic update"
        notify_opal(patch_data, reason=reason)
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar device {device_id} no OPAL: {e}")

def fetch_device_roles(device_id: int) -> List[int]:
    """
    Busca as roles associadas a um dispositivo específico
    Primeiro tenta o cache local, depois a API
    """
    # Verificar no cache primeiro
    if device_id in device_roles_cache:
        roles = list(device_roles_cache[device_id])
        logger.info(f"📋 Roles encontradas no cache para device {device_id}: {roles}")
        return roles
    
    # Se não estiver no cache, buscar via API
    api_url = f"{API_BASE_URL}/devices/{device_id}/roles/"
    
    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            # Assumindo que a API retorna um JSON com as roles
            roles_data = response.json()
            logger.debug(f"API retornou para device {device_id}: {roles_data}")
            
            # Extraindo apenas os IDs das roles
            role_ids = [role['role_id'] for role in roles_data]
            
            # Atualizar o cache
            device_roles_cache[device_id] = set(role_ids)
            
            logger.info(f"📋 Roles encontradas via API para device {device_id}: {role_ids}")
            return role_ids
        else:
            logger.warning(f"⚠️ Erro ao buscar roles para device {device_id}: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ Erro ao buscar roles para device {device_id}: {e}")
        return []

def does_entity_exist_in_opa(entity_id: str, entity_type: str) -> bool:
    """
    Verifica se uma entidade existe no OPA, usando cache local
    """
    cache_key = f"{entity_type}:{entity_id}"
    
    # Primeiro verifica no cache
    if cache_key in entity_cache:
        logger.debug(f"📋 Cache hit para {entity_type} {entity_id}")
        return entity_cache[cache_key]
    
    # Se não estiver no cache, consulta o OPA
    url = f"{OPA_BASE_URL}/v1/data/{entity_type}/{entity_id}"
    
    for retry in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=5)
            
            if resp.status_code == 200:
                # Atualiza o cache e retorna
                entity_cache[cache_key] = True
                return True
            elif resp.status_code == 404:
                entity_cache[cache_key] = False
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

def build_patch_from_event(event: Dict[str, Any], topic: str) -> Optional[Dict[str, Any]]:
    """
    Constrói um JSON Patch a partir do evento Debezium e identifica o tipo de entidade
    """
    if not validate_event(event):
        return None
    
    payload = event.get("payload", {})
    op_type = payload.get("op")
    after = payload.get("after", {})
    before = payload.get("before", {})
    primary_key = "id"
    
    # Identificar qual entidade está sendo alterada com base no tópico
    entity_type = determine_entity_type(topic)
    
    # Se for um evento da tabela de relacionamento devices_roles, processá-lo separadamente
    if entity_type == "devices_roles":
        process_device_role_event(event)
        return None
    
    # Garante que estamos lidando com objetos válidos
    if not isinstance(after, dict) and not isinstance(before, dict):
        logger.error("❌ Dados 'after' e 'before' inválidos")
        return None

    # Para dispositivos, precisamos enriquecer os dados com as roles
    if entity_type == "devices" and op_type in ["c", "u"]:
        device_id = after.get(primary_key)
        if device_id:
            # Buscar as roles deste dispositivo
            roles = fetch_device_roles(device_id)
            # Adicionar as roles ao objeto do dispositivo
            after["roles"] = roles
            logger.info(f"✅ Adicionadas {len(roles)} roles ao device {device_id}")
    
    patch_list = None
    
    if op_type == "c":  # CREATE
        if not after or primary_key not in after:
            logger.error(f"❌ Operação CREATE sem ID válido para {entity_type}")
            return None
        
        entity_id = after.get(primary_key)
        patch_list = [{
            "op": "add",
            "path": f"/{entity_id}",
            "value": after
        }]
        logger.info(f"ℹ️ Criando novo {entity_type}: {entity_id}")

    elif op_type == "u":  # UPDATE
        if not after or primary_key not in after:
            logger.error(f"❌ Operação UPDATE sem ID válido para {entity_type}")
            return None
        
        entity_id = after.get(primary_key)
        if does_entity_exist_in_opa(entity_id, entity_type):
            logger.info(f"ℹ️ Atualizando {entity_type} existente: {entity_id}")
            patch_list = [{
                "op": "replace",
                "path": f"/{entity_id}",
                "value": after
            }]
        else:
            logger.info(f"ℹ️ {entity_type.capitalize()} não encontrado no OPA, criando: {entity_id}")
            patch_list = [{
                "op": "add",
                "path": f"/{entity_id}",
                "value": after
            }]

    elif op_type == "d":  # DELETE
        if not before or primary_key not in before:
            logger.error(f"❌ Operação DELETE sem ID válido para {entity_type}")
            return None
        
        entity_id = before.get(primary_key)
        # Invalidar o cache para esta entidade
        cache_key = f"{entity_type}:{entity_id}"
        if cache_key in entity_cache:
            del entity_cache[cache_key]
            
        patch_list = [{
            "op": "remove",
            "path": f"/{entity_id}"
        }]
        logger.info(f"ℹ️ Removendo {entity_type}: {entity_id}")

    if patch_list:
        return {
            "patch": patch_list,
            "entity_type": entity_type
        }
        
    return None

def notify_opal(patch_data: Dict[str, Any], reason: str = "Debezium event -> incremental patch") -> bool:
    """
    Envia o JSON Patch para o OPAL Server com retry e backoff
    """
    if not patch_data or "patch" not in patch_data:
        logger.warning("⚠️ Patch vazio ou inválido, nada enviado ao OPAL.")
        return False
    
    patch = patch_data["patch"]
    entity_type = patch_data["entity_type"]
    
    payload = {
        "id": f"update-{datetime.now().isoformat()}",
        "entries": [
            {
                "url": "",
                "config": {},
                "topics": ["policy_data"],
                "dst_path": f"/{entity_type}",
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
                logger.info(f"✅ Servidor OPAL notificado com sucesso para {entity_type}. Status: {resp.status_code}")
                return True
            else:
                logger.warning(f"⚠️ Erro ao notificar OPAL para {entity_type}. Status: {resp.status_code}, Resposta: {resp.text}")
                
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

    topic = message.topic
    logger.info(f"📥 Novo evento recebido no tópico {topic}")
    logger.debug(f"Conteúdo do evento: {json.dumps(event, indent=2)}")
    
    # Se o tópico for relacionado à tabela de relacionamento devices_roles
    entity_type = determine_entity_type(topic)
    if entity_type == "devices_roles":
        process_device_role_event(event)
        return
    
    patch_data = build_patch_from_event(event, topic)
    if patch_data:
        op = event.get('payload', {}).get('op')
        entity_id = (event.get('payload', {}).get('after') or 
                   event.get('payload', {}).get('before') or 
                   {}).get('id')
        
        entity_type = patch_data["entity_type"]
        
        operation_types = {
            'c': 'CREATE',
            'u': 'UPDATE',
            'd': 'DELETE'
        }
        
        op_name = operation_types.get(op, 'UNKNOWN')
        reason = f"OPAL Patch: {op_name} {entity_type} id={entity_id}"
        notify_opal(patch_data, reason=reason)

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
        # Precisamos adicionar o tópico para a tabela de relacionamento
        all_topics = TOPICS.copy() if isinstance(TOPICS, list) else TOPICS.split(",")
        related_topic = "EventNotifier.public.Devices_devices_roles"
        if related_topic not in all_topics:
            all_topics.append(related_topic)
            logger.info(f"➕ Adicionado tópico de relacionamento devices_roles: {all_topics}")
        
        consumer = KafkaConsumer(
            *all_topics,
            bootstrap_servers=KAFKA_BROKER,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=safe_deserializer,
            group_id=os.getenv("KAFKA_GROUP_ID", "opal_consumer_group"),
            max_poll_interval_ms=300000,  # 5 minutos
            session_timeout_ms=30000,     # 30 segundos
            heartbeat_interval_ms=10000   # 10 segundos
        )
        
        logger.info(f"🎧 Escutando eventos nos tópicos: {all_topics}")
        
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

def load_initial_device_roles():
    """
    Carrega os dados iniciais de relacionamento entre devices e roles
    """
    try:
        # API para listar todos os dispositivos
        devices_url = f"{API_BASE_URL}/devices/"
        devices_response = requests.get(devices_url, timeout=10)
        
        if devices_response.status_code != 200:
            logger.warning(f"⚠️ Não foi possível carregar a lista de dispositivos: {devices_response.status_code}")
            return
        
        devices = devices_response.json()
        logger.info(f"📋 Carregando roles para {len(devices)} dispositivos...")
        
        for device in devices:
            device_id = device.get("id")
            if device_id:
                roles = fetch_device_roles(device_id)
                logger.info(f"📋 Device {device_id}: {len(roles)} roles carregadas")
                
                # Atualizar o OPAL para cada dispositivo carregado inicialmente
                if roles:
                    # Adicionar roles ao device
                    device["roles"] = roles
                    
                    # Criar patch para o OPAL
                    patch = [{
                        "op": "replace",
                        "path": f"/{device_id}",
                        "value": device
                    }]
                    
                    patch_data = {
                        "patch": patch,
                        "entity_type": "devices"
                    }
                    
                    # Notificar o OPAL
                    reason = f"OPAL Patch: INIT device {device_id} roles - Initial load"
                    notify_opal(patch_data, reason=reason)
    
    except Exception as e:
        logger.error(f"❌ Erro ao carregar dados iniciais de devices_roles: {e}")

if __name__ == "__main__":
    logger.info("🚀 Iniciando Kafka Consumer para OPAL")
    
    try:
        # Carregar relacionamentos iniciais
        logger.info("📋 Carregando dados iniciais de devices_roles...")
        load_initial_device_roles()
        
        wait_for_kafka(KAFKA_BROKER)
        consume_kafka()
    except Exception as e:
        logger.critical(f"❌ Erro fatal: {e}", exc_info=True)
        exit(1)