from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, PostgresDsn, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "BrandMonitor"
    API_V1_STR: str = "/api/v1"
    
    # 服务器基础 URL (用于生成完整的图片链接)
    # 本地测试时可能是 http://localhost:8000
    # 部署时应设置为服务器的公网 IP 或域名，例如 http://1.2.3.4:8000
    SERVER_HOST: str = "http://localhost:8000"

    # 数据库配置
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str = "5432"
    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None

    @validator("SQLALCHEMY_DATABASE_URI", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        
        # 针对 PostgresDsn 的构建，不同 Pydantic 版本可能有差异
        # 这里构建标准 postgresql://user:pass@host:port/db
        password = values.get("POSTGRES_PASSWORD")
        if not password:
            password = None

        return PostgresDsn.build(
            scheme="postgresql",
            username=values.get("POSTGRES_USER"),
            password=password,
            host=values.get("POSTGRES_SERVER"),
            port=int(values.get("POSTGRES_PORT")),
            path=values.get("POSTGRES_DB") or "",
        )

    # 静态文件目录
    STATIC_DIR: str = "static"
    IMAGES_DIR: str = "static/images"

    # 定时任务配置
    SCHEDULER_INTERVAL_HOURS: int = 4  # 默认4小时抓取一次
    MEDIA_RETENTION_DAYS: int = 60     # 媒体文件保留天数

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")


settings = Settings()