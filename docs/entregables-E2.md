# Guía de Operación y Pruebas del Mock (Fase E2) — Grupo 5 Pedidos

## 1. URLs de los Entornos Operativos

Para la Fase E2, el Grupo 5 dispone de dos mecanismos complementarios para servir el contrato:

| Entorno | URL / Comando | Tipo | Implementación | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Público (Cloud)** | `https://grupo5-pedidos-mock.onrender.com` | Mock Estático | Prism (Stoplight) | ✅ Desplegado |
| **Local (Laptop)** | `http://localhost:8050` | Mock Dinámico | FastAPI (`app/main.py`) | ✅ Operativo |

---

## 2. Nota de Despliegue en Cloud (Render)

> ⚠️ **Control de Errores Crítico:** La versión actual de Prism presenta un bug de compatibilidad con el módulo `cluster` de Node.js 24.x si se ejecuta con su configuración por defecto (`--multiprocess=true`). Esto causa caídas intermitentes del contenedor en la capa gratuita de Render.

Para mitigar este fallo, el **Start Command** en la configuración de Render se modificó explícitamente para desactivar el multiprocesamiento:

```bash
npx @stoplight/prism-cli mock contrato/openapi.yaml --host 0.0.0.0 --port $PORT --multiprocess=false
```

*Nota: Si el equipo realiza un redespliegue o cambia de cuenta en Render, este flag debe mantenerse de forma obligatoria.*

---

## 3. Pruebas de Integración Temprana vía `curl`

Los siguientes comandos están adaptados a las reglas de negocio fijadas en la Fase E1. Puedes ejecutarlos apuntando al entorno local (`http://localhost:8050`) o al cloud de Render.

### Caso A: Creación de Pedido Exitoso (Camino Feliz — Simulación G4 Checkout)

Envía los montos estrictamente como enteros en CLP. La dirección de envío puede ir como `null` en caso de que el Grupo 4 no la arrastre desde el carrito.

```bash
curl -X POST http://localhost:8050/orders \
  -H "Authorization: Bearer test-token-grupo2" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Correlation-Id: 99999999-8888-4777-9666-555555555555" \
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
    "shippingAddress": null,
    "notes": "Checkout sin dirección. G5 procesa multi-origen con G6."
  }'
```

- **Respuesta esperada (201 Created):** Retorna el objeto de la orden incluyendo el arreglo de control logístico exigido por la v1.2 de G6: `"shipmentIds": ["SHP-mock-1", "SHP-mock-2"]`.

### Caso B: Diseño Defensivo (Rechazo de decimales/USD de G4)

Prueba de esfuerzo para verificar que los validadores de Pydantic bloquean payloads flotantes o monedas incorrectas de otros servicios.

```bash
curl -X POST http://localhost:8050/orders \
  -H "Authorization: Bearer test-token-grupo2" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440001" \
  -d '{
    "userId": "e9d8c7b6-a543-2109-8765-fedcba098765",
    "items": [
      {
        "productId": "f0e9d8c7-b6a5-4321-0987-fedcba098765",
        "name": "Notebook Lenovo IdeaPad",
        "quantity": 1,
        "unitPrice": 1599.98,
        "subtotal": 1599.98
      }
    ]
  }'
```

- **Respuesta esperada (422 Unprocessable Entity / 400 Bad Request):** El sistema rechaza la petición debido a que `unitPrice` no cumple con la restricción de entero estricto (`StrictInt`).

### Caso C: Consulta de Pedido por ID (Uso del BFF / Grupo 1)

```bash
curl -X GET http://localhost:8050/orders/ORD-20260626-001 \
  -H "Authorization: Bearer test-token-grupo2"
```

### Caso D: Simulación de Transición de Estado (Manejo de Ciclo de Vida Interno)

```bash
curl -X PATCH http://localhost:8050/orders/ORD-20260626-001/status \
  -H "Authorization: Bearer test-token-grupo2" \
  -H "Content-Type: application/json" \
  -d '{"status": "PAID"}'
```

---

## 4. Pruebas Automatizadas (Postman / Bruno)

El archivo de la colección de pruebas ha sido reubicado y actualizado dentro de la nueva arquitectura limpia en:
`tests/postman_collection.json`

Para ejecutar la suite de pruebas:

1. Abre tu cliente de API (Postman / Bruno / Insomnia).
2. Importa el archivo JSON de la carpeta `tests/`.
3. Ajusta la variable de entorno base `{{baseUrl}}` según el entorno que desees certificar:
   - Local: `http://localhost:8050`
   - Cloud: `https://grupo5-pedidos-mock.onrender.com`
