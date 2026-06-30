# 📦 Grupo 5 — Order Management Service

> **Mini Marketplace Cloud · INFE6001-411-TEORIA-2026-1**  
> Servicio central del ecosistema: administra el ciclo de vida completo de un pedido.

---

## 🔗 Links rápidos

| Recurso | URL |
|---------|-----|
| 🌐 Mock (E2 — Prism) | `https://grupo5-pedidos-mock.onrender.com` |
| 🚀 Producción (E3 — FastAPI real) | `https://api-grupo5-pedidos.onrender.com` |
| 📄 Swagger UI (producción) | `https://api-grupo5-pedidos.onrender.com/docs` |
| 📋 OpenAPI YAML | [`contrato/openapi.yaml`](contrato/openapi.yaml) |
| 🗃️ Esquema de datos | [`modelo-de-datos.md`](modelo-de-datos.md) |
| 📬 Colección Postman | [`tests/postman_collection.json`](tests/postman_collection.json) |
| 📡 Contrato de eventos | [`contrato/events.md`](contrato/events.md) |

---

## ¿Qué hace este servicio?

Recibe un pedido ya validado desde **Grupo 4 (Checkout)**, lo persiste con estado `CREATED` y administra todas las transiciones hasta `DELIVERED` o `CANCELLED`. Es el servicio que más grupos consumen en el ecosistema.

**No valida stock ni precio** — eso lo hace G4 antes de llamar a este servicio.

---

## Endpoints disponibles en el mock

| Método | Path | Descripción |
|--------|------|-------------|
| `GET` | `/` | Health check liviano — sin autenticación (no valida BD) |
| `POST` | `/orders` | Crear pedido · requiere `Idempotency-Key` header |
| `GET` | `/orders/{orderId}` | Detalle de un pedido |
| `GET` | `/users/{userId}/orders?page=&pageSize=` | Listado paginado por usuario |
| `PATCH` | `/orders/{orderId}/status` | Transición de estado |

> ⚠️ El servicio real (E3) no usa prefijo `/v1` — ver `TECHNICAL.md` sección 11 (Gaps conocidos).

Todos los endpoints (excepto `/`) requieren `Authorization: Bearer <token>`.

### Ejemplo rápido — crear un pedido

```bash
curl -X POST https://api-grupo5-pedidos.onrender.com/orders \
  -H "Authorization: Bearer <token>" \
  -H "Idempotency-Key: f47ac10b-58cc-4372-a567-0e02b2c3d479" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "e9d8c7b6-a543-2109-8765-fedcba098765",
    "items": [
      {
        "productId": "f0e9d8c7-b6a5-4321-0987-fedcba098765",
        "name": "Notebook Lenovo IdeaPad",
        "quantity": 2,
        "unitPrice": 799990,
        "subtotal": 1599980
      }
    ],
    "shippingAddress": {
      "street": "Av. Libertador 1234",
      "city": "Santiago",
      "region": "Metropolitana",
      "country": "Chile"
    },
    "subtotal": 1599980,
    "shippingCost": 4990,
    "totalAmount": 1604970
  }'
```

---

## Máquina de estados

```
CREATED → PAYMENT_PENDING → PAID → READY_TO_SHIP → SHIPPED → DELIVERED
    │              │
    └─ CANCELLED   └─ FAILED
```

Transiciones no permitidas retornan `409 INVALID_STATUS_TRANSITION`.

---

## Eventos publicados

| Evento | Cuándo | Consumidores |
|--------|--------|--------------|
| `ORDER_CREATED` | Al crear el pedido | G7 Reportería, G9 Notificaciones |
| `ORDER_STATUS_CHANGED` | Cada transición de estado | G7, G9 |
| `ORDER_CANCELLED` | Al cancelar o fallar | G7, G9 |

Ver payloads completos en [`contrato/events.md`](contrato/events.md).

---

## Grupos que deben integrar con este servicio

| Grupo | Relación | Qué necesitan |
|-------|----------|---------------|
| **G4 Checkout** | Llama `POST /orders` | Body con items, dirección y montos ya validados |
| **G1 BFF** | Consulta estado | `GET /orders/{orderId}` y `GET /orders?userId=` |
| **G6 Pagos** | Publica eventos que G5 consume | `PAYMENT_APPROVED` / `PAYMENT_REJECTED` |
| **G7 Reportería** | Consume eventos | `ORDER_CREATED`, `ORDER_STATUS_CHANGED` |
| **G8 Despacho** | G5 llama a crear envío | `POST /api/v1/shipments` tras `PAID` |
| **G9 Notificaciones** | Consume eventos | `ORDER_CREATED`, `ORDER_STATUS_CHANGED`, `ORDER_CANCELLED` |

---

## Cómo probar

1. Importar [`tests/postman_collection.json`](tests/postman_collection.json) en Postman.
2. Configurar las variables de entorno:
   - `baseUrl` → `https://api-grupo5-pedidos.onrender.com`
   - `authToken` → `Bearer <jwt-de-G2>`
   - `userId` → UUID del usuario de prueba

Con Newman (CLI):
```bash
npm install -g newman
newman run tests/postman_collection.json \
  --env-var "baseUrl=https://api-grupo5-pedidos.onrender.com" \
  --env-var "authToken=Bearer mock-token" \
  --env-var "userId=e9d8c7b6-a543-2109-8765-fedcba098765"
```

---

## Estructura del repositorio

```
Grupo5-Pedidos/
├── README.md                    ← este archivo
├── TECHNICAL.md                 ← documentación interna de implementación
├── app/                          ← código fuente del servicio real (FastAPI)
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── events_logger.py
├── contrato/
│   ├── openapi.yaml             ← contrato REST (OpenAPI 3.0.3)
│   └── events.md                ← contrato de eventos Pub/Sub
├── docs/
│   └── entregables-E2.md        ← guía de operación y pruebas del mock
├── tests/
│   └── postman_collection.json  ← colección de pruebas
├── modelo-de-datos.md
├── seed.py                      ← script para poblar la BD con datos de prueba
├── Dockerfile.txt
└── requirements.txt
```

---

## Equipo

**Grupo 5 — INFE6001-411-TEORIA-2026-1**
