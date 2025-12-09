from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.db import models
from app import schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.Post])
def read_posts(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
    brand_name: Optional[str] = None,
    platform: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """
    查询帖子列表
    
    - **brand_name**: 筛选品牌名称
    - **platform**: 筛选平台 (instagram)
    - **limit**: 返回数量
    - **start_date / end_date**: 筛选发布时间范围
    """
    query = db.query(models.Post)

    # Filter by Brand
    if brand_name:
        query = query.join(models.Brand).filter(models.Brand.name == brand_name)
    
    # Filter by Platform
    if platform:
        query = query.filter(models.Post.platform == platform)
        
    # Filter by Date Range
    if start_date:
        query = query.filter(models.Post.posted_at >= start_date)
    if end_date:
        query = query.filter(models.Post.posted_at <= end_date)

    # Sort: Newest first
    query = query.order_by(desc(models.Post.posted_at))
    
    # Pagination
    posts = query.offset(skip).limit(limit).all()
    
    # Enrich with brand name (since Post schema expects it optionally, 
    # but the DB model `Post` object has `brand` relationship)
    # Pydantic's from_attributes should handle mapping if we access properties.
    # However, `Post` model in schemas.py has `brand_name`. 
    # Let's verify if we need to manually inject it or if `brand.name` is accessible.
    
    results = []
    for p in posts:
        # Manually attach brand_name if Pydantic needs it flatten
        # (Alternatively, use a nested Brand schema)
        p.brand_name = p.brand.name
        results.append(p)

    return results