from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictInt, field_serializer


class OrderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    productId: UUID = Field(validation_alias=AliasChoices("productId", "product_id"))
    name: str
    quantity: int = Field(gt=0, description="La cantidad debe ser mayor a 0")
    unitPrice: StrictInt = Field(
        validation_alias=AliasChoices("unitPrice", "unit_price"),
        description="Precio unitario en CLP, sin decimales",
    )
    subtotal: StrictInt = Field(description="Subtotal en CLP, sin decimales (quantity x unitPrice)")


class ShippingAddress(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    street: str
    city: str
    region: str
    country: str
    postalCode: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("postalCode", "postal_code"),
    )


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: UUID
    items: List[OrderItem] = Field(min_length=1, description="El pedido debe tener al menos 1 item")
    shippingAddress: Optional[ShippingAddress] = None
    notes: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    orderId: str = Field(validation_alias=AliasChoices("orderId", "order_id"))
    userId: UUID = Field(validation_alias=AliasChoices("userId", "user_id"))
    status: str
    items: List[OrderItem]
    shipmentIds: List[str] = Field(
        validation_alias=AliasChoices("shipmentIds", "shipment_ids"),
        description="Lista de cajas fisicas devueltas por Logistica",
    )
    shippingAddress: Optional[ShippingAddress] = Field(
        default=None,
        validation_alias=AliasChoices("shippingAddress", "shipping_address"),
    )
    subtotal: StrictInt
    shippingCost: StrictInt = Field(validation_alias=AliasChoices("shippingCost", "shipping_cost"))
    totalAmount: StrictInt = Field(validation_alias=AliasChoices("totalAmount", "total_amount"))
    currency: str
    notes: Optional[str] = None
    createdAt: datetime = Field(validation_alias=AliasChoices("createdAt", "created_at"))
    updatedAt: datetime = Field(validation_alias=AliasChoices("updatedAt", "updated_at"))

    @field_serializer("createdAt", "updatedAt")
    def serialize_dt(self, dt: datetime, _info):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class OrderStatusResponse(BaseModel):
    orderId: str
    status: str


class Pagination(BaseModel):
    page: int
    pageSize: int
    total: int
    totalPages: int
    hasNext: bool
    hasPrev: bool


class OrdersByUserResponse(BaseModel):
    data: List[OrderResponse]
    pagination: Pagination
