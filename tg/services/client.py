"""
Telegram客户端封装模块

提供统一的Telegram客户端接口,处理连接管理、消息处理等
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable, Union

from telethon import TelegramClient, events
from telethon.errors import AuthKeyDuplicatedError, FloodWaitError

from .event_bus import telegram_event_bus, TelegramEventType
from tg.exceptions import TelegramConnectionError, RetryableError
from tg.config import telegram_config


class TelegramClientManager:
    """Telegram客户端管理器"""

    def __init__(self, session_name: Optional[str] = None):
        self.session_name = session_name or telegram_config.TG_SESSION_NAME
        self.client: Optional[TelegramClient] = None
        self.logger = logging.getLogger(__name__)
        self.is_connected = False
        self.entities_cache: Dict[int, Any] = {}
        self.message_handlers: List[Callable] = []
        self.connection_retry_count = 0
        self.max_retries = telegram_config.TG_CONNECTION_RETRIES

    async def initialize(self):
        """初始化客户端"""
        try:
            proxy_config = telegram_config.get_proxy_config()

            self.client = TelegramClient(
                self.session_name,
                telegram_config.TG_API_ID,
                telegram_config.TG_API_HASH,
                proxy=proxy_config,
                timeout=telegram_config.TG_TIMEOUT
            )

            self.logger.info("Telegram client initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize Telegram client: {e}")
            raise TelegramConnectionError(f"Failed to initialize client: {e}")

    async def connect(self):
        """连接到Telegram"""
        if not self.client:
            await self.initialize()

        try:
            await self.client.start()
            self.is_connected = True
            self.connection_retry_count = 0

            me = await self.client.get_me()
            self.logger.info(f"Connected as: {me.first_name} (ID: {me.id})")

            await telegram_event_bus.publish(
                TelegramEventType.CONNECTION_RESTORED,
                {"client_id": me.id, "username": getattr(me, "username", None)},
                source="telegram_client"
            )

        except Exception as e:
            self.is_connected = False
            self.connection_retry_count += 1
            self.logger.error(f"Failed to connect to Telegram: {e}")
            raise TelegramConnectionError(f"Connection failed: {e}")

    async def disconnect(self):
        """断开连接"""
        if self.client and self.is_connected:
            try:
                await self.client.disconnect()
                self.is_connected = False
                self.logger.info("Disconnected from Telegram")
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")

    async def get_entity(self, entity_id: Union[int, str]) -> Any:
        """获取实体(用户、频道、群组)"""
        if not self.is_connected:
            raise TelegramConnectionError("Client not connected")

        if isinstance(entity_id, int) and entity_id in self.entities_cache:
            return self.entities_cache[entity_id]

        try:
            entity = await self.client.get_entity(entity_id)
            if hasattr(entity, "id"):
                self.entities_cache[entity.id] = entity
            return entity
        except Exception as e:
            self.logger.error(f"Failed to get entity {entity_id}: {e}")
            raise TelegramConnectionError(f"Failed to get entity: {e}")

    def add_message_handler(self, handler: Callable):
        """添加消息处理器"""
        self.message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable):
        """移除消息处理器"""
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)

    async def start_monitoring(self, entities: List[Union[int, str]]):
        """开始监控指定实体的消息"""
        if not self.is_connected:
            await self.connect()

        entity_objects = []
        for entity_id in entities:
            try:
                entity = await self.get_entity(entity_id)
                entity_objects.append(entity)
                entity_name = getattr(entity, "title", getattr(entity, "first_name", entity_id))
                self.logger.info(f"Monitoring entity: {entity_name} ({entity_id})")
            except Exception as e:
                self.logger.error(f"Failed to get entity {entity_id}: {e}")

        if not entity_objects:
            raise TelegramConnectionError("No valid entities to monitor")

        @self.client.on(events.NewMessage(chats=entity_objects))
        async def message_handler(event):
            try:
                message = event.message
                chat = await event.get_chat()

                await telegram_event_bus.publish(
                    TelegramEventType.MESSAGE_RECEIVED,
                    {
                        "message": message,
                        "chat": chat,
                        "chat_id": event.chat_id,
                        "sender_id": event.sender_id,
                        "text": message.text,
                        "date": message.date
                    },
                    source="telegram_client"
                )

                for handler in self.message_handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        self.logger.error(f"Error in message handler: {e}")
            except Exception as e:
                self.logger.error(f"Error handling message: {e}")

        self.logger.info(f"Started monitoring {len(entity_objects)} entities")

    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "is_connected": self.is_connected,
            "session_name": self.session_name,
            "retry_count": self.connection_retry_count,
            "entities_cached": len(self.entities_cache),
            "handlers_count": len(self.message_handlers)
        }


# 全局客户端管理器实例
telegram_client_manager = TelegramClientManager()
