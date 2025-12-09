from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base

class PlatformType(str, enum.Enum):
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    FACEBOOK = "facebook"

class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    instagram_username = Column(String, nullable=True)
    telegram_channel_id = Column(String, nullable=True) # 预留
    twitter_username = Column(String, nullable=True)    # 预留
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    posts = relationship("Post", back_populates="brand", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    
    platform = Column(Enum(PlatformType), nullable=False, default=PlatformType.INSTAGRAM)
    original_id = Column(String, index=True, nullable=False) # IG shortcode or Tweet ID
    
    content_text = Column(Text, nullable=True)
    media_urls = Column(Text, nullable=True) # 存储 JSON 字符串: ["/static/...", "/static/..."]
    original_url = Column(String, nullable=True)
    
    posted_at = Column(DateTime, nullable=True) # 帖子实际发布时间
    created_at = Column(DateTime, default=datetime.utcnow) # 抓取入库时间

    brand = relationship("Brand", back_populates="posts")
