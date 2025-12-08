"""
Telegram配置管理

使用环境变量配置Telegram API相关参数
"""

import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class TelegramConfig(BaseSettings):
    """Telegram配置类"""

    # Telegram API凭据
    TG_API_ID: str = Field(..., env="TG_API_ID", description="Telegram API ID")
    TG_API_HASH: str = Field(..., env="TG_API_HASH", description="Telegram API Hash")

    # 代理配置
    TG_PROXY_HOST: str = Field("127.0.0.1", env="TG_PROXY_HOST", description="代理主机")
    TG_PROXY_PORT: int = Field(10808, env="TG_PROXY_PORT", description="代理端口")
    TG_USE_PROXY: bool = Field(False, env="TG_USE_PROXY", description="是否使用代理")

    # 会话配置
    TG_SESSION_NAME: str = Field("tg_monitor", env="TG_SESSION_NAME", description="会话文件名")
    TG_TIMEOUT: int = Field(30, env="TG_TIMEOUT", description="超时时间(秒)")
    TG_CONNECTION_RETRIES: int = Field(5, env="TG_CONNECTION_RETRIES", description="连接重试次数")
    TG_AUTO_RECONNECT: bool = Field(True, env="TG_AUTO_RECONNECT", description="自动重连")

    # 监控配置
    TG_MONITOR_GROUP_IDS: str = Field("", env="TG_MONITOR_GROUP_IDS", description="监控群组ID(逗号分隔)")
    TG_MONITOR_USER_IDS: str = Field("", env="TG_MONITOR_USER_IDS", description="监控用户ID(逗号分隔)")

    class Config:
        env_file = "../.env"  # 相对于backend目录,加载根目录的.env
        case_sensitive = True
        extra = "ignore"  # 忽略额外的环境变量

    def get_group_ids(self) -> List[int]:
        """解析群组ID列表"""
        if not self.TG_MONITOR_GROUP_IDS:
            return []
        try:
            return [int(x.strip()) for x in self.TG_MONITOR_GROUP_IDS.split(',') if x.strip()]
        except ValueError:
            return []

    def get_user_ids(self) -> List[int | str]:
        """
        解析用户ID/Username列表

        支持混合格式:
        - 数字ID: 123456789
        - Username: @username 或 username

        示例: "123456789,@alice,bob"
        """
        if not self.TG_MONITOR_USER_IDS:
            return []

        result = []
        for item in self.TG_MONITOR_USER_IDS.split(','):
            item = item.strip()
            if not item:
                continue

            # 尝试转换为整数
            try:
                result.append(int(item))
            except ValueError:
                # 不是数字，当作username处理
                # 移除开头的@符号（如果有）
                if item.startswith('@'):
                    item = item[1:]
                result.append(item)

        return result

    def get_proxy_config(self):
        """获取代理配置"""
        if self.TG_USE_PROXY:
            return ("socks5", self.TG_PROXY_HOST, self.TG_PROXY_PORT)
        return None


# 全局配置实例
try:
    telegram_config = TelegramConfig()
except Exception as e:
    # 如果配置加载失败,使用默认值(用于开发环境)
    print(f"Warning: Failed to load Telegram config: {e}")
    telegram_config = None
