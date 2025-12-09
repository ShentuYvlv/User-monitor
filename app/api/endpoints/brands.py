from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.db import models
from app import schemas
from app.services.scheduler import task_update_all_brands, task_cleanup_old_media
from app.core.security import get_api_key

router = APIRouter(dependencies=[Depends(get_api_key)])

@router.get("/", response_model=List[schemas.Brand])
def read_brands(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    获取品牌列表
    """
    brands = db.query(models.Brand).offset(skip).limit(limit).all()
    return brands

@router.post("/", response_model=schemas.Brand)
def create_brand(
    brand_in: schemas.BrandCreate,
    db: Session = Depends(get_db)
):
    """
    创建新品牌监控
    """
    # 检查是否存在
    existing = db.query(models.Brand).filter(models.Brand.name == brand_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Brand with this name already exists")
    
    db_brand = models.Brand(**brand_in.model_dump())
    db.add(db_brand)
    db.commit()
    db.refresh(db_brand)
    return db_brand

@router.put("/{brand_id}", response_model=schemas.Brand)
def update_brand(
    brand_id: int,
    brand_in: schemas.BrandUpdate,
    db: Session = Depends(get_db)
):
    """
    更新品牌信息
    """
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    # 检查更名是否冲突
    if brand_in.name != brand.name:
        existing = db.query(models.Brand).filter(models.Brand.name == brand_in.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Brand with this new name already exists")

    update_data = brand_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(brand, field, value)

    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand

@router.delete("/{brand_id}", response_model=schemas.Brand)
def delete_brand(
    brand_id: int,
    db: Session = Depends(get_db)
):
    """
    删除品牌
    """
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    db.delete(brand)
    db.commit()
    return brand

@router.post("/trigger-update")
def trigger_update_brands(
    background_tasks: BackgroundTasks,
    brand_name: Optional[str] = Query(None, description="指定品牌名称，不传则更新所有"),
    limit: int = Query(10, description="抓取最新帖子的数量")
):
    """
    手动触发：立即开始抓取最新帖子
    支持指定品牌和数量限制
    """
    background_tasks.add_task(task_update_all_brands, brand_name, limit)
    message = f"Update triggered for {brand_name if brand_name else 'all brands'} with limit {limit}"
    return {"message": message}

@router.post("/trigger-cleanup")
def trigger_cleanup_media(background_tasks: BackgroundTasks):
    """
    手动触发：立即开始清理过期媒体文件
    """
    background_tasks.add_task(task_cleanup_old_media)
    return {"message": "Media cleanup task triggered in background"}