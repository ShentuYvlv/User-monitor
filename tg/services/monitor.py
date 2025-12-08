"""
Telegram Group Monitor Module

Core features:
- Monitor multiple Telegram groups/channels for messages
- Real-time message processing and parsing
- Broadcast via WebSocket to frontend clients
- Complete lifecycle management and error handling

Design Philosophy:
- State as Responsibility: Who creates, who destroys
- Async as Temporal: Time is the fourth dimension
- Decoupling as Freedom: Component communication through event bus
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set, Union
from datetime import datetime

from telethon.tl.types import Message
from fastapi import WebSocket

from .base import BaseTelegramMonitor
from .client import telegram_client_manager
from .event_bus import telegram_event_bus, TelegramEventType
from .models import TelegramMessage, MonitorStatus, WebSocketMessage
from tg.exceptions import TelegramMonitorError
from tg.config import telegram_config


class TelegramGroupMonitor(BaseTelegramMonitor):
    """
    Telegram Group Monitor

    Three-layer architecture:
    Phenomenon Layer: Receive Telegram messages, send WebSocket messages
    Essence Layer: Message processing, state management, error recovery
    Philosophy Layer: Event-driven, unidirectional data flow, defensive programming
    """

    def __init__(self, group_ids: List[int], user_ids: Optional[List[Union[int, str]]] = None):
        """
        Initialize group monitor

        Args:
            group_ids: List of group/channel IDs to monitor
            user_ids: List of user IDs or usernames to monitor (optional)
                     - int: numeric user ID (e.g., 123456789)
                     - str: username (e.g., "username" or "@username")

        Design Principles:
        - Defensive programming: Validate all inputs
        - Contract design: Clear preconditions
        """
        user_ids = user_ids or []
        super().__init__("telegram_group_monitor", {"group_ids": group_ids, "user_ids": user_ids})

        if not group_ids and not user_ids:
            raise TelegramMonitorError("At least one group ID or user ID must be provided")

        self.group_ids = group_ids
        self.user_ids = user_ids
        self.monitored_entities: List[Any] = []
        self.message_count = 0

        # WebSocket client set - use Set for uniqueness and O(1) deletion
        self.websocket_clients: Set[WebSocket] = set()
        self._websocket_lock = asyncio.Lock()  # Protect concurrent access

        # Subscribe to event bus
        telegram_event_bus.subscribe(
            TelegramEventType.MESSAGE_RECEIVED,
            self._handle_message_received_event
        )
        telegram_event_bus.subscribe(
            TelegramEventType.CONNECTION_LOST,
            self._handle_connection_lost_event
        )
        telegram_event_bus.subscribe(
            TelegramEventType.CONNECTION_RESTORED,
            self._handle_connection_restored_event
        )

    async def start(self):
        """
        Start group monitoring

        Startup flow:
        1. Validate configuration
        2. Connect Telegram client
        3. Fetch and cache entities
        4. Register message handlers
        5. Begin monitoring

        Error handling:
        - Config errors: Fail fast
        - Connection errors: Retry mechanism
        - Entity errors: Partial success strategy
        """
        try:
            if not self.group_ids and not self.user_ids:
                raise TelegramMonitorError("No group IDs or user IDs configured for monitoring")

            # Ensure client is connected
            if not telegram_client_manager.is_connected:
                self.logger.info("Telegram client not connected, connecting now...")
                await telegram_client_manager.connect()

            # Fetch and validate all entities
            await self._fetch_monitored_entities()

            if not self.monitored_entities:
                raise TelegramMonitorError(
                    "No valid entities to monitor. Check group IDs and permissions."
                )

            # Register message handler
            telegram_client_manager.add_message_handler(self._process_telegram_message)

            # Start monitoring
            entity_ids = [
                getattr(entity, 'id', entity) for entity in self.monitored_entities
            ]
            await telegram_client_manager.start_monitoring(entity_ids)

            # Update state
            self.is_running = True
            self.start_time = datetime.now()

            # Publish startup event
            await telegram_event_bus.publish(
                TelegramEventType.MONITOR_STARTED,
                {
                    'monitor': self.name,
                    'entities': len(self.monitored_entities),
                    'group_ids': self.group_ids,
                    'user_ids': self.user_ids
                },
                source=self.name
            )

            self.logger.info(
                f"Telegram group monitor started successfully. "
                f"Monitoring {len(self.monitored_entities)} entities."
            )

        except Exception as e:
            self.is_running = False
            self.logger.error(f"Failed to start telegram group monitor: {e}", exc_info=True)
            raise TelegramMonitorError(f"Failed to start monitor: {e}")

    async def stop(self):
        """
        Stop group monitoring

        Cleanup flow:
        1. Remove message handlers
        2. Unsubscribe events
        3. Disconnect all WebSocket connections
        4. Clean up resources

        Design Principles:
        - Graceful degradation: Continue cleanup even if parts fail
        - Resource management: Ensure all resources are released
        """
        try:
            # Remove message handler
            telegram_client_manager.remove_message_handler(self._process_telegram_message)

            # Unsubscribe events
            telegram_event_bus.unsubscribe(
                TelegramEventType.MESSAGE_RECEIVED,
                self._handle_message_received_event
            )
            telegram_event_bus.unsubscribe(
                TelegramEventType.CONNECTION_LOST,
                self._handle_connection_lost_event
            )
            telegram_event_bus.unsubscribe(
                TelegramEventType.CONNECTION_RESTORED,
                self._handle_connection_restored_event
            )

            # Close all WebSocket connections
            await self._close_all_websockets()

            # Update state
            self.is_running = False

            # Publish stop event
            await telegram_event_bus.publish(
                TelegramEventType.MONITOR_STOPPED,
                {
                    'monitor': self.name,
                    'message_count': self.message_count,
                    'uptime': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
                },
                source=self.name
            )

            self.logger.info(
                f"Telegram group monitor stopped. "
                f"Processed {self.message_count} messages."
            )

        except Exception as e:
            self.logger.error(f"Error stopping telegram group monitor: {e}", exc_info=True)

    async def process_message(self, message: Any) -> bool:
        """
        Process message - BaseTelegramMonitor abstract method implementation

        Args:
            message: Telegram message object

        Returns:
            bool: Whether processing succeeded
        """
        return await self._process_telegram_message(message)

    async def _fetch_monitored_entities(self):
        """
        Fetch and cache entities to monitor

        Strategy: Partial success - get as many available entities as possible
        Failed entities are logged but won't block overall startup
        """
        self.monitored_entities = []

        # Fetch group/channel entities
        for entity_id in self.group_ids:
            try:
                entity = await telegram_client_manager.get_entity(entity_id)
                self.monitored_entities.append(entity)

                # Extract entity info
                entity_name = getattr(entity, 'title', getattr(entity, 'first_name', str(entity_id)))
                entity_type = self._get_entity_type(entity)

                self.logger.info(f"Added {entity_type}: {entity_name} (ID: {entity_id})")

            except Exception as e:
                self.logger.error(f"Failed to get group entity {entity_id}: {e}")
                # Continue processing other entities, don't interrupt flow

        # Fetch user entities
        for entity_id in self.user_ids:
            try:
                # Determine if it's an ID or username
                is_username = isinstance(entity_id, str)
                identifier_type = "username" if is_username else "ID"

                self.logger.info(f"Attempting to fetch user by {identifier_type}: {entity_id}")

                entity = await telegram_client_manager.get_entity(entity_id)
                self.monitored_entities.append(entity)

                # Extract entity info
                real_id = getattr(entity, 'id', None)
                entity_name = getattr(entity, 'first_name', str(entity_id))
                last_name = getattr(entity, 'last_name', '')
                username = getattr(entity, 'username', '')

                if last_name:
                    entity_name += f" {last_name}"
                if username:
                    entity_name += f" (@{username})"

                entity_type = self._get_entity_type(entity)

                self.logger.info(f"✅ Successfully added {entity_type}: {entity_name} (ID: {real_id})")

            except Exception as e:
                self.logger.error(
                    f"❌ Failed to get user entity '{entity_id}' ({identifier_type}): {e}\n"
                    f"   Possible solutions:\n"
                    f"   1. If using ID: Ensure you have interacted with this user before\n"
                    f"   2. Try using username instead: TG_MONITOR_USER_IDS=@username\n"
                    f"   3. Add the user to one of your monitored groups first"
                )
                # Continue processing other entities, don't interrupt flow

    def _get_entity_type(self, entity) -> str:
        """
        Determine entity type

        Args:
            entity: Telegram entity object

        Returns:
            str: Entity type description
        """
        if hasattr(entity, 'megagroup') and entity.megagroup:
            return "Supergroup"
        elif hasattr(entity, 'broadcast') and entity.broadcast:
            return "Channel"
        elif hasattr(entity, 'title'):
            return "Group"
        else:
            return "User"

    @staticmethod
    def _parse_tweet_content(text: str) -> Dict[str, Any]:
        """
        解析推文消息内容

        支持三种格式:
        类型1: 推文
        🌟监控到新推文
        你关注的用户: XXX
        用户所属分组: XXX
        推文内容: XXX

        类型2: 回复
        🌟监控到新推文回复
        你关注的用户: XXX
        用户所属分组: XXX
        上文内容: XXX
        回帖内容: XXX

        类型3: 其他类型 - 返回原文

        Args:
            text: 消息文本

        Returns:
            dict: {
                'type': 'tweet' | 'reply' | 'other',
                'user': str (可选),
                'group': str (可选),
                'content': str (可选),
                'context': str (可选, reply类型)
            }
        """
        import re
        import logging

        logger = logging.getLogger(__name__)

        if not text:
            return {'type': 'other', 'content': ''}

        # 先清理markdown格式符号 (**, __, 等)
        cleaned_text = re.sub(r'\*\*', '', text)  # 移除 **
        cleaned_text = re.sub(r'__', '', cleaned_text)  # 移除 __

        # 调试日志: 打印前300字符
        logger.debug(f"[Parse Debug] Cleaned text (first 300 chars): {cleaned_text[:300]}")

        # 类型1: 推文
        # 格式: 🌟监控到新推文\n你关注的用户: XXX\n用户所属分组: XXX\n推文内容: XXX
        # 改进: 使用 [^\n]+ 匹配到换行符之前的所有内容,更精确
        tweet_pattern = r'🌟监控到新推文[\s\S]*?你关注的用户:\s*([^\n]+)\s*\n\s*用户所属分组:\s*([^\n]+)\s*\n\s*推文内容:\s*([\s\S]+)'
        tweet_match = re.search(tweet_pattern, cleaned_text)

        if tweet_match:
            user = tweet_match.group(1).strip()
            group = tweet_match.group(2).strip()
            content = tweet_match.group(3).strip()

            logger.debug(f"[Parse Debug] Tweet matched - user: '{user}', group: '{group}', content_len: {len(content)}")

            return {
                'type': 'tweet',
                'user': user,
                'group': group,
                'content': content
            }

        # 类型2: 回复
        # 格式: 🌟监控到新推文回复\n你关注的用户: XXX\n用户所属分组: XXX\n上文内容: XXX\n回帖内容: XXX
        reply_pattern = r'🌟监控到新推文回复[\s\S]*?你关注的用户:\s*([^\n]+)\s*\n\s*用户所属分组:\s*([^\n]+)\s*\n\s*上文内容:\s*([^\n]+)\s*\n\s*回帖内容:\s*([\s\S]+)'
        reply_match = re.search(reply_pattern, cleaned_text)

        if reply_match:
            user = reply_match.group(1).strip()
            group = reply_match.group(2).strip()
            context = reply_match.group(3).strip()
            content = reply_match.group(4).strip()

            logger.debug(f"[Parse Debug] Reply matched - user: '{user}', group: '{group}'")

            return {
                'type': 'reply',
                'user': user,
                'group': group,
                'context': context,
                'content': content
            }

        # 类型3: 其他类型 - 返回清理后的内容
        logger.debug(f"[Parse Debug] No pattern matched, returning as 'other' type")
        return {
            'type': 'other',
            'content': cleaned_text
        }

    async def _handle_message_received_event(self, event):
        """
        Handle MESSAGE_RECEIVED event

        Core of event-driven architecture - respond to event bus messages
        """
        try:
            message_data = event.data
            message = message_data.get('message')
            chat_id = message_data.get('chat_id')

            # Filter: only process messages from monitored groups
            monitored_ids = [getattr(entity, 'id', None) for entity in self.monitored_entities]
            if chat_id not in monitored_ids:
                return

            # Delegate to message processor
            await self._process_telegram_message(message)

        except Exception as e:
            self.logger.error(f"Error handling message received event: {e}", exc_info=True)

    async def _handle_connection_lost_event(self, event):
        """Handle connection lost event"""
        self.logger.warning("Telegram connection lost, notifying WebSocket clients")
        await self._broadcast_status_to_websocket("connection_lost")

    async def _handle_connection_restored_event(self, event):
        """Handle connection restored event"""
        self.logger.info("Telegram connection restored, notifying WebSocket clients")
        await self._broadcast_status_to_websocket("connection_restored")

    async def _process_telegram_message(self, message: Message) -> bool:
        """
        Process Telegram message - Core business logic

        Processing flow:
        1. Validate message
        2. Extract message data
        3. Construct structured data
        4. Broadcast to WebSocket clients
        5. Publish processing event

        Args:
            message: Telethon Message object

        Returns:
            bool: Whether processing succeeded

        Design Principles:
        - Defensive programming: Handle all possible None and exceptions
        - Data immutability: Message data is not modified once created
        """
        try:
            if not message:
                self.logger.warning("Received None message, skipping")
                return False

            # Increment counter
            self.message_count += 1

            # Extract basic info - defensive access
            chat_id = getattr(message, 'chat_id', None)
            message_id = getattr(message, 'id', None)
            message_text = getattr(message, 'text', '') or ''
            message_date = getattr(message, 'date', datetime.now())

            # Get sender info
            sender_id = None
            sender_name = "Unknown"
            try:
                sender = await message.get_sender() if hasattr(message, 'get_sender') else None
                if sender:
                    sender_id = getattr(sender, 'id', None)
                    first_name = getattr(sender, 'first_name', '') or ''
                    last_name = getattr(sender, 'last_name', '') or ''
                    username = getattr(sender, 'username', '')

                    sender_name = first_name
                    if last_name:
                        sender_name += f" {last_name}"
                    if not sender_name and username:
                        sender_name = username
                    if not sender_name:
                        sender_name = "Unknown"
            except Exception as e:
                self.logger.warning(f"Failed to get sender info: {e}")

            # Get group info
            chat_name = "Unknown Group"
            try:
                chat = await message.get_chat() if hasattr(message, 'get_chat') else None
                if chat:
                    chat_name = getattr(chat, 'title', getattr(chat, 'username', 'Unknown Group'))
            except Exception as e:
                self.logger.warning(f"Failed to get chat info: {e}")

            # Detect media type
            has_media = hasattr(message, 'media') and message.media is not None
            media_type = None
            if has_media:
                media_type = type(message.media).__name__

            # Parse tweet content - 解析推文内容
            parsed_result = self._parse_tweet_content(message_text)
            parsed_type = parsed_result.get('type', 'other')
            # 移除type字段,剩余的作为parsed_data
            parsed_data = {k: v for k, v in parsed_result.items() if k != 'type'}

            # Construct structured message data
            telegram_msg = TelegramMessage(
                message_id=message_id,
                chat_id=chat_id,
                chat_name=chat_name,
                sender_id=sender_id or 0,
                sender_name=sender_name,
                text=message_text,
                date=message_date,
                has_media=has_media,
                media_type=media_type,
                timestamp=datetime.now(),
                parsed_type=parsed_type,
                parsed_data=parsed_data
            )

            # Log to logger
            self.logger.info(
                f"[Message #{self.message_count}] "
                f"From: {chat_name} | "
                f"Sender: {sender_name} | "
                f"Text: {message_text[:50]}..."
            )

            # Broadcast to WebSocket clients
            # 使用 model_dump 并设置 mode='json' 来正确序列化 datetime
            if hasattr(telegram_msg, 'model_dump'):
                message_dict = telegram_msg.model_dump(mode='json')
            else:
                message_dict = telegram_msg.dict()
                # 手动转换 datetime 为 ISO 格式字符串
                if 'date' in message_dict and isinstance(message_dict['date'], datetime):
                    message_dict['date'] = message_dict['date'].isoformat()
                if 'timestamp' in message_dict and isinstance(message_dict['timestamp'], datetime):
                    message_dict['timestamp'] = message_dict['timestamp'].isoformat()

            await self._broadcast_to_websocket(message_dict)

            # Publish processing complete event
            await telegram_event_bus.publish(
                TelegramEventType.MESSAGE_PROCESSED,
                {
                    'monitor': self.name,
                    'message': message_dict,  # 使用已经序列化好的dict
                    'count': self.message_count
                },
                source=self.name
            )

            # Update stats
            self.stats['messages_processed'] = self.message_count
            self.stats['last_activity'] = datetime.now()

            return True

        except Exception as e:
            self.logger.error(f"Error processing telegram message: {e}", exc_info=True)
            self.stats['errors_count'] += 1
            return False

    async def _broadcast_to_websocket(self, message_data: Dict[str, Any]):
        """
        Broadcast message to all WebSocket clients

        Args:
            message_data: Message data dictionary

        Concurrency strategy:
        - Async concurrent send to all clients
        - Failed connections automatically removed
        - Use lock to protect client set modifications
        """
        if not self.websocket_clients:
            return

        # Construct WebSocket message
        ws_message = WebSocketMessage(
            type="message",
            data=message_data
        )

        # Concurrent send to all clients
        tasks = []
        for ws_client in list(self.websocket_clients):  # Copy to avoid modification during iteration
            tasks.append(self._send_to_websocket_client(ws_client, ws_message))

        # Wait for all sends to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results - remove failed connections
        failed_clients = []
        for ws_client, result in zip(list(self.websocket_clients), results):
            if isinstance(result, Exception):
                self.logger.warning(f"Failed to send to WebSocket client: {result}")
                failed_clients.append(ws_client)

        # Batch remove failed clients
        if failed_clients:
            async with self._websocket_lock:
                for ws_client in failed_clients:
                    self.websocket_clients.discard(ws_client)
            self.logger.info(f"Removed {len(failed_clients)} failed WebSocket connections")

    async def _send_to_websocket_client(self, ws_client: WebSocket, message: WebSocketMessage):
        """
        Send message to single WebSocket client

        Args:
            ws_client: WebSocket connection object
            message: WebSocket message object
        """
        try:
            if hasattr(message, 'model_dump'):
                await ws_client.send_json(message.model_dump(mode='json'))
            else:
                await ws_client.send_json(message.dict())
        except Exception as e:
            self.logger.debug(f"Error sending to WebSocket client: {e}")
            raise  # Re-raise for upstream handling

    async def _broadcast_status_to_websocket(self, status_type: str):
        """
        Broadcast status update to WebSocket clients

        Args:
            status_type: Status type (connection_lost, connection_restored, etc.)
        """
        if not self.websocket_clients:
            return

        ws_message = WebSocketMessage(
            type="status",
            data={"status": status_type}
        )

        tasks = [
            self._send_to_websocket_client(ws, ws_message)
            for ws in list(self.websocket_clients)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def add_websocket_client(self, websocket: WebSocket):
        """
        Add WebSocket client

        Args:
            websocket: FastAPI WebSocket object
        """
        async with self._websocket_lock:
            self.websocket_clients.add(websocket)

        self.logger.info(
            f"WebSocket client added. Total clients: {len(self.websocket_clients)}"
        )

        # Send welcome message
        status = self.get_status()
        if hasattr(status, 'model_dump'):
            status_dict = status.model_dump(mode='json')
        else:
            status_dict = status.dict()

        welcome_message = WebSocketMessage(
            type="connected",
            message=f"Connected to Telegram monitor. Monitoring {len(self.monitored_entities)} groups.",
            data=status_dict
        )
        try:
            if hasattr(welcome_message, 'model_dump'):
                await websocket.send_json(welcome_message.model_dump(mode='json'))
            else:
                await websocket.send_json(welcome_message.dict())
        except Exception as e:
            self.logger.error(f"Failed to send welcome message: {e}")

    async def remove_websocket_client(self, websocket: WebSocket):
        """
        Remove WebSocket client

        Args:
            websocket: FastAPI WebSocket object
        """
        async with self._websocket_lock:
            self.websocket_clients.discard(websocket)

        self.logger.info(
            f"WebSocket client removed. Total clients: {len(self.websocket_clients)}"
        )

    async def _close_all_websockets(self):
        """Close all WebSocket connections"""
        if not self.websocket_clients:
            return

        self.logger.info(f"Closing {len(self.websocket_clients)} WebSocket connections...")

        # Send close notification
        close_message = WebSocketMessage(
            type="status",
            message="Monitor is shutting down"
        )

        tasks = []
        for ws_client in list(self.websocket_clients):
            async def close_client(ws):
                try:
                    if hasattr(close_message, 'model_dump'):
                        await ws.send_json(close_message.model_dump(mode='json'))
                    else:
                        await ws.send_json(close_message.dict())
                    await ws.close()
                except Exception as e:
                    self.logger.debug(f"Error closing WebSocket: {e}")

            tasks.append(close_client(ws_client))

        await asyncio.gather(*tasks, return_exceptions=True)

        # Clear set
        async with self._websocket_lock:
            self.websocket_clients.clear()

    def get_status(self) -> MonitorStatus:
        """
        Get monitor status

        Returns:
            MonitorStatus: Status data model
        """
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()

        connection_status = "connected" if telegram_client_manager.is_connected else "disconnected"

        monitored_entities_list = [
            {
                'id': getattr(entity, 'id', None),
                'name': getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                'type': self._get_entity_type(entity)
            }
            for entity in self.monitored_entities
        ]

        return MonitorStatus(
            is_running=self.is_running,
            monitored_count=len(self.monitored_entities),
            message_count=self.message_count,
            uptime=uptime,
            connection_status=connection_status,
            monitored_entities=monitored_entities_list
        )


class TelegramMonitorService:
    """
    Telegram Monitor Service - Singleton Pattern

    Provides global access point, manages TelegramGroupMonitor lifecycle

    Usage:
        service = TelegramMonitorService()
        await service.start([group_id1, group_id2])
        await service.add_websocket_client(websocket)
    """

    _instance: Optional[TelegramGroupMonitor] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, group_ids: Optional[List[int]] = None, user_ids: Optional[List[Union[int, str]]] = None) -> TelegramGroupMonitor:
        """
        Get or create monitor instance

        Args:
            group_ids: Group ID list (only needed on first creation)
            user_ids: User ID list (only needed on first creation)

        Returns:
            TelegramGroupMonitor: Monitor instance
        """
        async with cls._lock:
            if cls._instance is None:
                if group_ids is None:
                    # Read from config
                    group_ids = telegram_config.get_group_ids() if telegram_config else []

                if user_ids is None:
                    # Read from config
                    user_ids = telegram_config.get_user_ids() if telegram_config else []

                if not group_ids and not user_ids:
                    raise TelegramMonitorError("No group IDs or user IDs provided for monitoring")

                cls._instance = TelegramGroupMonitor(group_ids, user_ids)

            return cls._instance

    @classmethod
    async def start(cls, group_ids: Optional[List[int]] = None, user_ids: Optional[List[Union[int, str]]] = None):
        """Start monitoring service"""
        instance = await cls.get_instance(group_ids, user_ids)
        if not instance.is_running:
            await instance.start()

    @classmethod
    async def stop(cls):
        """Stop monitoring service"""
        async with cls._lock:
            if cls._instance and cls._instance.is_running:
                await cls._instance.stop()

    @classmethod
    async def add_websocket(cls, websocket: WebSocket):
        """Add WebSocket client"""
        instance = await cls.get_instance()
        await instance.add_websocket_client(websocket)

    @classmethod
    async def remove_websocket(cls, websocket: WebSocket):
        """Remove WebSocket client"""
        if cls._instance:
            await cls._instance.remove_websocket_client(websocket)

    @classmethod
    def get_status(cls) -> Optional[MonitorStatus]:
        """Get monitoring status"""
        if cls._instance:
            return cls._instance.get_status()
        return None


# Convenient global access point
telegram_monitor_service = TelegramMonitorService()
