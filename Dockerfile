# 1. Utilizar una imagen oficial de Python basada en una distribución "slim" muy liviana
FROM python:3.12-slim

# 2. Definir el directorio de trabajo dentro del contenedor donde vivirá el código
WORKDIR /app

# 3. Evitar que Python escriba archivos de caché .pyc en el disco del contenedor
ENV PYTHONDONTWRITEBYTECODE=1

# 4. Forzar a que los logs de FastAPI se transmitan directamente a la consola en tiempo real.
# Esto es crítico para que puedas ver los errores e impresiones en vivo en el panel de Render.
ENV PYTHONUNBUFFERED=1

# 5. Configurar la variable de entorno del sistema para que reconozca la raíz de tus módulos
ENV PYTHONPATH=/app

# 6. Copiar primero de forma aislada el archivo de requerimientos.
# Esto permite aprovechar la caché de capas de Docker; si tu código cambia pero no tus librerías,
# Render no perderá tiempo reinstalando dependencias en cada despliegue.
COPY requirements.txt .

# 7. Instalar todas las dependencias del proyecto eliminando la caché temporal de pip
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# 8. Copiar absolutamente todo el resto del código del proyecto hacia el contenedor
COPY . .

# 9. Informar el puerto en el que escuchará el contenedor
EXPOSE 8080

# 10. Comando de ejecución definitivo para iniciar tu servicio en producción.
# Vincula Uvicorn a la IP 0.0.0.0 y al puerto 8080 (el estándar que Render escanea para abrir la URL pública).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]