import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Intentar cargar la URL de la base de datos desde las variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Si estás desarrollando localmente en Windows sin variables de entorno aún,
# puedes usar esta cadena de fallback (reemplázala con tus credenciales reales de Supabase si es necesario)
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:tu_password_aqui@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"

# Configuración del motor con límites estrictos de pool para la capa gratuita (Free Tier)
engine = create_engine(
    DATABASE_URL,
    pool_size=5,          # Máximo de conexiones persistentes abiertas
    max_overflow=10,      # Conexiones adicionales permitidas en picos de carga
    pool_pre_ping=True    # Verifica si la conexión está viva antes de usarla (evita caídas en Render)
)

# Generador de sesiones de base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base para la creación de los modelos relacionales
Base = declarative_base()

# Dependencia crucial para FastAPI: Garantiza que CADA conexión se cierre explícitamente
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() # <--- Cortafuegos contra el agotamiento de conexiones en Supabase