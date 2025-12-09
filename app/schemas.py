from typing import List, Optional, Union
from datetime import datetime
import json
from pydantic import BaseModel, ConfigDict, field_validator
from app.db.models import PlatformType
from app.core.config import settings

# --- Shared Properties ---

class BrandBase(BaseModel):
    name: str
    instagram_username: Optional[str] = None
    telegram_channel_id: Optional[str] = None
    twitter_username: Optional[str] = None
    is_active: bool = True

class PostBase(BaseModel):
    platform: PlatformType
    original_id: str
    content_text: Optional[str] = None
    media_urls: Optional[Union[str, List[str]]] = None # 修改类型提示，允许接收字符串或列表
    original_url: Optional[str] = None
    posted_at: Optional[datetime] = None
    like_count: int = 0
    comment_count: int = 0

# --- Brand Schemas ---

class BrandCreate(BrandBase):
    pass

class BrandUpdate(BrandBase):
    pass

class Brand(BrandBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Post Schemas ---

class PostCreate(PostBase):
    brand_id: int

class Post(PostBase):
    id: int
    brand_id: int
    created_at: datetime
    
    # We will return brand name for convenience
    brand_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('media_urls', mode='before')
    def parse_and_absolutize_media_urls(cls, v):
        """
        1. Parse JSON string to list.
        2. Prepend SERVER_HOST to relative paths.
        """
        if v is None:
            return []
        
        # 如果是 JSON 字符串，先转成 list
        if isinstance(v, str):
            try:
                urls = json.loads(v)
            except json.JSONDecodeError:
                return []
        else:
            urls = v

        if not isinstance(urls, list):
            return []

        # 拼接完整 URL
        # 去除 settings.SERVER_HOST 结尾的 / 和 url 开头的 / 以避免双斜杠
        base_url = settings.SERVER_HOST.rstrip("/")
        
        full_urls = []
        for url in urls:
            if url.startswith("/"):
                full_urls.append(f"{base_url}{url}")
            else:
                full_urls.append(f"{base_url}/{url}")
        
        return full_urls