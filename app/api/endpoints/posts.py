from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.db import models
from app import schemas
from app.core.security import get_api_key

router = APIRouter(dependencies=[Depends(get_api_key)])

@router.get("/", response_model=List[schemas.Post])
def read_posts(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
    brand_id: Optional[int] = Query(None, description="筛选品牌ID"),
    brand_name: Optional[str] = Query(None, description="筛选品牌名称"),
    platform: Optional[str] = Query(None, description="筛选平台 (e.g., instagram)"),
    start_date: Optional[date] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    since_id: Optional[int] = Query(None, description="增量同步：获取 ID 大于此值的帖子")
):
    """
    获取帖子列表，支持多维度筛选。
    """
    query = db.query(models.Post).join(models.Brand)
    
    # 1. 品牌筛选
    if brand_id:
        query = query.filter(models.Post.brand_id == brand_id)
    if brand_name:
        query = query.filter(models.Brand.name == brand_name)
        
    # 2. 平台筛选
    if platform:
        query = query.filter(models.Post.platform == platform)
        
    # 3. 日期筛选 (posted_at)
    if start_date:
        query = query.filter(models.Post.posted_at >= start_date)
    if end_date:
        # 包含结束日期当天，通常需要加一天或处理时间
        # 这里简单处理为 >= start AND < end + 1day 或者直接比较 date
        # 由于 posted_at 是 DateTime，直接比较 date 可能会漏掉 end_date 当天的时间
        # 建议转换成 datetime 边界
        import datetime
        end_dt = datetime.datetime.combine(end_date, datetime.time.max)
        query = query.filter(models.Post.posted_at <= end_dt)

    # 4. 增量同步 (since_id)
    if since_id:
        query = query.filter(models.Post.id > since_id)

    # 排序：按 ID 倒序（保证增量同步的顺序性和最新性）
    query = query.order_by(models.Post.id.desc())
    
    posts = query.offset(skip).limit(limit).all()
    
    # 填充 brand_name (Schema 需要)
    for post in posts:
        post.brand_name = post.brand.name
        
    return posts