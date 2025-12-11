from fastapi import APIRouter

from app.api.endpoints import posts, brands, twitter

api_router = APIRouter()

api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(brands.router, prefix="/brands", tags=["brands"])
api_router.include_router(twitter.router, prefix="/twitter", tags=["twitter"])