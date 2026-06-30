from pydantic import BaseModel, Field, StrictInt, field_serializer, ConfigDict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class OrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    productId: UUID = Field(alias="product_id")
    name: str
    quantity: int = Field(gt=0, description="La cantidad debe ser mayor a 0")
    unitPrice: StrictInt = Field(alias="unit_price", description="Precio unitario en CLP, sin decimales")
    subtotal: StrictInt = Field(description="Subtotal en CLP, sin decimales (quantity x unitPrice)")

class ShippingAddress(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    street: str
    city: str
    region: str
    country: str
    postalCode: Optional[str] = Field(default=None, alias="postal_code")

class CreateOrderRequest(BaseModel):
    userId: UUID
    items: List[OrderItem] = Field(min_length=1, description="El pedido debe tener al menos 1 ítem")
    shippingAddress: Optional[ShippingAddress] = None
    notes: Optional[str] = None

class OrderResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    orderId: str = Field(alias="order_id")
    userId: UUID = Field(alias="user_id")
    status: str
    items: List[OrderItem]
    shipmentIds: List[str] = Field(alias="shipment_ids", description="Lista de cajas físicas devueltas por Logística")
    shippingAddress: Optional[ShippingAddress] = Field(default=None, alias="shipping_address")
    subtotal: StrictInt
    shippingCost: StrictInt = Field(alias="shipping_cost")
    totalAmount: StrictInt = Field(alias="total_amount")
    currency: str
    notes: Optional[str] = None
    createdAt: datetime = Field(alias="created_at")
    updatedAt: datetime = Field(alias="updated_at")

    # Problema 7a: Forzar formateo estricto ISO 8601 terminando en 'Z' para la malla y el BFF
    @field_serializer('createdAt', 'updatedAt')
    def serialize_dt(self, dt: datetime, _info):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
