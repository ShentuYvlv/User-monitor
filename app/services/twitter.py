import logging
import json
import httpx
import os
import shutil
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.models import Brand, Post, PlatformType
from app.schemas import TwitterScrapeRequest, TwitterScrapeResponse

logger = logging.getLogger(__name__)

class TwitterService:
    def __init__(self, db: Session):
        self.db = db
        self.scraper_url = f"{settings.TWITTER_SCRAPER_HOST}/scrape"

    async def _download_media(self, url: str, username: str, tweet_id: str, index: int) -> str | None:
        """
        下载媒体文件到本地 static/images/twitter/{username}/
        返回相对路径，例如: /static/images/twitter/elonmusk/123456_0.jpg
        """
        if not url:
            return None

        try:
            # 确定文件扩展名
            ext = ".jpg"
            if ".mp4" in url or "video" in url:
                ext = ".mp4"
            elif ".png" in url:
                ext = ".png"
            
            # 构建保存路径
            # 格式: static/images/twitter/{username}/{tweet_id}_{index}{ext}
            base_dir = Path(settings.IMAGES_DIR) / "twitter" / username
            base_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"{tweet_id}_{index}{ext}"
            file_path = base_dir / filename
            
            # 如果文件已存在，直接返回路径（避免重复下载）
            rel_path = f"/static/images/twitter/{username}/{filename}"
            if file_path.exists():
                return rel_path

            # 下载文件
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
            
            logger.info(f"Downloaded media: {rel_path}")
            return rel_path

        except Exception as e:
            logger.error(f"Failed to download media {url}: {e}")
            return url # 如果下载失败，保留原始链接作为 fallback

    async def scrape_and_save(self, request_data: TwitterScrapeRequest, brand_id: int):
        """
        调用 Node.js 微服务抓取推文，并保存到数据库
        :param request_data: 包含 resolved username (真实推特账号) 和 limit
        :param brand_id: 关联的品牌ID (必须提供)
        :return: 抓取结果统计
        """
        logger.info(f"Calling Twitter Scraper for user: {request_data.username}")

        # 构造发给微服务的 Payload
        payload = {
            "username": request_data.username,
            "limit": request_data.limit
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    self.scraper_url,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
            except httpx.RequestError as e:
                logger.error(f"Failed to connect to scraper service: {e}")
                raise Exception(f"Scraper service unavailable: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(f"Scraper service returned error {e.response.status_code}: {e.response.text}")
                raise Exception(f"Scraper failed: {e.response.text}")

        scrape_response = TwitterScrapeResponse(**data)
        
        if not scrape_response.success:
            raise Exception("Scraper reported failure")

        saved_count = 0
        
        for tweet in scrape_response.tweets:
            # 查重
            exists = self.db.query(Post).filter(
                Post.original_id == tweet.id,
                Post.platform == PlatformType.TWITTER
            ).first()

            if exists:
                continue

            # 处理并下载媒体
            raw_media_urls = []
            if tweet.photos:
                raw_media_urls.extend([p.get('url') for p in tweet.photos if p.get('url')])
            if tweet.videos:
                raw_media_urls.extend([v.get('url') for v in tweet.videos if v.get('url')])
            
            local_media_paths = []
            for i, url in enumerate(raw_media_urls):
                local_path = await self._download_media(url, request_data.username, tweet.id, i)
                if local_path:
                    local_media_paths.append(local_path)

            # 转换时间戳
            posted_at = datetime.fromtimestamp(tweet.timestamp) if tweet.timestamp else datetime.utcnow()

            new_post = Post(
                brand_id=brand_id,
                platform=PlatformType.TWITTER,
                original_id=tweet.id,
                content_text=tweet.text or "",
                media_urls=json.dumps(local_media_paths), # 存入本地路径
                original_url=tweet.permanentUrl or f"https://x.com/{request_data.username}/status/{tweet.id}",
                posted_at=posted_at
            )
            
            self.db.add(new_post)
            saved_count += 1

        self.db.commit()
        logger.info(f"Saved {saved_count} new tweets for {request_data.username}")
        
        return {
            "success": True,
            "fetched": scrape_response.count,
            "saved": saved_count,
            "user": request_data.username
        }
