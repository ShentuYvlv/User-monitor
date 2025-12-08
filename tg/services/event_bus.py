"""
Telegram事件总线模块

实现发布-订阅模式,用于Telegram监控组件间的解耦通信
"""

import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TelegramEventType(Enum):
    """Telegram事件类型枚举"""
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_PROCESSED = "message_processed"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    ERROR_OCCURRED = "error_occurred"
    MONITOR_STARTED = "monitor_started"
    MONITOR_STOPPED = "monitor_stopped"


@dataclass
class TelegramEvent:
    """Telegram事件数据类"""
    type: TelegramEventType
    data: Any
    timestamp: datetime
    source: str
    event_id: Optional[str] = None

    def __post_init__(self):
        if self.event_id is None:
            self.event_id = f"{self.type.value}_{self.timestamp.timestamp()}"


class TelegramEventBus:
    """Telegram事件总线"""

    def __init__(self):
        self._subscribers: Dict[TelegramEventType, List[Callable]] = {}
        self._logger = logging.getLogger(__name__)
        self._event_history: List[TelegramEvent] = []
        self._max_history = 1000

    def subscribe(self, event_type: TelegramEventType, callback: Callable[[TelegramEvent], None]):
        """订阅事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        self._logger.debug(f"Subscribed to {event_type.value}")

    def unsubscribe(self, event_type: TelegramEventType, callback: Callable[[TelegramEvent], None]):
        """取消订阅事件"""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                self._logger.debug(f"Unsubscribed from {event_type.value}")
            except ValueError:
                self._logger.warning(f"Callback not found for {event_type.value}")

    async def publish(self, event_type: TelegramEventType, data: Any, source: str = "unknown"):
        """发布事件"""
        event = TelegramEvent(
            type=event_type,
            data=data,
            timestamp=datetime.now(),
            source=source
        )

        # 记录事件历史
        self._add_to_history(event)

        # 通知所有订阅者
        if event_type in self._subscribers:
            tasks = []
            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        tasks.append(callback(event))
                    else:
                        # 对于非异步回调,在线程池中执行
                        loop = asyncio.get_event_loop()
                        tasks.append(loop.run_in_executor(None, callback, event))
                except Exception as e:
                    self._logger.error(f"Error executing callback for {event_type.value}: {e}")

            # 并发执行所有回调
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        self._logger.debug(f"Published event {event_type.value} from {source}")

    def _add_to_history(self, event: TelegramEvent):
        """添加到事件历史"""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

    def get_event_history(self, event_type: Optional[TelegramEventType] = None,
                         limit: int = 100) -> List[TelegramEvent]:
        """获取事件历史"""
        if event_type is None:
            return self._event_history[-limit:]
        else:
            filtered = [e for e in self._event_history if e.type == event_type]
            return filtered[-limit:]

    def clear_history(self):
        """清空事件历史"""
        self._event_history.clear()

    def get_subscriber_count(self, event_type: TelegramEventType) -> int:
        """获取事件订阅者数量"""
        return len(self._subscribers.get(event_type, []))


# 全局Telegram事件总线实例
telegram_event_bus = TelegramEventBus()
