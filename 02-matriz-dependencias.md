# Matriz de Dependencias — Grupo 5: Pedidos (Order Management)

Convención de la columna **Estado**:

- ✅ Contrato verificado e integración técnica confirmada en repositorio real.
- 🟡 Contrato definido de mutuo acuerdo, pero el servicio no está desplegado o requiere ajustes menores.
- 🔴 Dependencia bloqueada, riesgo crítico de integración o desalineación de esquemas.

---

## 5.1 — Quiénes dependen de Grupo 5 (Consumidores)

| Grupo | Qué consume | Protocolo | Detalle técnico | Estado |
|:---|:---|:---|:---|:---|
| **G4 — Carrito y Checkout** | Creación del registro definitivo del pedido | REST síncrono (entrante) | Invoca `POST /orders`. G4 tiene mapeado `ORDER_SERVICE_UNAVAILABLE` como error estructurado en su contrato. | 🔴 G4 envía montos en USD/float y omite `shippingAddress` — requiere mesa de diseño |
| **G1 — BFF / Frontend** | Consulta de pedidos históricos y estados en pantalla | REST síncrono | Consume `GET /orders/{orderId}` y `GET /users/{userId}/orders` | 🟡 Contrato listo; pendiente despliegue del BFF en cloud |
| **G7 — Reportería** | Ingesta de datos comerciales para dashboards en tiempo real | Evento async (Kafka) | Escucha `ORDER_CREATED` y `ORDER_STATUS_CHANGED`. Confirmado en `x-events.consumed` de su contrato. | ✅ Contrato alineado |
| **G8 — Notificaciones** | Alertas transaccionales al usuario final | Evento async (Kafka) | Escucha `ORDER_CREATED`, `ORDER_STATUS_CHANGED` y `ORDER_CANCELLED`. | ✅ Contrato alineado |

---

## 5.2 — De quiénes depende Grupo 5 (Proveedores)

| Grupo | Qué necesita G5 | Protocolo | Detalle técnico | Estado |
|:---|:---|:---|:---|:---|
| **G2 — Identidad** | Validación centralizada de JWT y RBAC | REST síncrono (saliente) | Invoca `POST /auth/validate` con el token Bearer. | ✅ Confirmado contra entorno real |
| **G8 — Pagos** | Procesamiento monetario y resultado transaccional | Híbrido REST + Evento | G5 invoca `POST /v1/payments` síncrono; luego consume `PAYMENT_APPROVED` o `PAYMENT_REJECTED` async. | ✅ Sincronizado en CLP e integers (int64) |
| **G6 — Despacho** | Creación de envíos físicos (Multi-Origen) y tracking | REST síncrono + polling | Invoca `POST /api/v1/shipments` con arreglo `packages` para recibir múltiples `shipmentIds`. Ejecuta polling iterativo a `GET /api/v1/shipments/{shipmentId}` inyectando headers obligatorios. | 🔴 Eventos bloqueados; endpoint exige datos volumétricos y `originCd` por ítem. |
| **G3 — Catálogo** | Datos volumétricos y origen de los ítems | REST síncrono (saliente) | **Nueva dependencia.** Invoca `GET /products/{productId}` para extraer `originCd`, peso y dimensiones requeridos por G6. | 🟡 Contrato existe en la malla; pendiente implementar cliente HTTP en G5 |

---

## 5.3 — Matriz cruzada de conectividad

| | G1 BFF | G2 Auth | G3 Catálogo | G4 Checkout | G6 Despacho | G7 Reportería | G8 Pagos | G8 Notif |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **G5 envía →** | — | ❌ | ❌ | ❌ | ✅ REST | ✅ Evento | ✅ REST | ✅ Evento |
| **G5 recibe ←** | ❌ | ✅ REST | 🟡 REST | 🔴 REST | 🔴 Polling | ❌ | ✅ Evento | ❌ |

---

## 5.4 — Riesgos priorizados de integración

### 🔴 Riesgo 1 — Datos volumétricos y de Origen requeridos por G6 v1.2 (Bloqueante crítico)

G6 actualizó su API para soportar envíos Multi-Origen. Ahora exige un arreglo `packages` donde cada ítem contenga `originCd` (NORTE, CENTRO, SUR), peso en gramos y dimensiones en centímetros en su `POST /api/v1/shipments`. G4 no provee estos datos.
G5 debe introducir una llamada síncrona a **G3 (Catálogo)** por cada ítem del carrito para poblar este arreglo.

**Impacto:** El flujo logístico se vuelve:
`PAID → GET /products/{id} (G3) → POST /api/v1/shipments (G6) → Retorna Array de IDs → READY_TO_SHIP`

### 🔴 Riesgo 2 — Quiebre de esquema monetario con G4 (Bloqueante crítico)

El contrato de G4 procesa transacciones en `USD` con subtotales en `double`.
Esto colisiona directamente con el estándar del marketplace (G5 y G8 operan
exclusivamente en `CLP` con tipo `integer/int64`). Se requiere mesa de diseño
con G4 para corregir tipos antes de iniciar la codificación.

**Acción requerida:** G4 debe actualizar su `contrato-g4.yaml` para emitir
`currency: "CLP"` y `totalAmount: integer`.

### 🔴 Riesgo 3 — Ausencia de `shippingAddress` en Checkout (Bloqueante crítico)

El endpoint `/v1/checkout` de G4 no captura ni propaga el objeto
`shippingAddress` hacia G5. Como mitigación, G5 acepta el campo como
`nullable` en su `openapi.yaml`, delegando al BFF (G1) la responsabilidad de
resolver la dirección.

### 🟡 Riesgo 4 — Polling iterativo sobre capa gratuita de Render (Riesgo de performance)

Con la actualización v1.2 de G6, un solo pedido puede generar 3 `shipmentIds` distintos. El polling periódico a G6 (cada 60 s) se multiplicará por la cantidad de cajas, lo que puede saturar las instancias en la capa gratuita de Render (N+1 query problem). Este riesgo se elimina drásticamente cuando G6 active su worker de Kafka (upgrade a `events.md v1.1`).
