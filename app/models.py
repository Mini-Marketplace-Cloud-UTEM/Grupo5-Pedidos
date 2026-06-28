from sqlalchemy import Column, String, ForeignKey, Integer, BigInteger, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime, timezone

class Order(Base):
    __tablename__ = "orders"

    # PK de negocio estructurada como ORD-YYYYMMDD-NNN
    order_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    status = Column(String, default="CREATED", nullable=False)
    
    # Soporte Multi-Origen G6 v1.2: Almacena un arreglo nativo de strings en Postgres
    shipment_ids = Column(ARRAY(String), default=[], nullable=False)
    
    # Mitigación G4: Se almacena la dirección como un objeto JSON estructurado (nullable)
    shipping_address = Column(JSON, nullable=True)
    
    # FASE 1: Blindaje monetario usando BigInteger (Int8 en PostgreSQL)
    subtotal = Column(BigInteger, nullable=False)
    shipping_cost = Column(BigInteger, default=3500, nullable=False)
    total_amount = Column(BigInteger, nullable=False)
    
    currency = Column(String, default="CLP", nullable=False)
    notes = Column(Text, nullable=True)
    
    # Estándar estricto ISO 8601 con zona horaria UTC explícita
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relación uno a muchos con los ítems del pedido (Cascada elimina ítems si se borra la orden)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    product_id = Column(String, nullable=False)
    name = Column(String, nullable=False) # Snapshot del nombre del producto
    quantity = Column(Integer, nullable=False)
    
    # FASE 1: Snapshots comerciales protegidos con BigInteger (Int8)
    unit_price = Column(BigInteger, nullable=False)
    subtotal = Column(BigInteger, nullable=False)

    # Relación inversa hacia la orden principal
    order = relationship("Order", back_populates="items")