from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, PostgresDsn, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "BrandMonitor"
    API_V1_STR: str = "/api/v1"
    
    # 服务器基础 URL
    SERVER_HOST: str = "http://localhost:8000"

    # 安全配置
    API_TOKEN: str = "secret-token"  # 默认值，请在 .env 中修改

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
    SCHEDULER_INTERVAL_HOURS: int = 2  # 默认每小时抓取一次
    SCHEDULER_FETCH_LIMIT: int = 5    # 每次抓取的帖子数量
    MEDIA_RETENTION_DAYS: int = 30     # 媒体文件保留天数

    # Twitter Scraper Microservice
    TWITTER_SCRAPER_HOST: str = "http://localhost:3000"
    TWITTER_PROXY_URL: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 允许 .env 中存在多余变量，防止报错


settings = Settings()
