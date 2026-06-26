from fastapi import FastAPI

app = FastAPI(title="Grupo 5 - Pedidos Mock")

@app.get("/")
def read_root():
    return {"message": "Servicio de Pedidos operativo"}
