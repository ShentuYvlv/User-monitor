from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.db import models
from app import schemas
from app.services.scheduler import task_update_all_brands, task_cleanup_old_media

router = APIRouter()

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
def trigger_update_brands(background_tasks: BackgroundTasks):
    """
    手动触发：立即开始抓取所有品牌最新帖子
    """
    background_tasks.add_task(task_update_all_brands)
    return {"message": "Brand update task triggered in background"}

@router.post("/trigger-cleanup")
def trigger_cleanup_media(background_tasks: BackgroundTasks):
    """
    手动触发：立即开始清理过期媒体文件
    """
    background_tasks.add_task(task_cleanup_old_media)
    return {"message": "Media cleanup task triggered in background"}