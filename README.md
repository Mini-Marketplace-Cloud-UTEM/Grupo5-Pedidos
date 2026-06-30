# 📦 Grupo 5 — Order Management Service

> **Mini Marketplace Cloud · INFE6001-411-TEORIA-2026-1**  
> Servicio central del ecosistema: administra el ciclo de vida completo de un pedido.

---

## 🔗 Links rápidos

| Recurso | URL |
|---------|-----|
| 🌐 Mock público (Render) | `https://grupo5-pedidos.onrender.com/v1` |
| 📄 Swagger UI | `https://grupo5-pedidos.onrender.com/docs` |
| 📋 OpenAPI YAML | [`contrato/openapi.yaml`](contrato/openapi.yaml) |
| 🗃️ Esquema SQL | [`app/schema.py`](app/schema.py) |
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
| `GET` | `/v1/health` | Health check — sin autenticación |
| `POST` | `/v1/orders` | Crear pedido · requiere `Idempotency-Key` header |
| `GET` | `/v1/orders/{orderId}` | Detalle de un pedido |
| `GET` | `/v1/orders?userId=&page=&pageSize=` | Listado paginado por usuario |
| `PATCH` | `/v1/orders/{orderId}/status` | Transición de estado |

Todos los endpoints (excepto `/health`) requieren `Authorization: Bearer <token>`.

### Ejemplo rápido — crear un pedido

```bash
curl -X POST https://grupo5-pedidos.onrender.com/v1/orders \
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

Ver payloads completos en [`eventos/events-schema.json`](eventos/events-schema.json).

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

1. Importar [`pruebas/postman-collection.json`](pruebas/postman-collection.json) en Postman.
2. Configurar las variables de entorno:
   - `baseUrl` → `https://grupo5-pedidos.onrender.com/v1`
   - `authToken` → `Bearer <jwt-de-G2>`
   - `userId` → UUID del usuario de prueba
3. Ejecutar la carpeta **"1. Flujo Feliz"** para el camino completo, luego **"2. Casos de borde"** para errores.

Con Newman (CLI):
```bash
npm install -g newman
newman run pruebas/postman-collection.json \
  --env-var "baseUrl=https://grupo5-pedidos.onrender.com/v1" \
  --env-var "authToken=Bearer mock-token" \
  --env-var "userId=e9d8c7b6-a543-2109-8765-fedcba098765"
```

---

## Estructura del repositorio

```
Grupo5-Pedidos/
├── README.md                    ← este archivo
├── TECHNICAL.md                 ← documentación interna de implementación
├── contrato/
│   └── openapi.yaml             ← contrato REST (OpenAPI 3.0.3)
├── eventos/
│   └── events-schema.json       ← esquemas JSON de eventos pub/sub
├── sql/
│   └── schema.sql               ← esquema físico PostgreSQL
└── pruebas/
    └── postman-collection.json  ← colección de pruebas
```

---

## Equipo

**Grupo 5 — INFE6001-411-TEORIA-2026-1**
