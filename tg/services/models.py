"""
Telegram监控数据模型

定义消息、状态等数据结构
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class TelegramMessage(BaseModel):
    """Telegram消息数据模型"""
    message_id: int
    chat_id: int
    chat_name: str
    sender_id: int
    sender_name: str
    text: str
    date: datetime
    has_media: bool
    media_type: Optional[str] = None
    timestamp: datetime
    # 添加解析后的结构化数据
    parsed_type: Optional[str] = "other"  # "tweet" / "reply" / "other"
    parsed_data: Optional[Dict[str, Any]] = None  # 解析后的结构化字段

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MonitorStatus(BaseModel):
    """监控器状态模型"""
    is_running: bool
    monitored_count: int
    message_count: int
    uptime: float
    connection_status: str
    monitored_entities: List[dict] = []


class TelegramEntity(BaseModel):
    """Telegram实体(群组/频道)模型"""
    id: int
    name: str
    type: str  # 群组/频道/超级群组
    username: Optional[str] = None


class WebSocketMessage(BaseModel):
    """WebSocket消息模型"""
    type: str  # message, connected, status, error, pong
    data: Optional[dict] = None
    message: Optional[str] = None
    timestamp: datetime = None

    def __init__(self, **data):
        if data.get('timestamp') is None:
            data['timestamp'] = datetime.now()
        super().__init__(**data)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
