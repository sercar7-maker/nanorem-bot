from fastapi import FastAPI

from web.order_handler import router as order_router

app = FastAPI()

app.include_router(order_router)


@app.get("/")
def root():
    return {"status": "ok"}