from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import smart_money, bots, backtests, stress_tests, settings

app = FastAPI(title="LWG Capital Command Center API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(smart_money.router)
app.include_router(bots.router)
app.include_router(backtests.router)
app.include_router(stress_tests.router)
app.include_router(settings.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "lwg-command-center"}
