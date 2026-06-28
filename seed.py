import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Forzar la carga antes de importar el motor
from app.database import SessionLocal, engine, Base
from app.models import Order, OrderItem

def generate_random_order_id(date_obj) -> str:
    date_str = date_obj.strftime("%Y%m%d")
    return f"ORD-{date_str}-{random.randint(100, 999)}"

def populate_database():
    print("⏳ Conectando e inicializando tablas en Supabase...")
    # Crea las tablas físicamente en Supabase si aún no existen
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # Listas de datos para simular un ambiente real
    statuses = ["CREATED", "PAYMENT_PENDING", "PAID", "READY_TO_SHIP", "SHIPPED", "DELIVERED", "CANCELLED", "FAILED"]
    product_names = [
        "Notebook Lenovo IdeaPad", "Mouse Gamer Logitech", "Teclado Mecánico Redragon", 
        "Monitor Asus 24 IPS", "Audífonos HyperX Cloud", "Memoria RAM Kingston 16GB",
        "Disco SSD Crucial 1TB", "Tarjeta de Video RTX 4060"
    ]
    cities = ["Santiago", "La Pintana", "Providencia", "Maipú", "Concepción", "Valparaíso", "Antofagasta"]
    
    print("🚀 Generando 50 pedidos aleatorios con blindaje Int8...")
    
    try:
        for i in range(50):
            # 1. Generar tiempos consistentes en el pasado (últimos 30 días) con zona horaria UTC
            days_ago = random.randint(0, 30)
            hours_ago = random.randint(1, 23)
            base_date = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
            
            order_id = generate_random_order_id(base_date)
            user_id = str(uuid.uuid4())
            status = random.choice(statuses)
            
            # 2. Generar líneas de productos (Items)
            num_items = random.randint(1, 4)
            items_to_insert = []
            calculated_subtotal = 0
            
            for _ in range(num_items):
                p_name = random.choice(product_names)
                qty = random.randint(1, 3)
                # Precios realistas en CLP (Enteros estrictos)
                u_price = random.randint(50, 800) * 1000 
                sub_total = qty * u_price
                calculated_subtotal += sub_total
                
                item_obj = OrderItem(
                    product_id=str(uuid.uuid4()),
                    name=p_name,
                    quantity=qty,
                    unit_price=u_price,
                    subtotal=sub_total
                )
                items_to_insert.append(item_obj)
            
            shipping_cost = 3500
            total_amount = calculated_subtotal + shipping_cost
            
            # 3. Estructurar dirección como JSON (Mitigación G4 nullable)
            address_json = {
                "street": f"Avenida Siempre Viva {random.randint(100, 9990)}",
                "city": random.choice(cities),
                "region": "Metropolitana",
                "country": "Chile",
                "postalCode": f"{random.randint(1000000, 9999999)}"
            } if random.random() > 0.2 else None # 20% de probabilidad de ser nulo para simular fallos de G4
            
            # 4. Crear instancia de Orden
            db_order = Order(
                order_id=order_id,
                user_id=user_id,
                status=status,
                shipment_ids=[f"SHP-{random.randint(1000, 9999)}", f"SHP-{random.randint(5000, 9999)}"] if status in ["READY_TO_SHIP", "SHIPPED", "DELIVERED"] else [],
                shipping_address=address_json,
                subtotal=calculated_subtotal,
                shipping_cost=shipping_cost,
                total_amount=total_amount,
                currency="CLP",
                notes=f"Pedido masivo simulado para analítica Batch G7. Seed #{i+1}",
                created_at=base_date,
                updated_at=base_date + timedelta(minutes=random.randint(5, 120))
            )
            
            # Asociar ítems mediante la relación relacional
            db_order.items = items_to_insert
            db.add(db_order)
            
        db.commit()
        print("✅ Base de datos poblada con éxito. 50 órdenes transaccionadas en Supabase.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error crítico durante el sembrado de datos: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    populate_database()