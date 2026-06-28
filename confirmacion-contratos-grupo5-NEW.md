# Confirmación de Contratos y Eventos - Grupo 5 (Pedidos)

Hola a todos, para avanzar con la **Fase E3** y la integración de los servicios, les confirmo los detalles técnicos del **Grupo 5 (Pedidos)** basándome en la matriz de alineación:

---

## 1. Tópico Pub/Sub

- **Tópico:** `OrderCreated`

---

## 2. Esquema JSON (`OrderCreatedPayload`)

Validado según nuestro contrato de integración. Confirmamos que `totalAmount` se envía estrictamente como número (tipo numérico, no string) para asegurar la integridad monetaria, y `createdAt` sigue el formato solicitado.

```json
{
  "eventId": "evt-5a3b2c11-0000-4000-8000-000000000005",
  "eventType": "OrderCreated",
  "version": "1.2",
  "producer": "group-5-pedidos",
  "correlationId": "99999999-8888-4777-9666-555555555555",
  "payload": {
    "orderId": "ORD-20260627-001",
    "userId": "user-uuid-123",
    "status": "CREATED",
    "totalAmount": 1599980,
    "currency": "CLP",
    "createdAt": "2026-06-27T14:30:00Z",
    "items": [
      {
        "productId": "prod-uuid-456",
        "name": "Producto Ejemplo",
        "quantity": 2,
        "unitPrice": 799990,
        "subtotal": 1599980
      }
    ]
  }
}
```

---

## 3. Formato de Fechas

Todos nuestros campos de fecha (`createdAt` y otros asociados) se envían estrictamente en formato **ISO 8601 con zona horaria UTC**.

> Ejemplo: `2026-06-27T14:30:00Z`

---

## 4. Ruta de Logs (Supabase Storage)

Para el recálculo batch, depositaremos los archivos en el bucket `event-logs` con la siguiente estructura, permitiendo una lectura ordenada por fecha:

- **Ruta:** `group-5-pedidos/year=2026/month=06/`
- **Formato de archivo:** `YYYY-MM-DD-events.jsonl` (JSON Lines)

---

Quedo atento a cualquier comentario. ¡Saludos!
