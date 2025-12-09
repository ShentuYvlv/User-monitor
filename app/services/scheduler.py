import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.instagram import InstagramService
from app.db.models import Brand

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def task_update_all_brands():
    """
    定时任务：轮询所有启用的品牌并抓取最新帖子
    """
    logger.info("Task Started: Update all brands")
    db: Session = SessionLocal()
    try:
        service = InstagramService(db)
        
        # 获取所有活跃品牌
        brands = db.query(Brand).filter(Brand.is_active == True).all()
        
        for brand in brands:
            try:
                # 默认抓取最新的 10 条
                service.fetch_and_save_posts(brand, limit=10)
            except Exception as e:
                logger.error(f"Error updating brand {brand.name}: {e}")
                
    except Exception as e:
        logger.error(f"Task Failed: {e}")
    finally:
        db.close()
    logger.info("Task Finished: Update all brands")

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
