from pydantic import BaseModel, Field, StrictInt, field_serializer, ConfigDict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

# Nota sobre alias: usamos `validation_alias` (no `alias`) a propósito.
# `validation_alias` solo afecta cómo se LEE el dato (ej. desde un objeto ORM
# con atributos snake_case). La SALIDA (serialización a JSON) sigue usando el
# nombre del campo (camelCase), que es lo que exige el contrato openapi.yaml.
# Si usáramos `alias` a secas, FastAPI también serializaría con el alias
# (snake_case) por defecto, rompiendo el contrato.

class OrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    productId: UUID = Field(validation_alias="product_id")
    name: str
    quantity: int = Field(gt=0, description="La cantidad debe ser mayor a 0")
    unitPrice: StrictInt = Field(validation_alias="unit_price", description="Precio unitario en CLP, sin decimales")
    subtotal: StrictInt = Field(description="Subtotal en CLP, sin decimales (quantity x unitPrice)")

class ShippingAddress(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    street: str
    city: str
    region: str
    country: str
    postalCode: Optional[str] = Field(default=None, validation_alias="postal_code")

class CreateOrderRequest(BaseModel):
    userId: UUID
    items: List[OrderItem] = Field(min_length=1, description="El pedido debe tener al menos 1 ítem")
    shippingAddress: Optional[ShippingAddress] = None
    notes: Optional[str] = None

class OrderResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    orderId: str = Field(validation_alias="order_id")
    userId: UUID = Field(validation_alias="user_id")
    status: str
    items: List[OrderItem]
    shipmentIds: List[str] = Field(validation_alias="shipment_ids", description="Lista de cajas físicas devueltas por Logística")
    shippingAddress: Optional[ShippingAddress] = Field(default=None, validation_alias="shipping_address")
    subtotal: StrictInt
    shippingCost: StrictInt = Field(validation_alias="shipping_cost")
    totalAmount: StrictInt = Field(validation_alias="total_amount")
    currency: str
    notes: Optional[str] = None
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")

    # Problema 7a: Forzar formateo estricto ISO 8601 terminando en 'Z' para la malla y el BFF
    @field_serializer('createdAt', 'updatedAt')
    def serialize_dt(self, dt: datetime, _info):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
