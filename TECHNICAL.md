# TECHNICAL.md — Guía de implementación interna

> Grupo 5: Order Management · Mini Marketplace Cloud
> Este archivo describe **exactamente lo que está implementado en este repositorio**, no un diseño futuro. El README público está en `README.md`.

---

## Índice

1. [Stack técnico](#1-stack-técnico)
2. [Cómo levantar localmente](#2-cómo-levantar-localmente)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Estructura del código](#4-estructura-del-código)
5. [Idempotencia — cómo funciona](#5-idempotencia--cómo-funciona)
6. [Máquina de estados](#6-máquina-de-estados)
7. [Eventos](#7-eventos)
8. [Modelo de datos](#8-modelo-de-datos)
9. [Integración con otros grupos](#9-integración-con-otros-grupos)
10. [Deploy en Render](#10-deploy-en-render)
11. [Gaps conocidos](#11-gaps-conocidos)

---

## 1. Stack técnico

| Capa | Tecnología |
|------|-----------|
| Runtime | Python 3.12 |
| Framework | FastAPI (auto-genera `/docs` con Swagger UI) |
| ORM | SQLAlchemy 2.x (motor síncrono, no async) |
| BD | PostgreSQL (Supabase) |
| Validación | Pydantic v2, con `Field(alias=...)` explícito por campo para mapear `snake_case` (BD) ↔ `camelCase` (contrato) |
| Contenedor | Docker |
| Deploy | Render (Web Service) |

---

## 2. Cómo levantar localmente

```bash
git clone <url-del-repo>
cd <repo>

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configurar variables de entorno (ver sección 3) antes de levantar
uvicorn app.main:app --host 0.0.0.0 --port 8050 --reload
```

El servicio queda disponible en:
- API: `http://localhost:8050`
- Swagger UI: `http://localhost:8050/docs`

### Con Docker

```bash
docker build -t order-service .
docker run -p 8080:8080 --env-file .env order-service
```

---

## 3. Variables de entorno

| Variable | Uso | Valor por defecto en el código |
|---|---|---|
| `DATABASE_URL` | Conexión a PostgreSQL (Supabase) | — (obligatoria en producción) |
| `G2_AUTH_URL` | Base URL del servicio de Identidad para validar tokens | `https://grupo2-identidadusuario.onrender.com` |
| `G3_CATALOG_URL` | Base URL del servicio de Catálogo (datos volumétricos para envío) | `https://api-grupo3-catalogo.onrender.com` |
| `G6_DELIVERY_URL` | Base URL del servicio de Despacho | `https://api-grupo6-despacho.onrender.com` |

Estas tres URLs externas tienen un valor por defecto hardcodeado en `app/main.py` como fallback, pero en Render deben configurarse explícitamente como variables de entorno para poder cambiarlas sin tocar código.

---

## 4. Estructura del código

```
app/
├── main.py             # FastAPI app, todos los endpoints, llamadas a G2/G3/G6
├── database.py          # Engine SQLAlchemy, sesión, get_db dependency
├── models.py             # SQLAlchemy ORM: Order, OrderItem
├── schemas.py            # Pydantic: CreateOrderRequest, OrderResponse, OrderItem, ShippingAddress
└── events_logger.py     # Envío de eventos analíticos (log_event_to_storage)
seed.py                   # Script para poblar la BD con datos de prueba
Dockerfile.txt             # Definición del contenedor
```

No hay separación en `routers/`, `services/` ni `integrations/` — todos los endpoints y la lógica de negocio viven en `app/main.py`. Tampoco hay tabla de eventos (`order_events`) ni columna `idempotency_key` dedicada: la idempotencia se resuelve guardando la key dentro del campo `notes` (ver sección 5).

---

## 5. Idempotencia — cómo funciona

Implementación actual (simple, no usa tabla dedicada):

```python
existing_order = db.query(Order).filter(Order.notes.contains(f"IK:{idempotency_key}")).first()
if existing_order:
    return existing_order
```

Al crear el pedido, la `Idempotency-Key` recibida se guarda embebida en el campo `notes`:

```python
notes=f"{request.notes or ''} [IK:{idempotency_key}]"
```

**Limitación conocida:** esto no valida que el *body* de la petición sea idéntico al original (solo que la key ya existe), y depender de un `LIKE`/`contains` sobre un campo de texto no es lo más performante a escala. Es funcional para la fase actual del proyecto, pero un campo `idempotency_key UNIQUE` dedicado sería la mejora natural para iteraciones futuras.

---

## 6. Máquina de estados

El servicio no valida transiciones contra una tabla de transiciones permitidas — el estado se asigna directamente según lo que llega en el PATCH, con una excepción: cuando el nuevo estado es `PAID`, dispara la orquestación síncrona con G3 (datos volumétricos) y G6 (creación de envío):

```
CREATED → PAYMENT_PENDING → PAID → READY_TO_SHIP → SHIPPED → DELIVERED
                  │
                  ▼
               FAILED → CANCELLED
```

Ver el detalle completo en `01-documento-arquitectura.md`, sección 5.

---

## 7. Eventos

Eventos publicados vía `log_event_to_storage` (`app/events_logger.py`):

| Evento | Cuándo |
|---|---|
| `ORDER_CREATED` | Al crear el pedido exitosamente |
| `ORDER_STATUS_CHANGED` | En cada transición de estado |
| `ORDER_CANCELLED` | Cuando el estado deriva en `CANCELLED`/`FAILED` |

Esquema completo del envelope y payloads en [`contrato/events.md`](contrato/events.md).

---

## 8. Modelo de datos

Implementado en `app/models.py` con SQLAlchemy. Ver el detalle completo y los tipos en [`modelo-de-datos.md`](modelo-de-datos.md).

### Tabla `orders`
`order_id` (PK, string `ORD-YYYYMMDD-NNN`), `user_id`, `status`, `shipment_ids` (array), `shipping_address` (JSON, nullable), `subtotal`, `shipping_cost`, `total_amount`, `currency`, `notes`, `created_at`, `updated_at`.

### Tabla `order_items`
`id` (PK autoincrement), `order_id` (FK), `product_id`, `name`, `quantity`, `unit_price`, `subtotal`.

---

## 9. Integración con otros grupos

### G2 (Identidad) — validación de token

Cada endpoint protegido llama síncronamente a `POST {G2_AUTH_URL}/auth/validate` con el header `Authorization` reenviado. La respuesta real de G2 tiene esta forma:

```json
{"valid": true, "user": {"id": "...", "roles": ["customer"]}}
```

El código lee `user.id` y el primer rol de `user.roles` (o `"admin"` si está presente en la lista).

### G3 (Catálogo) — datos volumétricos

Al transicionar un pedido a `PAID`, el servicio consulta `GET {G3_CATALOG_URL}/products/{productId}` por cada ítem para obtener `originCd`, peso y dimensiones, usados luego en la llamada a G6. Si la consulta falla, se usan valores por defecto (`CENTRO`, 1.0 kg, `20x20x20`) para no bloquear el flujo.

### G6 (Despacho) — creación de envíos

`POST {G6_DELIVERY_URL}/api/v1/shipments` con el arreglo de paquetes. Mientras G6 no tenga worker de eventos activo, G5 no hace polling automático — la actualización de `SHIPPED`/`DELIVERED` depende de llamadas manuales a `PATCH /orders/{orderId}/status` (ver gaps).

---

## 10. Deploy en Render

### Pasos realizados

1. Web Service en Render conectado al repositorio de GitHub.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (puerto definido en `Dockerfile.txt` como `8080`, Render expone vía `$PORT`).
4. **Variables de entorno configuradas:** `DATABASE_URL` (apuntando a la instancia de Supabase), `G2_AUTH_URL`, `G3_CATALOG_URL`, `G6_DELIVERY_URL`.
5. Base de datos PostgreSQL provista por Supabase (no por Render).

URL pública: `https://api-grupo5-pedidos.onrender.com`

---

## 11. Gaps conocidos

- **Sin polling ni consumo de eventos automático desde G6**: la transición `SHIPPED`→`DELIVERED` requiere un trigger manual o externo hasta que G6 tenga su worker de eventos activo.
- **Idempotencia basada en `LIKE` sobre `notes`**, no en una columna dedicada con índice único.
- **No hay endpoint de salud separado** (`/` cumple esa función como health check liviano, sin tocar la BD).
- **No hay pipeline de CI/CD automatizado** (GitHub Actions) — el deploy en Render se dispara por auto-deploy al hacer push a `main`, pero no hay step de lint/test previo documentado.
- **`requirements.txt` no fija versiones exactas** (usa `>=`), lo que puede causar drift entre el entorno local y producción si una dependencia saca una versión incompatible.
