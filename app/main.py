from fastapi import FastAPI, Header, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
import random
import os
import httpx

# Importaciones internas de la arquitectura del Grupo 5
from app.database import get_db
from app.models import Order, OrderItem
from app.schemas import CreateOrderRequest, OrderResponse
from app.events_logger import log_event_to_storage  # <--- Integración analítica de la Fase 3

app = FastAPI(
    title="Grupo 5 - Pedidos (Core Transaccional & Analítico Cloud)",
    version="1.2.0",
    description="Microservicio de producción definitivo conectado a Supabase y optimizado para analítica Batch"
)

# Enrutamiento de URLs de la malla del marketplace (Variables de entorno en Render)
G2_AUTH_URL = os.getenv("G2_AUTH_URL", "https://api-grupo2-auth.onrender.com")
G3_CATALOG_URL = os.getenv("G3_CATALOG_URL", "https://api-grupo3-catalogo.onrender.com")
G6_DELIVERY_URL = os.getenv("G6_DELIVERY_URL", "https://api-grupo6-despacho.onrender.com")

def generate_order_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ORD-{today}-{random.randint(100, 999)}"

# Cortafuegos de Seguridad Perimetral (Fase 2)
async def verify_security_and_role(authorization: Optional[str] = Header(None), x_correlation_id: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token Bearer ausente o mal formateado.")
    
    headers = {
        "Authorization": authorization,
        "X-Correlation-Id": x_correlation_id or str(uuid4()),
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{G2_AUTH_URL}/auth/validate", headers=headers, timeout=5.0)
            if response.status_code != 200:
                raise HTTPException(status_code=401, detail="Token inválido o expirado según el Grupo 2.")
            
            auth_data = response.json()
            return {
                "userId": auth_data.get("userId"),
                "role": auth_data.get("role")  # 'customer' o 'admin'
            }
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Servicio de Autenticación (G2) no disponible de forma síncrona.")

# Endpoint raíz de cortesía de red (Health Check para Render)
@app.get("/")
def read_root():
    return {"message": "Servicio de Pedidos operativo y conectado a Supabase - v1.2.0"}


# 1. CREAR PEDIDO (POST /orders) — Integración de persistencia, idempotencia y analítica
@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest, 
    idempotency_key: str = Header(alias="Idempotency-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db)
):
    correlation_id = x_correlation_id or str(uuid4())

    # Control de roles
    if auth_user["role"] != "admin" and str(request.userId) != auth_user["userId"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para transaccionar a nombre de otro cliente.")

    # Control de idempotencia física contra la base de datos
    existing_order = db.query(Order).filter(Order.notes.contains(f"IK:{idempotency_key}")).first()
    if existing_order:
        return existing_order

    # Lógica matemática transaccional (StrictInt / Int8)
    calculated_subtotal = sum(item.subtotal for item in request.items)
    shipping_cost = 3500 
    total_amount = calculated_subtotal + shipping_cost
    new_order_id = generate_order_id()

    db_order = Order(
        order_id=new_order_id,
        user_id=str(request.userId),
        status="CREATED",
        shipment_ids=[],
        shipping_address=request.shipping_address.model_dump() if request.shipping_address else None,
        subtotal=calculated_subtotal,
        shipping_cost=shipping_cost,
        total_amount=total_amount,
        currency="CLP",
        notes=f"{request.notes or ''} [IK:{idempotency_key}]"
    )

    db.add(db_order)
    db.flush()

    # Inserción de líneas de producto (Snapshots comerciales)
    items_payload_for_log = []
    for item in request.items:
        db_item = OrderItem(
            order_id=new_order_id,
            product_id=str(item.productId),
            name=item.name,
            quantity=item.quantity,
            unit_price=item.unitPrice,
            subtotal=item.subtotal
        )
        db.add(db_item)
        items_payload_for_log.append({
            "productId": str(item.productId),
            "name": item.name,
            "quantity": item.quantity,
            "unitPrice": item.unitPrice,
            "subtotal": item.subtotal
        })

    try:
        db.commit()
        db.refresh(db_order)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Fallo relacional en Supabase: {str(e)}")

    # --- DISPARADOR ANALÍTICO ASÍNCRONO (Fase 3) ---
    event_payload = {
        "orderId": db_order.order_id,
        "userId": db_order.user_id,
        "status": db_order.status,
        "totalAmount": db_order.total_amount,
        "currency": db_order.currency,
        "items": items_payload_for_log
    }
    await log_event_to_storage("ORDER_CREATED", correlation_id, event_payload)

    return db_order


# 2. OBTENER UN PEDIDO POR ID (GET /orders/{orderId})
@app.get("/orders/{orderId}", response_model=OrderResponse)
async def get_order_by_id(
    orderId: str, 
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db)
):
    db_order = db.query(Order).filter(Order.order_id == orderId).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no registrado en los sistemas.")
        
    if auth_user["role"] != "admin" and db_order.user_id != auth_user["userId"]:
        raise HTTPException(status_code=403, detail="Acceso denegado a este registro comercial.")
        
    return db_order


# 3. ACTUALIZAR ESTADO (PATCH) — Orquestación síncrona de la malla y logs cronológicos
@app.patch("/orders/{orderId}/status", response_model=OrderResponse)
async def update_order_status(
    orderId: str, 
    request_data: dict, 
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db)
):
    new_status = request_data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="El campo 'status' es obligatorio.")

    db_order = db.query(Order).filter(Order.order_id == orderId).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")

    correlation_id = x_correlation_id or str(uuid4())

    # Flujo síncrono condicional: Si pasa a PAID, enriquece datos con G3 y despacha a G6
    if new_status == "PAID":
        packages_payload = []
        async with httpx.AsyncClient() as client:
            # Enriquecimiento volumétrico con Catálogo (Grupo 3)
            for item in db_order.items:
                try:
                    g3_response = await client.get(
                        f"{G3_CATALOG_URL}/products/{item.product_id}", 
                        headers={"X-Correlation-Id": correlation_id},
                        timeout=4.0
                    )
                    if g3_response.status_code == 200:
                        catalog_data = g3_response.json()
                        packages_payload.append({
                            "productId": item.product_id,
                            "originCd": catalog_data.get("originCd", "CENTRO"),
                            "weight": catalog_data.get("weightKg", 1.0),
                            "dimensions": catalog_data.get("dimensionsCm", "20x20x20")
                        })
                    else:
                        packages_payload.append({"productId": item.product_id, "originCd": "CENTRO", "weight": 1.0, "dimensions": "20x20x20"})
                except Exception:
                    packages_payload.append({"productId": item.product_id, "originCd": "CENTRO", "weight": 1.0, "dimensions": "20x20x20"})

            # Generación física de guías en Despacho (Grupo 6)
            g6_headers = {
                "X-Correlation-Id": correlation_id,
                "X-Request-Id": str(uuid4()),
                "X-Consumer": "G5-Pedidos",
                "Content-Type": "application/json"
            }
            try:
                g6_response = await client.post(
                    f"{G6_DELIVERY_URL}/api/v1/shipments", 
                    json={"packages": packages_payload}, 
                    headers=g6_headers,
                    timeout=5.0
                )
                if g6_response.status_code in [200, 201]:
                    db_order.shipment_ids = g6_response.json()
                    db_order.status = "READY_TO_SHIP"
                else:
                    db_order.status = "PAID"
            except Exception:
                db_order.status = "PAID"

    else:
        db_order.status = new_status

    db_order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_order)

    # --- DISPARADORES ANALÍTICOS DE TRANSICIÓN DE ESTADOS ---
    status_changed_payload = {
        "orderId": db_order.order_id,
        "newStatus": db_order.status,
        "shipmentIds": db_order.shipment_ids
    }
    
    # Emitir cambio de estado general
    await log_event_to_storage("ORDER_STATUS_CHANGED", correlation_id, status_changed_payload)
    
    # Emitir cancelación analítica separada si el estado derivó en fallas críticas
    if db_order.status in ["CANCELLED", "FAILED"]:
        await log_event_to_storage("ORDER_CANCELLED", correlation_id, {"orderId": db_order.order_id, "reason": "TRANSITION_TO_FAIL_STATE"})

    return db_order


# 4. LISTAR PEDIDOS PAGINADOS (GET /users/{userId}/orders)
@app.get("/users/{userId}/orders")
async def get_orders_by_user(
    userId: UUID, 
    page: int = 1, 
    pageSize: int = 10, 
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db)
):
    if auth_user["role"] != "admin" and str(userId) != auth_user["userId"]:
        raise HTTPException(status_code=403, detail="Acceso denegado al historial de este cliente.")
        
    skip = (page - 1) * pageSize
    query = db.query(Order).filter(Order.user_id == str(userId))
    total = query.count()
    orders = query.offset(skip).limit(pageSize).all()
    total_pages = (total + pageSize - 1) // pageSize if total > 0 else 0

    return {
        "data": orders,
        "pagination": {
            "page": page, "pageSize": pageSize, "total": total, "totalPages": total_pages,
            "hasNext": page < total_pages, "hasPrev": page > 1
        }
    }