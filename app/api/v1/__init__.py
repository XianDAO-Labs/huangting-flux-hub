from fastapi import APIRouter
from .agents import router as agents_router
from .signals import router as signals_router
from .network import router as network_router

api_router = APIRouter()
api_router.include_router(agents_router, tags=["Agents"])
api_router.include_router(signals_router, tags=["Signals"])
api_router.include_router(network_router, tags=["Network"])
