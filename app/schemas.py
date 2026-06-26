from pydantic import BaseModel, Field, StrictInt
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class OrderItem(BaseModel):
    productId: UUID
    name: str
    quantity: int = Field(gt=0, description="La cantidad debe ser mayor a 0")
    # StrictInt rechaza floats (ej. 1599.98 fallará automáticamente con error 422)
    unitPrice: StrictInt = Field(description="Precio unitario en CLP, sin decimales")
    subtotal: StrictInt = Field(description="Subtotal en CLP, sin decimales (quantity x unitPrice)")

class ShippingAddress(BaseModel):
    street: str
    city: str
    region: str
    country: str
    postalCode: Optional[str] = None

class CreateOrderRequest(BaseModel):
    userId: UUID
    items: List[OrderItem] = Field(min_length=1, description="El pedido debe tener al menos 1 ítem")
    # shippingAddress es opcional (nullable) para mitigar que G4 no la envía en su checkout
    shippingAddress: Optional[ShippingAddress] = None
    notes: Optional[str] = None

class OrderResponse(BaseModel):
    orderId: str
    userId: UUID
    status: str
    items: List[OrderItem]
    # Soporte Multi-Origen v1.2 alineado con el Grupo 6 (Logística)
    shipmentIds: List[str] = Field(description="Lista de cajas físicas devueltas por Logística")
    shippingAddress: Optional[ShippingAddress] = None
    subtotal: StrictInt
    shippingCost: StrictInt
    totalAmount: StrictInt
    currency: str = "CLP"
    notes: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime