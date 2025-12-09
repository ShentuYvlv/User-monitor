import os
import json
import logging
import shutil
import time
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

import instaloader
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Brand, Post, PlatformType

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self, db: Session):
        self.db = db
        self.L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            filename_pattern="{date_utc}_UTC_{shortcode}"
        )
        # 尝试加载 Session (如果有) - 这里可以扩展为从 .env 读取账号密码登录
        # self.L.load_session_from_file(username) 
        
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
            
            # 下载逻辑
            # Instaloader 默认下载到当前工作目录，我们需要控制它
            # 或者我们手动下载媒体资源，这里为了利用 instaloader 的解析能力，我们使用 download_post
            # 但 download_post 会下载到 target 目录。
            
            target_dir = base_dir
            
            # 下载文件
            try:
                # download_post 会下载图片、视频、文案等到 target_dir
                # 为了避免文件名混乱，Instaloader 会使用 filename_pattern
                # 我们需要在下载后收集生成的文件名
                
                # 由于 instaloader API 直接下载比较难获取确切的文件名列表用于存库，
                # 我们这里采用 iterate over sidecars / video_url / url 手动处理更可控，
                # 或者使用 instaloader 下载后扫描目录。
                # 考虑到稳定性，我们手动提取 URL 并下载。
                
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
            # 简单的防风控延迟
            time.sleep(2) 

    def _download_post_media(self, post: instaloader.Post, save_dir: Path) -> List[str]:
        """
        手动下载帖子的媒体文件，返回相对路径列表
        """
        import requests
        
        media_paths = []
        timestamp_str = post.date_utc.strftime("%Y%m%d_%H%M%S")
        prefix = f"{timestamp_str}_{post.shortcode}"
        
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

                response = requests.get(url, stream=True, timeout=30)
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
