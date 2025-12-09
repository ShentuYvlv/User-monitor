import os
import json
import logging
import shutil
import time
import random
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

import instaloader
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Brand, Post, PlatformType
from app.utils.instagram_helper import get_random_user_agent, apply_anti_detection

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self, db: Session):
        self.db = db
        
        # Enhanced Instaloader initialization with advanced User-Agent
        self.L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            filename_pattern="{date_utc}_UTC_{shortcode}",
            user_agent=get_random_user_agent(), # Random realistic User-Agent
            max_connection_attempts=3,
            request_timeout=30.0,
        )
        
        # Apply anti-detection monkey-patching (Jitter & Backoff)
        apply_anti_detection(self.L.context._session)
        
        # self.L.load_session_from_file(username) 
        
    def _random_sleep(self, min_seconds=2, max_seconds=5):
        """Simulate human-like delay (Application Layer)"""
        sleep_time = random.uniform(min_seconds, max_seconds)
        time.sleep(sleep_time)

    def fetch_and_save_posts(self, brand: Brand, limit: int = 10):
        """
        抓取指定品牌的 Instagram 帖子并存入数据库
        """
        username = brand.instagram_username
        if not username:
            logger.warning(f"Brand {brand.name} has no instagram_username.")
            return

        logger.info(f"Starting fetch for Instagram user: {username}")
        
        try:
            profile = instaloader.Profile.from_username(self.L.context, username)
        except instaloader.ProfileNotExistsException:
            logger.error(f"Instagram profile {username} not found.")
            return
        except instaloader.ConnectionException as e:
            logger.error(f"Connection error fetching {username} (IP might be blocked): {e}")
            return
        except Exception as e:
            logger.error(f"Error fetching profile {username}: {e}")
            return

        # 准备下载目录: static/images/instagram/{username}
        base_dir = Path(settings.IMAGES_DIR) / "instagram" / username
        base_dir.mkdir(parents=True, exist_ok=True)

        posts_iterator = profile.get_posts()
        
        count = 0
        for post in posts_iterator:
            if count >= limit:
                break
            
            shortcode = post.shortcode
            
            # 检查数据库是否已存在
            exists = self.db.query(Post).filter(
                Post.original_id == shortcode, 
                Post.platform == PlatformType.INSTAGRAM
            ).first()
            
            if exists:
                logger.info(f"Post {shortcode} already exists. Skipping.")
                count += 1
                continue

            logger.info(f"Processing new post {shortcode}...")
            
            target_dir = base_dir
            
            # 下载文件
            try:
                media_files = self._download_post_media(post, target_dir)
            except Exception as e:
                logger.error(f"Failed to download media for {shortcode}: {e}")
                media_files = []

            # 存入数据库
            new_post = Post(
                brand_id=brand.id,
                platform=PlatformType.INSTAGRAM,
                original_id=shortcode,
                content_text=post.caption,
                media_urls=json.dumps(media_files), # 存为 JSON 列表
                original_url=f"https://www.instagram.com/p/{shortcode}/",
                posted_at=post.date_utc
            )
            self.db.add(new_post)
            self.db.commit()
            
            count += 1
            
            # 每次下载后随机延迟，防止被判定为机器人
            self._random_sleep(2, 5)

        # 抓取完一个用户的所有目标帖子后，也要稍微休息一下，避免连续请求下一个用户太快
        self._random_sleep(5, 10)

    def _download_post_media(self, post: instaloader.Post, save_dir: Path) -> List[str]:
        """
        手动下载帖子的媒体文件，返回相对路径列表
        """
        import requests
        
        media_paths = []
        timestamp_str = post.date_utc.strftime("%Y%m%d_%H%M%S")
        prefix = f"{timestamp_str}_{post.shortcode}"
        
        # 使用 Instaloader 的 session 进行请求，这样能复用 User-Agent 等配置
        session = self.L.context._session

        # 内部下载帮助函数
        def download_file(url: str, suffix: str) -> Optional[str]:
            if not url:
                return None
            try:
                filename = f"{prefix}_{len(media_paths)}{suffix}"
                filepath = save_dir / filename
                
                # 如果文件已存在则跳过 (虽然上面已经判断过 DB，但防止文件残留)
                if filepath.exists():
                     # 生成相对路径: /static/images/instagram/{username}/{filename}
                    rel_path = f"/static/images/instagram/{save_dir.name}/{filename}"
                    return rel_path

                response = session.get(url, stream=True, timeout=30)
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # 生成相对路径
                rel_path = f"/static/images/instagram/{save_dir.name}/{filename}"
                return rel_path
            except Exception as e:
                logger.error(f"Error downloading {url}: {e}")
                return None

        # 1. 视频
        if post.is_video:
            path = download_file(post.video_url, ".mp4")
            if path: media_paths.append(path)
        
        # 2. Sidecar (多图/多视频)
        if post.typename == 'GraphSidecar':
            for node in post.get_sidecar_nodes():
                if node.is_video:
                    path = download_file(node.video_url, ".mp4")
                    if path: media_paths.append(path)
                else:
                    path = download_file(node.display_url, ".jpg")
                    if path: media_paths.append(path)
        
        # 3. 单图 (如果是视频，上面已经处理了视频文件，这里可能还有一个封面图，根据需求是否保留)
        # 如果不是 Sidecar 且不是 Video (即普通 GraphImage)
        elif not post.is_video:
             path = download_file(post.url, ".jpg")
             if path: media_paths.append(path)

        return media_paths

    def cleanup_old_media(self, days: int = 60):
        """
        清理旧的媒体文件和数据库记录
        """
        logger.info(f"Starting cleanup of media older than {days} days...")
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # 1. 查询过期帖子
        expired_posts = self.db.query(Post).filter(
            Post.posted_at < cutoff_date
        ).all()
        
        count = 0
        for post in expired_posts:
            # 删除文件
            if post.media_urls:
                try:
                    file_list = json.loads(post.media_urls)
                    for rel_path in file_list:
                        # rel_path format: /static/images/instagram/username/file.jpg
                        # convert to absolute system path
                        # settings.STATIC_DIR is "static"
                        # strip leading /
                        clean_path = rel_path.lstrip("/")
                        abs_path = Path(clean_path).resolve()
                        
                        if abs_path.exists():
                            os.remove(abs_path)
                            logger.info(f"Deleted file: {abs_path}")
                except Exception as e:
                    logger.error(f"Error deleting files for post {post.id}: {e}")
            
            # 删除数据库记录
            self.db.delete(post)
            count += 1
        
        self.db.commit()
        logger.info(f"Cleanup finished. Removed {count} posts and their media.")
