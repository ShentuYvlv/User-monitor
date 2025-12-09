from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

# 定义 header key 名称，例如 "X-API-Token" 或 "Authorization"
# 这里使用 "X-API-Token"
api_key_header = APIKeyHeader(name="X-API-Token", auto_error=True)

async def get_api_key(api_key: str = Depends(api_key_header)):
    """
    验证静态 API Token
    """
    if api_key != settings.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    return api_key
