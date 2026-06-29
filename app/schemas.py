from pydantic import BaseModel, Field, StrictInt, field_serializer
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class OrderItem(BaseModel):
    productId: UUID
    name: str
    quantity: int = Field(gt=0, description="La cantidad debe ser mayor a 0")
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
    shippingAddress: Optional[ShippingAddress] = None
    notes: Optional[str] = None

class OrderResponse(BaseModel):
    orderId: str
    userId: UUID
    status: str
    items: List[OrderItem]
    shipmentIds: List[str] = Field(description="Lista de cajas físicas devueltas por Logística")
    shippingAddress: Optional[ShippingAddress] = None
    subtotal: StrictInt
    shippingCost: StrictInt
    totalAmount: StrictInt
    currency: str
    notes: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    # Problema 7a: Forzar formateo estricto ISO 8601 terminando en 'Z' para la malla y el BFF
    @field_serializer('createdAt', 'updatedAt')
    def serialize_dt(self, dt: datetime, _info):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")