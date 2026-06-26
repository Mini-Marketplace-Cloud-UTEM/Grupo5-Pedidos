# Modelo de Datos — Grupo 5 Pedidos (v1.2.0)

Este documento detalla la estructura lógica de los datos administrados por el servicio de pedidos (`order-service`) y su traducción directa a los validadores de tipos en código (`app/schemas.py`).

---

## 1. Entidades Principales

### `Order` (Pedido)
Representa la orden de compra transaccionada. En código FastAPI, su validación de tipos e integridad de red se rige mediante el esquema `OrderResponse`.

| Campo | Tipo en Código | Requerido | Descripción |
| --- | --- | --- | --- |
| `orderId` | `str` (Pattern) | ✅ | PK de negocio. Formato estricto: `ORD-YYYYMMDD-NNN`. |
| `userId` | `UUID` | ✅ | Identificador del comprador. FK lógica a Grupo 2 (Auth). |
| `status` | `str` (Enum) | ✅ | Estado operativo del pedido (Ver máquina de estados abajo). |
| `items` | `List[OrderItem]` | ✅ | Contenedor de líneas de productos comprados (Mínimo 1). |
| `shipmentIds` | `List[str]` | ✅ | **Soporte Multi-Origen G6 v1.2:** Lista de códigos físicos de seguimiento devueltos por Logística. |
| `shippingAddress` | `ShippingAddress \| null` | — | **Mitigación G4:** Pasa a ser opcional (`nullable`). Si Checkout no lo provee, se guarda nulo. |
| `subtotal` | `StrictInt` (CLP) | ✅ | Suma de subtotales de ítems. Sin decimales. |
| `shippingCost` | `StrictInt` (CLP) | ✅ | Costo logístico calculado. Fijo en `$3500` para la fase de Mock. |
| `totalAmount` | `StrictInt` (CLP) | ✅ | Monto final cobrado (`subtotal + shippingCost`). |
| `currency` | `str` (Enum) | ✅ | Restringido estrictamente a `"CLP"`. |
| `notes` | `str \| null` | — | Comentarios opcionales ingresados por el comprador. |
| `createdAt` | `datetime` (UTC) | ✅ | Timestamp de inserción en el sistema. |
| `updatedAt` | `datetime` (UTC) | ✅ | Timestamp del último cambio de estado. |

*Nota sobre persistencia transaccional:* Los campos monetarios utilizan `StrictInt` de Pydantic v2. Esto actúa como cortafuegos directo en la red; si un servicio externo envía montos con decimales (floats), la API abortará la operación de inmediato.

---

### `OrderItem` (Línea de pedido)
Esquema embebido que congela las condiciones comerciales del producto al momento exacto en que se efectúa la compra.

| Campo | Tipo en Código | Requerido | Descripción |
| --- | --- | --- | --- |
| `productId` | `UUID` | ✅ | FK lógica al maestro de productos en Grupo 3 (Catálogo). |
| `name` | `str` | ✅ | Snapshot del nombre del artículo. Previene desajustes si Catálogo edita el producto en el futuro. |
| `quantity` | `int` (gt: 0) | ✅ | Unidades adquiridas. Validado para ser estrictamente mayor a cero. |
| `unitPrice` | `StrictInt` (CLP) | ✅ | Snapshot del precio unitario al momento de la transacción. |
| `subtotal` | `StrictInt` (CLP) | ✅ | Multiplicación matemática verificada por la API: `quantity × unitPrice`. |

---

### `ShippingAddress` (Dirección de despacho)
Estructura de destino físico del paquete. Puede instanciarse como objeto nulo.

| Campo | Tipo en Código | Requerido | Descripción |
| --- | --- | --- | --- |
| `street` | `str` | ✅ | Avenida, calle, pasaje y numeración domiciliaria. |
| `city` | `str` | ✅ | Comuna / Ciudad de destino. |
| `region` | `str` | ✅ | Región / Provincia de despacho. |
| `country` | `str` | ✅ | País (Por defecto Chile). |
| `postalCode` | `str \| null` | — | Código postal opcional. |

---

## 2. Máquina de Estados del Pedido (Agregación Logística)

Debido a que el **Grupo 6 (Logística)** opera bajo una arquitectura Multi-Origen (v1.2), un solo pedido puede fragmentarse en múltiples cajas independientes (`shipmentIds`). La transición global de la orden en el Grupo 5 se calcula agregando los estados individuales de cada una:

```text
  [CREATED] ──► [PAYMENT_PENDING] ──► [PAID] ──► [READY_TO_SHIP] ──► [SHIPPED] ──► [DELIVERED]
                         │                              │
                         ▼                              ▼
                      [FAILED]                      [CANCELLED]
```

### Tabla de Reglas de Transición y Disparadores

| Desde Estado | Hacia Estado | Disparador y Lógica de Negocio Asociada |
| --- | --- | --- |
| `[*] (Inicio)` | `CREATED` | **Grupo 4** invoca con éxito el endpoint `POST /orders`. El inventario ya fue descontado previamente por G4. |
| `CREATED` | `PAYMENT_PENDING` | Lógica interna de **Grupo 5**. Ocurre inmediatamente al persistir el pedido e invocar `POST /v1/payments` del Grupo 8. |
| `PAYMENT_PENDING` | `PAID` | El **Grupo 8 (Pagos)** publica el evento asíncrono `PAYMENT_APPROVED`. |
| `PAYMENT_PENDING` | `FAILED` | El **Grupo 8 (Pagos)** publica el evento asíncrono `PAYMENT_REJECTED`. |
| `PAID` | `READY_TO_SHIP` | **Grupo 5** consulta dimensiones a G3, envía el array de paquetes a **Grupo 6** (`POST /api/v1/shipments`) y almacena los `shipmentIds` devueltos. |
| `READY_TO_SHIP` | `SHIPPED` | El worker de polling de **Grupo 5** detecta que **TODAS** las cajas en G6 pasaron al estado `IN_TRANSIT`. |
| `SHIPPED` | `DELIVERED` | El worker de polling de **Grupo 5** detecta que **TODAS** las cajas en G6 alcanzaron el estado `DELIVERED`. Estado final. |
| `READY_TO_SHIP` | `CANCELLED` | El worker de polling detecta que **AL MENOS UNA** de las cajas asociadas al pedido devolvió el estado `FAILED` en G6. |

---

## 3. Origen de Datos (Límites del Servicio)

Para evitar el acoplamiento y la duplicidad de datos en la malla, el Grupo 5 define estrictamente qué registros controla y cuáles consulta bajo demanda:

| Dominio del Dato | Proveedor de la Verdad | Mecanismo de Consumo en G5 |
| --- | --- | --- |
| **Estructura y Ciclo de Pedidos** | **Grupo 5 (Propio)** | Acceso total de lectura/escritura en base de datos. |
| **Identidad y Roles (`userId`)** | **Grupo 2 (Auth)** | REST Síncrono a `POST /auth/validate` enviando el token Bearer. |
| **Metadatos Físicos del Producto** | **Grupo 3 (Catálogo)** | REST Síncrono a `GET /products/{id}` para obtener el origen, peso y volumen. |
| **Flujo de Pago Transaccional** | **Grupo 8 (Pagos)** | Suscripción asíncrona a tópicos de Kafka (Eventos de Aprobación/Rechazo). |
| **Tracking y Cajas Físicas** | **Grupo 6 (Despacho)** | REST Síncrono inicial + Polling iterativo REST temporal a su API v1.2. |

---

## 4. Gestión Estándar de Errores de Red

Las validaciones nativas de FastAPI y los middlewares del Grupo 5 responden usando una estructura JSON unificada para inyectar predictibilidad al BFF (Grupo 1):

```json
{
  "code": "CÓDIGO_INTERNO_UPPER_SNAKE_CASE",
  "message": "Explicación humana detallada del error.",
  "details": null,
  "correlationId": "uuid-de-trazabilidad-transversal"
}
```

### Catálogo de Errores Oficiales del Servicio

| Código de Error Interno | HTTP Status | Escenario de Gatillo de Red |
| --- | --- | --- |
| `MISSING_IDEMPOTENCY_KEY` | `400 Bad Request` | Petición `POST /orders` sin la cabecera `Idempotency-Key`. Evita duplicidad de cobros. |
| `INVALID_CURRENCY` | `400 Bad Request` | Cortafuegos monetario. **Grupo 4** intentó mandar divisas alternativas (ej. `USD`). |
| `INVALID_AMOUNT` | `422 Unprocessable Entity` | Cortafuegos de tipos. Saltó el validador `StrictInt` porque venían decimales en los precios. |
| `UNAUTHORIZED` | `401 Unauthorized` | El token JWT de Grupo 2 no viene en las cabeceras o la firma expiró. |
| `FORBIDDEN` | `403 Forbidden` | El token es válido pero el `userId` no coincide con el dueño de la orden consultada. |
| `ORDER_NOT_FOUND` | `404 Not Found` | El formato del `orderId` en la ruta es correcto, pero no existe en los registros. |
| `DUPLICATED_ORDER` | `409 Conflict` | Intento de reenvío con la misma `Idempotency-Key` pero modificando el cuerpo del JSON. |
| `INVALID_STATUS_TRANSITION` | `409 Conflict` | Intento ilegal de alterar el ciclo de vida (ej. transicionar de `DELIVERED` hacia `PAID`). |
