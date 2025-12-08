"""
Telegram监控异常定义
"""

class TelegramMonitorError(Exception):
    """Telegram监控基础异常"""
    pass


class TelegramConnectionError(TelegramMonitorError):
    """Telegram连接错误"""
    pass


class TelegramAuthError(TelegramMonitorError):
    """Telegram认证错误"""
    pass


class MonitorNotRunningError(TelegramMonitorError):
    """监控器未运行"""
    pass


class RetryableError(TelegramMonitorError):
    """可重试的错误"""
    def __init__(self, message: str, max_retries: int = 3):
        self.retry_count = 0
        self.max_retries = max_retries
        super().__init__(message)

    def can_retry(self) -> bool:
        """判断是否可以重试"""
        return self.retry_count < self.max_retries

    def increment_retry(self):
        """增加重试计数"""
        self.retry_count += 1
