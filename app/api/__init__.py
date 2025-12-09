from fastapi import APIRouter

from app.api.endpoints import posts, brands

api_router = APIRouter()

api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(brands.router, prefix="/brands", tags=["brands"])