import os
import json
from datetime import datetime, timezone
from uuid import uuid4
from supabase import create_client, Client

# Credenciales de Supabase API (Diferentes de la URL de conexión de Postgres)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") # Se recomienda usar el service_role key en Render

# Inicialización segura del cliente de almacenamiento
supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def log_event_to_storage(event_type: str, correlation_id: Optional[str], payload: dict):
    if not supabase_client:
        print("⚠️ Supabase Storage Logger no inicializado. Omitiendo exportación analítica.")
        return

    now = datetime.now(timezone.utc)
    # Timestamps limpios para nombres de archivos y sobres analíticos
    timestamp_compact = now.strftime("%Y%m%dT%H%M%SZ")
    occurred_at_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # ID único de evento abreviado para el archivo
    short_evt_id = f"evt-{str(uuid4())[:8]}"

    # --- SOBRE ESTÁNDAR CORPORATIVO (EventEnvelope) ---
    envelope = {
        "eventId": f"evt-{str(uuid4())}",
        "eventType": event_type,
        "version": "1.2",
        "occurredAt": occurred_at_iso,
        "producer": "group-5-pedidos",
        "correlationId": correlation_id or str(uuid4()),
        "payload": payload
    }

    # Particionamiento cronológico exacto exigido por Cristóbal
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    
    # Estructura de carpetas: group-5-pedidos/year=YYYY/month=MM/day=DD/
    folder_path = f"group-5-pedidos/year={year}/month={month}/day={day}"
    file_name = f"{timestamp_compact}_{event_type}_{short_evt_id}.json"
    full_storage_path = f"{folder_path}/{file_name}"

    try:
        # Convertir diccionario a bytes JSON formateados
        file_bytes = json.dumps(envelope, indent=2).encode('utf-8')
        
        # Inyección directa en el bucket 'event-logs'
        supabase_client.storage.from_("event-logs").upload(
            path=full_storage_path,
            file=file_bytes,
            file_options={"content-type": "application/json"}
        )
        print(f"✅ Log analítico exportado exitosamente a Supabase Storage: {full_storage_path}")
    except Exception as e:
        print(f"❌ Fallo crítico al escribir en el bucket event-logs: {str(e)}")