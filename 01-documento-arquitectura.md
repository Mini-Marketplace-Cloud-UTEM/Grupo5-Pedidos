# Documento de Arquitectura — Grupo 5: Pedidos (Order Management)

**Proyecto:** Mini Marketplace Cloud — INFE6001-411-TEORIA-2026-1
**Servicio:** `order-service`
**Versión:** 1.2.0 (alineada con auditoría de contratos cruzados G3, G4, G8 y G6 v1.2 Multi-Origen)

> ⚠️ **Nota sobre numeración de grupos:** el enunciado del curso numera
> "Grupo 6 = Inventario" y "Grupo 7 = Despacho" como equipos separados. En
> la organización real de GitHub (`Mini-Marketplace-Cloud-UTEM`), **Grupo 4
> absorbió Carrito + Checkout + Inventario**, **Grupo 6 = Despacho**,
> **Grupo 7 = Reportería**, **Grupo 8 = Pagos + Notificaciones**. Este
> documento usa la numeración **real** del repo. Donde difiera con el
> enunciado, se indica.

---

## 1. Responsabilidad

Crear y administrar el ciclo de vida de un pedido desde que el checkout se
confirma hasta que se entrega o se cancela. Es el núcleo transaccional del
sistema y el servicio de mayor impacto si cambia su contrato sin avisar.

**Decisión v1.1:** G5 asume la responsabilidad de iniciar la transacción
monetaria, invocando `POST /v1/payments` de G8 inmediatamente después de
persistir la orden en estado `CREATED`. Esto resuelve el gap de "orquestación
huérfana" detectado en la revisión de contratos cruzados.

No valida stock — eso ya ocurrió en G4 antes de llamar a `POST /orders`.

---

## 2. Dueño del dato

`Order` y `OrderItem`. Nadie más escribe directamente sobre estas tablas.
Los datos monetarios se almacenan exclusivamente como enteros en CLP.

---

## 3. Posición en el ecosistema (flujo real sincronizado)

```text
Frontend (G1) ──► BFF (G1) ──► Checkout (G4)
                                   │
                       1. valida stock, reserva inventario
                       2. POST /orders  (crea el pedido en G5,
                          stock ya reservado, montos en CLP/integer)
                                   │
                                   ▼
                          order-service (G5)  status = CREATED
                                   │
                       3. G5 inicia pago → POST /v1/payments (G8)
                          status = PAYMENT_PENDING
                                   │
                    4. G8 publica PAYMENT_APPROVED / PAYMENT_REJECTED
                                   │
                                   ▼
                          G5 consume el evento
                          status = PAID  (o FAILED + ORDER_CANCELLED si rechazado)
                                   │
                       5. G5 consulta Catálogo → GET /products/{id} (G3)
                          (obtiene originCd, peso y dimensiones para G6)
                                   │
                       6. G5 crea envíos (Multi-Origen) → POST /api/v1/shipments (G6)
                          G6 retorna arreglo de IDs: ["SHP-1", "SHP-2"]
                          status = READY_TO_SHIP
                                   │
                       7. Polling iterativo → GET /api/v1/shipments/{shipmentId} (G6)
                          status = SHIPPED (cuando TODAS las cajas digan IN_TRANSIT)
                          status = DELIVERED (cuando TODAS digan DELIVERED)
                                   │
                       8. G5 publica ORDER_CREATED / ORDER_STATUS_CHANGED /
                          ORDER_CANCELLED → G7 (Reportería) y G8 (Notif.)
```

---

## 4. Modelo de datos

```text
Order
 ├─ orderId          string    PK negocio, formato ORD-YYYYMMDD-NNN
 ├─ userId           uuid      FK lógica a G2 (Auth)
 ├─ status           enum      ver §5
 ├─ items[]          OrderItem[]
 ├─ shipmentIds      string[]  Lista de IDs físicos en G6 (soporte Multi-Origen v1.2)
 ├─ shippingAddress  object?   nullable — G4 no lo captura aún (ver §9, gap 3)
 ├─ subtotal         integer   CLP, sin decimales
 ├─ shippingCost     integer   CLP
 ├─ totalAmount      integer   CLP
 ├─ currency         enum      [CLP]
 ├─ idempotencyKey   uuid      deduplicación de creación (no se expone en GET)
 ├─ notes            string?
 └─ createdAt / updatedAt      date-time UTC

OrderItem  (embebido en Order, no tabla propia expuesta)
 ├─ productId   uuid     FK lógica a G3 (Catálogo)
 ├─ name        string   snapshot al momento de compra
 ├─ quantity    integer
 ├─ unitPrice   integer  CLP
 └─ subtotal    integer  CLP
```

**Por qué `name` y `unitPrice` son snapshots:** si G3 cambia precio o nombre
después de la compra, el pedido histórico no debe cambiar retroactivamente.
G4 resuelve esos valores contra G3 al momento del checkout y los entrega ya
resueltos en el `POST /orders`.

---

## 5. Máquina de estados

```mermaid
stateDiagram-v2
    [*] --> CREATED: G4 llama POST /orders\n(stock ya reservado)
    CREATED --> PAYMENT_PENDING: G5 llama POST /payments (G8)
    PAYMENT_PENDING --> PAID: evento PAYMENT_APPROVED (G8)
    PAYMENT_PENDING --> FAILED: evento PAYMENT_REJECTED (G8)
    FAILED --> [*]: G5 publica ORDER_STATUS_CHANGED(FAILED)\ny ORDER_CANCELLED
    CREATED --> CANCELLED: cancelación antes de pagar
    PAID --> READY_TO_SHIP: G5 envía array de cajas a G6
    READY_TO_SHIP --> SHIPPED: TODOS los shipmentIds == IN_TRANSIT
    SHIPPED --> DELIVERED: TODOS los shipmentIds == DELIVERED
    READY_TO_SHIP --> FAILED: Al menos un shipmentId falla
    PAID --> CANCELLED: cancelación post-pago\n(reembolso fuera de alcance)
    CANCELLED --> [*]
    DELIVERED --> [*]
```

> **Nota sobre `STOCK_RESERVED`:** este estado existe en el enum por
> compatibilidad con la tabla de mapeo acordada con el BFF
> (`canonical-models.md`), pero en la práctica el stock ya está reservado por
> G4 antes de que el pedido exista en G5. Se considera implícito en `CREATED`.

---

## 6. Contratos que expone

Ver `contrato/openapi.yaml` (REST) y `contrato/events.md` (eventos Pub/Sub).

| Tipo | Contrato |
| --- | --- |
| `POST /orders` | Crear pedido — llamado por G4 |
| `GET /orders/{orderId}` | Detalle de un pedido |
| `PATCH /orders/{orderId}/status` | Transición de estado (uso interno) |
| `GET /users/{userId}/orders` | Listado paginado — consumido por G1 (BFF) |
| Publica `ORDER_CREATED` | Al registrar la orden exitosamente |
| Publica `ORDER_STATUS_CHANGED` | En cada transición de estado (incluye FAILED) |
| Publica `ORDER_CANCELLED` | Por fallo de pago o despacho parcial/total |
| Consume `PAYMENT_APPROVED` / `PAYMENT_REJECTED` / `PAYMENT_PENDING` | De G8 |

---

## 7. Seguridad y trazabilidad

* Todo endpoint recibe `Authorization: Bearer <token>`.
* Antes de procesar, G5 valida el token contra `POST /auth/validate` de G2.
* Las llamadas salientes hacia G6 inyectan obligatoriamente:
  `X-Request-Id` (UUID nuevo por llamada), `X-Correlation-Id` (del pedido) y
  `X-Consumer: G5-Pedidos`.

---

## 8. Idempotencia

`POST /orders` requiere el header `Idempotency-Key: <uuid>`. Si la misma clave llega dos veces:

* Mismo body → responde `200` con el pedido ya creado (sin duplicar).
* Body distinto → `409 DUPLICATED_ORDER`.

---

## 9. Gaps de integración (estado actual)

1. **G6 sin worker de Outbox + Multi-Origen (bloqueante temporal):** G6 no despacha eventos a Kafka aún. G5 usa polling periódico, el cual debe iterar sobre la ruta `GET /api/v1/shipments/{shipmentId}` por *cada* caja física del pedido para agregar los estados.
2. **Incompatibilidad monetaria con G4 (bloqueante crítico):** G4 envía montos en USD/float. G5 rechaza estrictamente cualquier `currency` distinto a `CLP`.
3. **`shippingAddress` ausente en Checkout (deuda técnica):** G4 no propaga el objeto `shippingAddress`. G5 lo acepta como `nullable`.
4. **`registro-de-servicios.md` pendiente:** La URL de G5 no está en el registro oficial.

---

## 10. Stack recomendado

* **Python 3.12 + FastAPI**
* **Pydantic v2** con `alias_generator` camelCase
* **PostgreSQL** vía SQLAlchemy
* **Docker**

---

## 11. Despliegue

* Cloud: Render Free (API) + Supabase (PostgreSQL).
