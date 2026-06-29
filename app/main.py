from datetime import datetime, timezone
import hashlib
import json
import os
import random
from typing import Optional
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.events_logger import log_event_to_storage
from app.models import Order, OrderItem
from app.schemas import CreateOrderRequest, OrderResponse, OrdersByUserResponse, OrderStatusResponse


app = FastAPI(
    title="Grupo 5 - Pedidos (Core Transaccional & Analitico Cloud)",
    version="1.2.0",
    description="Microservicio de pedidos conectado a PostgreSQL/Supabase.",
)

G2_AUTH_URL = os.getenv("G2_AUTH_URL", "https://api-grupo2-auth.onrender.com")
G3_CATALOG_URL = os.getenv("G3_CATALOG_URL", "https://api-grupo3-catalogo.onrender.com")
G6_DELIVERY_URL = os.getenv("G6_DELIVERY_URL", "https://api-grupo6-despacho.onrender.com")
ALLOW_TEST_AUTH = os.getenv("ALLOW_TEST_AUTH", "false").lower() == "true"

VALID_TRANSITIONS = {
    "CREATED": {"PAYMENT_PENDING", "CANCELLED"},
    "PAYMENT_PENDING": {"PAID", "FAILED", "CANCELLED"},
    "PAID": {"READY_TO_SHIP", "CANCELLED"},
    "READY_TO_SHIP": {"SHIPPED", "CANCELLED", "FAILED"},
    "SHIPPED": {"DELIVERED", "CANCELLED", "FAILED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
    "FAILED": set(),
}


def generate_order_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ORD-{today}-{random.randint(100000, 999999)}"


def request_body_hash(request: CreateOrderRequest) -> str:
    body = request.model_dump(mode="json", by_alias=True, exclude_none=False)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def verify_security_and_role(
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token Bearer ausente o mal formateado.")

    token = authorization.removeprefix("Bearer ").strip()
    if ALLOW_TEST_AUTH and token.startswith("test-token"):
        return {"userId": "test-user", "role": "admin"}

    headers = {
        "Authorization": authorization,
        "X-Correlation-Id": x_correlation_id or str(uuid4()),
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{G2_AUTH_URL}/auth/validate", headers=headers, timeout=5.0)
            if response.status_code != 200:
                raise HTTPException(status_code=401, detail="Token invalido o expirado segun el Grupo 2.")

            auth_data = response.json()
            return {
                "userId": auth_data.get("userId"),
                "role": auth_data.get("role", "customer"),
            }
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Servicio de Autenticacion (G2) no disponible.")


def assert_can_access_order(auth_user: dict, db_order: Order):
    if auth_user["role"] != "admin" and db_order.user_id != auth_user["userId"]:
        raise HTTPException(status_code=403, detail="Acceso denegado a este registro comercial.")


def validate_transition(previous_status: str, new_status: str):
    if new_status not in VALID_TRANSITIONS:
        raise HTTPException(status_code=400, detail="Estado de pedido no reconocido.")
    if new_status not in VALID_TRANSITIONS.get(previous_status, set()):
        raise HTTPException(status_code=409, detail=f"No se puede pasar de {previous_status} a {new_status}.")


@app.get("/")
def read_root():
    return {"message": "Servicio de Pedidos operativo - v1.2.0"}


@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db),
):
    correlation_id = x_correlation_id or str(uuid4())
    body_hash = request_body_hash(request)

    if auth_user["role"] != "admin" and str(request.userId) != auth_user["userId"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para crear pedidos de otro cliente.")

    existing_order = db.query(Order).filter(Order.notes.contains(f"IK:{idempotency_key}")).first()
    if existing_order:
        if f"BH:{body_hash}" not in (existing_order.notes or ""):
            raise HTTPException(status_code=409, detail="Esta Idempotency-Key ya fue usada con datos distintos.")
        return existing_order

    for item in request.items:
        if item.subtotal != item.quantity * item.unitPrice:
            raise HTTPException(status_code=400, detail="El subtotal de cada item debe ser quantity x unitPrice.")

    calculated_subtotal = sum(item.subtotal for item in request.items)
    shipping_cost = 3500
    total_amount = calculated_subtotal + shipping_cost
    new_order_id = generate_order_id()

    db_order = Order(
        order_id=new_order_id,
        user_id=str(request.userId),
        status="PAYMENT_PENDING",
        shipment_ids=[],
        shipping_address=request.shippingAddress.model_dump(by_alias=True) if request.shippingAddress else None,
        subtotal=calculated_subtotal,
        shipping_cost=shipping_cost,
        total_amount=total_amount,
        currency="CLP",
        notes=f"{request.notes or ''} [IK:{idempotency_key}] [BH:{body_hash}]",
    )

    db.add(db_order)
    db.flush()

    items_payload_for_log = []
    for item in request.items:
        db_item = OrderItem(
            order_id=new_order_id,
            product_id=str(item.productId),
            name=item.name,
            quantity=item.quantity,
            unit_price=item.unitPrice,
            subtotal=item.subtotal,
        )
        db.add(db_item)
        items_payload_for_log.append(
            {
                "productId": str(item.productId),
                "name": item.name,
                "quantity": item.quantity,
                "unitPrice": item.unitPrice,
                "subtotal": item.subtotal,
            }
        )

    try:
        db.commit()
        db.refresh(db_order)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Fallo relacional en base de datos: {exc}")

    await log_event_to_storage(
        "ORDER_CREATED",
        correlation_id,
        {
            "orderId": db_order.order_id,
            "userId": db_order.user_id,
            "status": db_order.status,
            "totalAmount": db_order.total_amount,
            "currency": db_order.currency,
            "items": items_payload_for_log,
        },
    )
    await log_event_to_storage(
        "ORDER_STATUS_CHANGED",
        correlation_id,
        {"orderId": db_order.order_id, "previousStatus": "CREATED", "status": db_order.status},
    )

    return db_order


@app.get("/orders/{orderId}", response_model=OrderResponse)
async def get_order_by_id(
    orderId: str,
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db),
):
    db_order = db.query(Order).filter(Order.order_id == orderId).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no registrado en los sistemas.")

    assert_can_access_order(auth_user, db_order)
    return db_order


@app.get("/orders/{orderId}/status", response_model=OrderStatusResponse)
async def get_order_status(
    orderId: str,
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db),
):
    db_order = db.query(Order).filter(Order.order_id == orderId).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")

    assert_can_access_order(auth_user, db_order)
    return {"orderId": db_order.order_id, "status": db_order.status}


@app.patch("/orders/{orderId}/status", response_model=OrderResponse)
async def update_order_status(
    orderId: str,
    request_data: dict,
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db),
):
    new_status = request_data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="El campo 'status' es obligatorio.")

    db_order = db.query(Order).filter(Order.order_id == orderId).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")

    assert_can_access_order(auth_user, db_order)
    previous_status = db_order.status
    validate_transition(previous_status, new_status)

    correlation_id = x_correlation_id or str(uuid4())

    if new_status == "PAID":
        db_order.status = await create_shipments_for_paid_order(db_order, correlation_id)
    else:
        db_order.status = new_status

    db_order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_order)

    await log_event_to_storage(
        "ORDER_STATUS_CHANGED",
        correlation_id,
        {
            "orderId": db_order.order_id,
            "previousStatus": previous_status,
            "status": db_order.status,
            "shipmentIds": db_order.shipment_ids,
        },
    )

    if db_order.status in ["CANCELLED", "FAILED"]:
        await log_event_to_storage(
            "ORDER_CANCELLED",
            correlation_id,
            {"orderId": db_order.order_id, "reason": request_data.get("reason", "TRANSITION_TO_FAIL_STATE")},
        )

    return db_order


async def create_shipments_for_paid_order(db_order: Order, correlation_id: str) -> str:
    packages_payload = []
    async with httpx.AsyncClient() as client:
        for item in db_order.items:
            try:
                g3_response = await client.get(
                    f"{G3_CATALOG_URL}/products/{item.product_id}",
                    headers={"X-Correlation-Id": correlation_id},
                    timeout=4.0,
                )
                catalog_data = g3_response.json() if g3_response.status_code == 200 else {}
            except Exception:
                catalog_data = {}

            packages_payload.append(
                {
                    "productId": item.product_id,
                    "originCd": catalog_data.get("originCd", "CENTRO"),
                    "weight": catalog_data.get("weightKg", 1.0),
                    "dimensions": catalog_data.get("dimensionsCm", "20x20x20"),
                }
            )

        g6_headers = {
            "X-Correlation-Id": correlation_id,
            "X-Request-Id": str(uuid4()),
            "X-Consumer": "G5-Pedidos",
            "Content-Type": "application/json",
        }
        try:
            g6_response = await client.post(
                f"{G6_DELIVERY_URL}/api/v1/shipments",
                json={"packages": packages_payload},
                headers=g6_headers,
                timeout=5.0,
            )
            if g6_response.status_code in [200, 201]:
                shipment_ids = g6_response.json()
                db_order.shipment_ids = shipment_ids if isinstance(shipment_ids, list) else []
                return "READY_TO_SHIP"
        except Exception:
            pass

    return "PAID"


@app.get("/users/{userId}/orders", response_model=OrdersByUserResponse)
async def get_orders_by_user(
    userId: UUID,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
    auth_user: dict = Depends(verify_security_and_role),
    db: Session = Depends(get_db),
):
    if auth_user["role"] != "admin" and str(userId) != auth_user["userId"]:
        raise HTTPException(status_code=403, detail="Acceso denegado al historial de este cliente.")

    query = db.query(Order).filter(Order.user_id == str(userId))
    if status_filter:
        if status_filter not in VALID_TRANSITIONS:
            raise HTTPException(status_code=400, detail="Estado de pedido no reconocido.")
        query = query.filter(Order.status == status_filter)

    skip = (page - 1) * pageSize
    total = query.count()
    orders = query.offset(skip).limit(pageSize).all()
    total_pages = (total + pageSize - 1) // pageSize if total > 0 else 0

    return {
        "data": orders,
        "pagination": {
            "page": page,
            "pageSize": pageSize,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        },
    }
