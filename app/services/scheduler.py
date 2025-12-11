import logging
import shutil
import time
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.instagram import InstagramService
from app.services.twitter import TwitterService
from app.schemas import TwitterScrapeRequest
from app.db.models import Brand, Post

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def task_update_all_brands(brand_name: str = None, limit: int = settings.SCHEDULER_FETCH_LIMIT):
    """
    定时任务：轮询所有启用的品牌并抓取最新帖子 (Instagram & Twitter)
    支持手动触发时指定品牌和数量
    """
    task_desc = f"Update brand '{brand_name}'" if brand_name else "Update all brands"
    logger.info(f"Task Started: {task_desc} (limit={limit})")
    
    db = SessionLocal()
    try:
        # 初始化 Services
        insta_service = InstagramService(db)
        twitter_service = TwitterService(db)
        
        query = db.query(Brand).filter(Brand.is_active == True)
        if brand_name:
            query = query.filter(Brand.name == brand_name)
            
        brands = query.all()
        
        if not brands and brand_name:
            logger.warning(f"Brand '{brand_name}' not found or inactive.")
            return

        for brand in brands:
            # 1. Instagram
            if brand.instagram_username:
                try:
                    logger.info(f"Updating Instagram for {brand.name}...")
                    insta_service.fetch_and_save_posts(brand, limit=limit)
                except Exception as e:
                    logger.error(f"Error updating Instagram for {brand.name}: {e}")
            
            # 2. Twitter (Async call wrapper)
            if brand.twitter_username:
                try:
                    logger.info(f"Updating Twitter for {brand.name}...")
                    req = TwitterScrapeRequest(username=brand.twitter_username, limit=limit)
                    # 由于 scrape_and_save 是 async 的，而 APScheduler 默认运行在同步线程
                    # 我们需要创建一个新的事件循环来运行它，或者使用 asyncio.run
                    asyncio.run(twitter_service.scrape_and_save(req, brand.id))
                except Exception as e:
                    logger.error(f"Error updating Twitter for {brand.name}: {e}")

    except Exception as e:
        logger.error(f"Task Failed: {e}")
    finally:
        db.close()
    logger.info(f"Task Finished: {task_desc}")

def task_cleanup_old_media():
    """
    定时任务：清理过期媒体文件
    """
    logger.info("Task Started: Cleanup old media")
    db: Session = SessionLocal()
    try:
        service = InstagramService(db)
        service.cleanup_old_media(days=settings.MEDIA_RETENTION_DAYS)
    except Exception as e:
        logger.error(f"Cleanup Task Failed: {e}")
    finally:
        db.close()
    logger.info("Task Finished: Cleanup old media")

def start_scheduler():
    # 任务1: 定期抓取 (默认每4小时)
    scheduler.add_job(
        task_update_all_brands,
        IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
        id="update_brands",
        name="Update Instagram Brands",
        replace_existing=True
    )
    
    # 任务2: 每天清理一次过期文件
    scheduler.add_job(
        task_cleanup_old_media,
        IntervalTrigger(days=1),
        id="cleanup_media",
        name="Cleanup Old Media",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started.")
