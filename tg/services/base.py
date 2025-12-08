"""
Telegram监控器基类

提供监控器的基础框架和通用功能
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from datetime import datetime

from .event_bus import telegram_event_bus, TelegramEventType
from tg.exceptions import TelegramMonitorError, RetryableError


class BaseTelegramMonitor(ABC):
    """Telegram监控器基类"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.stats = {
            'messages_processed': 0,
            'errors_count': 0,
            'last_activity': None
        }

    @abstractmethod
    async def start(self):
        """启动监控"""
        pass

    @abstractmethod
    async def stop(self):
        """停止监控"""
        pass

    @abstractmethod
    async def process_message(self, message: Any) -> bool:
        """处理消息"""
        pass

    async def _safe_start(self):
        """安全启动监控器"""
        try:
            self.is_running = True
            self.start_time = datetime.now()
            await telegram_event_bus.publish(
                TelegramEventType.MONITOR_STARTED,
                {'monitor': self.name},
                source=self.name
            )
            await self.start()
            self.logger.info(f"Monitor {self.name} started successfully")
        except Exception as e:
            self.is_running = False
            self.logger.error(f"Failed to start monitor {self.name}: {e}")
            await telegram_event_bus.publish(
                TelegramEventType.ERROR_OCCURRED,
                {'monitor': self.name, 'error': str(e)},
                source=self.name
            )
            raise TelegramMonitorError(f"Failed to start monitor {self.name}: {e}")

    async def _safe_stop(self):
        """安全停止监控器"""
        try:
            await self.stop()
            self.is_running = False
            await telegram_event_bus.publish(
                TelegramEventType.MONITOR_STOPPED,
                {'monitor': self.name},
                source=self.name
            )
            self.logger.info(f"Monitor {self.name} stopped successfully")
        except Exception as e:
            self.logger.error(f"Error stopping monitor {self.name}: {e}")
            await telegram_event_bus.publish(
                TelegramEventType.ERROR_OCCURRED,
                {'monitor': self.name, 'error': str(e)},
                source=self.name
            )

    async def _safe_process_message(self, message: Any) -> bool:
        """安全处理消息"""
        try:
            result = await self.process_message(message)
            self.stats['messages_processed'] += 1
            self.stats['last_activity'] = datetime.now()
            return result
        except RetryableError as e:
            self.logger.warning(f"Retryable error in {self.name}: {e}")
            if e.can_retry():
                e.increment_retry()
                await asyncio.sleep(2 ** e.retry_count)  # 指数退避
                return await self._safe_process_message(message)
            else:
                self.stats['errors_count'] += 1
                await telegram_event_bus.publish(
                    TelegramEventType.ERROR_OCCURRED,
                    {'monitor': self.name, 'error': str(e), 'message': message},
                    source=self.name
                )
                return False
        except Exception as e:
            self.stats['errors_count'] += 1
            self.logger.error(f"Error processing message in {self.name}: {e}")
            await telegram_event_bus.publish(
                TelegramEventType.ERROR_OCCURRED,
                {'monitor': self.name, 'error': str(e), 'message': message},
                source=self.name
            )
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取监控器状态"""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()

        return {
            'name': self.name,
            'is_running': self.is_running,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'uptime': uptime,
            'stats': self.stats.copy()
        }

    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self.config.copy()

    def update_config(self, new_config: Dict[str, Any]):
        """更新配置"""
        self.config.update(new_config)
        self.logger.info(f"Config updated for monitor {self.name}")
