from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Any

from app.core.database import get_db
from app.core.security import get_api_key
from app.schemas import TwitterScrapeRequest
from app.services.twitter import TwitterService
from app.db import models

router = APIRouter(dependencies=[Depends(get_api_key)])

@router.post("/scrape", status_code=200)
async def trigger_twitter_scrape(
    request: TwitterScrapeRequest,
    db: Session = Depends(get_db)
) -> Any:
    """
    手动触发 Twitter 抓取任务。
    input: 
      - username: 可以是 Brand 的名称 (name) 或者 Twitter 的用户名 (twitter_username)
    """
    service = TwitterService(db)
    
    input_name = request.username
    target_twitter_user = None
    brand_obj = None

    # 1. 尝试按 Brand Name 查找
    brand_by_name = db.query(models.Brand).filter(models.Brand.name == input_name).first()
    if brand_by_name:
        if brand_by_name.twitter_username:
            brand_obj = brand_by_name
            target_twitter_user = brand_by_name.twitter_username
        else:
            raise HTTPException(status_code=400, detail=f"Brand '{input_name}' exists but has no twitter_username configured.")
    
    # 2. 如果按 Name 没找到，或者输入的不像是 Name，尝试按 Twitter Username 查找
    if not brand_obj:
        brand_by_username = db.query(models.Brand).filter(models.Brand.twitter_username == input_name).first()
        if brand_by_username:
            brand_obj = brand_by_username
            target_twitter_user = brand_by_username.twitter_username

    # 3. 最终检查
    if not brand_obj or not target_twitter_user:
        raise HTTPException(
            status_code=404, 
            detail=f"No brand found with name or twitter_username matching '{input_name}'"
        )

    # 构造传递给 Service 的请求对象 (Service 层只认真实的 twitter username)
    # 这里我们需要创建一个临时的 request 对象或者修改 service 签名，为了保持一致性，我们创建一个新的 request 对象
    service_request = TwitterScrapeRequest(
        username=target_twitter_user,
        limit=request.limit
    )

    try:
        result = await service.scrape_and_save(service_request, brand_obj.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
