# TECHNICAL.md — Guía de implementación interna

> Grupo 5: Order Management · Mini Marketplace Cloud  
> Este archivo es para el equipo que implementa el servicio. El README público está en `README.md`.

---

## Índice

1. [Stack técnico](#1-stack-técnico)
2. [Cómo levantar localmente](#2-cómo-levantar-localmente)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Estructura del código](#4-estructura-del-código)
5. [Idempotencia — cómo funciona](#5-idempotencia--cómo-funciona)
6. [Máquina de estados — reglas de transición](#6-máquina-de-estados--reglas-de-transición)
7. [Consistencia eventual y eventos](#7-consistencia-eventual-y-eventos)
8. [Modelo de datos](#8-modelo-de-datos)
9. [Integración con otros grupos](#9-integración-con-otros-grupos)
10. [Deploy en Render](#10-deploy-en-render)
11. [Gaps conocidos](#11-gaps-conocidos)

---

## 1. Stack técnico

| Capa | Tecnología | Por qué |
|------|-----------|---------|
| Runtime | Python 3.12 | Consistente con G6 y G1 en el ecosistema |
| Framework | FastAPI | Auto-genera `/docs` (Swagger UI), validación Pydantic integrada |
| ORM | SQLAlchemy 2.x | Soporte async, compatible con PostgreSQL |
| BD | PostgreSQL (Render Free o Neon) | Requerido por la rúbrica (concepto SQL evaluado) |
| Validación | Pydantic v2 con `alias_generator` camelCase | Evita traducción manual snake_case ↔ camelCase en cada endpoint |
| Contenedor | Docker | Obligatorio por convenciones del proyecto |

---

## 2. Cómo levantar localmente

### Con Docker (recomendado)

```bash
# Clonar
git clone https://github.com/Mini-Marketplace-Cloud-UTEM/Grupo5-Pedidos.git
cd Grupo5-Pedidos

# Copiar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales de BD

# Construir y levantar
docker build -t order-service .
docker run -p 8050:8050 --env-file .env order-service
```

### Sin Docker

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Aplicar schema SQL
psql $DATABASE_URL -f sql/schema.sql

uvicorn app.main:app --host 0.0.0.0 --port 8050 --reload
```

El servicio queda disponible en:
- API: `http://localhost:8050/v1`
- Swagger UI: `http://localhost:8050/docs`
- ReDoc: `http://localhost:8050/redoc`

---

## 3. Variables de entorno

Crear un archivo `.env` en la raíz (nunca subir al repo):

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/orders_db

# Auth (Grupo 2)
AUTH_VALIDATE_URL=https://api-grupo2-auth.onrender.com/auth/validate

# Grupo 6 (Despacho)
SHIPMENT_SERVICE_URL=https://api-grupo6-despacho.onrender.com/api/v1

# Entorno
ENV=development          # development | production
LOG_LEVEL=INFO

# Polling hacia G6 (mientras no tengan broker de eventos)
SHIPMENT_POLL_INTERVAL_SECONDS=60
```

Ver `.env.example` para referencia completa sin valores reales.

---

## 4. Estructura del código

```
app/
├── main.py                  # FastAPI app, routers, startup
├── config.py                # Settings desde variables de entorno (pydantic-settings)
├── database.py              # Engine SQLAlchemy async, get_db dependency
├── models/
│   ├── order.py             # SQLAlchemy ORM: Order, OrderItem, OrderEvent
│   └── idempotency.py       # ProcessedIdempotencyKey
├── schemas/
│   ├── order.py             # Pydantic: CreateOrderRequest, Order, UpdateStatusRequest
│   └── events.py            # Pydantic: OrderCreatedEvent, OrderStatusChangedEvent
├── routers/
│   ├── orders.py            # POST /orders, GET /orders, GET /orders/{id}, PATCH /status
│   └── health.py            # GET /health
├── services/
│   ├── order_service.py     # Lógica de negocio: crear, transicionar, validar
│   ├── idempotency.py       # Verificar y registrar Idempotency-Key
│   ├── event_publisher.py   # Publicar ORDER_CREATED, ORDER_STATUS_CHANGED, ORDER_CANCELLED
│   └── shipment_poller.py   # Polling periódico a G6 (mitigación temporal)
├── integrations/
│   ├── auth_client.py       # POST /auth/validate → G2
│   └── shipment_client.py   # POST /shipments, GET /shipments → G6
└── middleware/
    └── correlation.py       # Inyectar X-Correlation-Id en cada request
```

---

## 5. Idempotencia — cómo funciona

El problema que resuelve: si G4 (Checkout) reintenta `POST /orders` por timeout de red, o si el usuario hace doble clic, **no se deben crear dos pedidos**.

### Flujo de decisión en `POST /orders`

```
Llega POST /orders con Idempotency-Key: <uuid>
           │
           ▼
¿Existe la key en processed_idempotency_keys?
           │
     SÍ ──►│ ¿request_hash (SHA-256 del body) coincide?
           │         │
           │    SÍ ──► 200 OK + pedido original  ← retransmisión legítima
           │         │
           │    NO ──► 409 DUPLICATED_ORDER       ← misma key, datos distintos
           │
     NO ──► Crear pedido en orders
            Guardar (key, order_id, hash) en processed_idempotency_keys
            201 Created + pedido nuevo
```

### Implementación en código (referencia)

```python
import hashlib, json

async def check_idempotency(key: str, body: dict, db) -> tuple[str, dict | None]:
    """
    Retorna ('new', None) si es primera vez.
    Retorna ('same', order) si ya existe con mismo body.
    Retorna ('conflict', None) si ya existe con body distinto.
    """
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()
    ).hexdigest()

    existing = await db.get(ProcessedIdempotencyKey, key)
    if not existing:
        return 'new', None
    if existing.request_hash == request_hash:
        order = await db.get(Order, existing.order_id)
        return 'same', order
    return 'conflict', None
```

### Idempotencia al consumir eventos externos

Cuando llega `PAYMENT_APPROVED` de G6, el `eventId` se guarda en `order_events.external_event_id` (columna `UNIQUE`). Si el mismo evento llega dos veces (reintento del broker), la segunda inserción falla por `UNIQUE` y el handler descarta silenciosamente.

```python
try:
    await db.execute(
        insert(OrderEvent).values(external_event_id=event.event_id, ...)
    )
except IntegrityError:
    logger.info(f"Evento duplicado ignorado: {event.event_id}")
    return
```

---

## 6. Máquina de estados — reglas de transición

### Transiciones permitidas

```python
VALID_TRANSITIONS: dict[str, list[str]] = {
    "CREATED":         ["PAYMENT_PENDING", "CANCELLED"],
    "PAYMENT_PENDING": ["PAID", "FAILED"],
    "PAID":            ["READY_TO_SHIP", "CANCELLED"],
    "STOCK_RESERVED":  ["READY_TO_SHIP"],
    "READY_TO_SHIP":   ["SHIPPED"],
    "SHIPPED":         ["DELIVERED"],
    # Estados terminales
    "DELIVERED":       [],
    "CANCELLED":       [],
    "FAILED":          [],
}
```

### Reglas adicionales

- `reason` es **obligatorio** cuando el nuevo estado es `CANCELLED` o `FAILED`. Sin él → `400 REASON_REQUIRED`.
- Cada transición genera un registro en `order_events` y publica un evento asíncrono.
- La transición y la publicación del evento deben ocurrir en la misma transacción de BD (o usando el patrón Outbox si se quiere garantía fuerte).

### Uso en el servicio

```python
async def transition_status(order_id: str, new_status: str, reason: str | None, db):
    order = await get_order_or_404(order_id, db)

    if new_status not in VALID_TRANSITIONS[order.status]:
        raise HTTPException(409, detail={
            "code": "INVALID_STATUS_TRANSITION",
            "message": f"No se puede pasar de {order.status} a {new_status}."
        })

    if new_status in ("CANCELLED", "FAILED") and not reason:
        raise HTTPException(400, detail={
            "code": "REASON_REQUIRED",
            "message": "El campo 'reason' es obligatorio para CANCELLED o FAILED."
        })

    previous = order.status
    order.status = new_status
    await db.commit()

    await publish_status_event(order, previous, new_status, reason)
    return order
```

---

## 7. Consistencia eventual y eventos

### Qué significa aquí

Cuando G5 actualiza un pedido a `PAID`, **no llama sincrónicamente a G7 (Reportería) ni a G9 (Notificaciones)**. En cambio, publica un evento en el bus y cada grupo lo procesa cuando puede. Durante un breve intervalo, el dashboard de G7 puede mostrar el pedido en estado anterior — eso es consistencia eventual y está aceptado.

### Sobre estándar de eventos

Todos los eventos siguen el `EventEnvelope` del proyecto:

```json
{
  "eventId":       "uuid-v4",
  "eventType":     "ORDER_STATUS_CHANGED",
  "version":       "1.0",
  "occurredAt":    "2026-06-22T10:05:00Z",
  "producer":      "group-5-pedidos",
  "correlationId": "uuid-de-trazabilidad-opcional",
  "payload":       { ... }
}
```

### Eventos que publica G5

| Evento | Payload clave | Quién consume |
|--------|--------------|---------------|
| `ORDER_CREATED` | orderId, userId, items, totalAmount | G7, G9 |
| `ORDER_STATUS_CHANGED` | orderId, previousStatus, status | G7, G9 |
| `ORDER_CANCELLED` | orderId, status, reason | G7, G9 |

### Eventos que consume G5

| Evento | De quién | Acción |
|--------|----------|--------|
| `PAYMENT_APPROVED` | G6 Pagos | → transición a `PAID`, luego `POST /shipments` a G8 |
| `PAYMENT_REJECTED` | G6 Pagos | → transición a `FAILED`, publica `ORDER_CANCELLED` |

---

## 8. Modelo de datos

Esquema completo en [`sql/schema.sql`](sql/schema.sql). Resumen:

### Tabla `orders`

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | UUID PK | Uso interno para joins |
| `order_id` | VARCHAR(30) UNIQUE | Clave de negocio: `ORD-YYYYMMDD-NNN` |
| `user_id` | UUID | FK lógica a G2 Auth |
| `status` | ENUM | Ver máquina de estados |
| `idempotency_key` | UUID UNIQUE | Garantía contra duplicados |
| `subtotal / shipping_cost / total_amount` | INTEGER | CLP, sin decimales |
| `shipping_*` | VARCHAR | Snapshot de dirección de envío |

### Tabla `order_items`

Snapshot inmutable de cada producto al momento de compra. `name` y `unit_price` no se actualizan si G3 (Catálogo) cambia el producto después.

### Tabla `order_events`

Audit trail completo. La columna `external_event_id UNIQUE` garantiza idempotencia en consumo de eventos externos.

### Índices clave

```sql
CREATE INDEX idx_orders_user_status ON orders (user_id, status);
-- Es la consulta más frecuente del BFF: "dame los pedidos de este user en este estado"
```

---

## 9. Integración con otros grupos

### G2 Auth — validación de JWT

Antes de procesar cualquier request autenticado:

```python
async def validate_token(token: str) -> dict:
    response = await http_client.post(
        f"{settings.AUTH_VALIDATE_URL}",
        headers={"Authorization": token}
    )
    if response.status_code != 200:
        raise HTTPException(401, detail={"code": "UNAUTHORIZED", "message": "Token inválido."})
    return response.json()  # {"valid": true, "user": {"id": "...", "role": "..."}}
```

### G4 Checkout — quién llama a quién

G4 llama a `POST /orders`. G5 **no** llama a G4. El BFF tampoco llama directo a G5 para crear pedidos.

### G8 Despacho — mitigación temporal por falta de broker

G8 no tiene aún worker de Outbox activo. Solución temporal: polling periódico.

```python
# services/shipment_poller.py
async def poll_shipments():
    """Corre cada SHIPMENT_POLL_INTERVAL_SECONDS segundos."""
    orders_in_transit = await get_orders_by_status(["READY_TO_SHIP", "SHIPPED"])
    for order in orders_in_transit:
        shipment = await shipment_client.get_by_order_id(order.order_id)
        if shipment["status"] == "DELIVERED":
            await transition_status(order.order_id, "DELIVERED", reason=None)
        elif shipment["status"] == "FAILED":
            await transition_status(order.order_id, "CANCELLED", reason="SHIPMENT_FAILED")
```

Cuando G8 active su broker, reemplazar este polling por consumo del evento `SHIPMENT_DELIVERED`. Documentar como versión `1.1` del contrato de eventos.

---

## 10. Deploy en Render

### Pasos

1. Crear un nuevo **Web Service** en [render.com](https://render.com).
2. Conectar el repo `Mini-Marketplace-Cloud-UTEM/Grupo5-Pedidos`.
3. Configurar:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables:** agregar todas las del `.env.example`
4. Crear una **PostgreSQL** en Render Free y copiar la `DATABASE_URL` interna.
5. Una vez desplegado, ejecutar el schema:
   ```bash
   psql $DATABASE_URL -f sql/schema.sql
   ```
6. Actualizar la fila de Grupo 5 en `marketplace-contracts/registro-de-servicios.md` con la URL pública.

### render.yaml (opcional, para deploy automático)

```yaml
services:
  - type: web
    name: grupo5-order-service
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: grupo5-orders-db
          property: connectionString
      - key: AUTH_VALIDATE_URL
        value: https://api-grupo2-auth.onrender.com/auth/validate
      - key: ENV
        value: production

databases:
  - name: grupo5-orders-db
    plan: free
```

### Nota sobre el error 404 en Prism

Si usas Stoplight Prism como mock (en vez de FastAPI real), el error `NO_PATH_MATCHED_ERROR` al ir a `/` es normal — Prism solo responde a rutas definidas en el OpenAPI. Siempre probar contra `/v1/health` o `/v1/orders`, nunca contra la raíz.

---

## 11. Gaps conocidos

| Gap | Impacto | Mitigación |
|-----|---------|------------|
| G8 (Despacho) sin broker de eventos activo | G5 no recibe `SHIPMENT_DELIVERED` | Polling a `GET /shipments?orderId=` cada 60s |
| No está definido explícitamente quién dispara `POST /payments` | El pedido puede quedar en `CREATED` sin que nadie inicie el cobro | Confirmar con G4 y G6 antes de implementar |
| `shippingAddress` no está en el contrato de G4 explícitamente | G5 no sabe si G4 lo reenvía o si debe buscarlo en otro servicio | Confirmar con G4 |

Ver `02-matriz-dependencias.md` para el detalle completo.
