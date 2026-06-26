from fastapi import FastAPI, Header, HTTPException
from app.schemas import CreateOrderRequest, OrderResponse
from datetime import datetime, timezone

app = FastAPI(
    title="Grupo 5 - Pedidos Mock",
    version="1.2.0",
    description="Mock oficial para desbloquear a G4 (Checkout) y G1 (BFF) - Sincronizado Multi-Origen G6"
)

# Dejamos el GET raíz limpio por cortesía de red
@app.get("/")
def read_root():
    return {"message": "Servicio de Pedidos operativo - v1.2.0"}

@app.post("/orders", response_model=OrderResponse, status_code=201)
def create_order(
    request: CreateOrderRequest, 
    idempotency_key: str = Header(alias="Idempotency-Key")
):
    # Validamos que no venga vacío por si acaso
    if not request.items:
        raise HTTPException(status_code=400, detail="El pedido no puede tener ítems vacíos")
        
    # Calculamos el subtotal en enteros CLP basados en el validador estricto
    calculated_subtotal = sum(item.subtotal for item in request.items)
    shipping_cost = 3500 
    
    # Retornamos el objeto Order estructurado según la Phase E2
    return OrderResponse(
        orderId="ORD-20260626-001",
        userId=request.userId,
        status="CREATED",
        items=request.items,
        shipmentIds=["SHP-mock-1", "SHP-mock-2"], # Simulación Multi-Origen v1.2 del Grupo 6
        shippingAddress=request.shippingAddress,
        subtotal=calculated_subtotal,
        shippingCost=shipping_cost,
        totalAmount=calculated_subtotal + shipping_cost,
        currency="CLP",
        notes=request.notes,
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc)
    )