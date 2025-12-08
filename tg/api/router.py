"""
Telegram群组监控WebSocket API

提供实时Telegram消息推送和监控管理接口
"""

import asyncio
import logging
from typing import List, Optional, Dict, Set, Any
from datetime import datetime
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel

from tg.services.monitor import TelegramMonitorService
from tg.services.models import TelegramMessage, MonitorStatus
from tg.exceptions import TelegramMonitorError

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[WebSocket, List[int]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, group_ids: List[int]):
        """连接客户端"""
        await websocket.accept()
        async with self._lock:
            self.active_connections[websocket] = group_ids
        logger.info(f"WebSocket client connected, monitoring {len(group_ids)} groups")

    async def disconnect(self, websocket: WebSocket):
        """断开客户端"""
        async with self._lock:
            if websocket in self.active_connections:
                group_ids = self.active_connections.pop(websocket)
                logger.info(f"WebSocket client disconnected, was monitoring {len(group_ids)} groups")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket) -> bool:
        """发送消息给指定客户端"""
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to client: {e}")
            await self.disconnect(websocket)
            return False

    async def broadcast(self, message: Dict[str, Any]):
        """广播消息给所有客户端"""
        disconnected = []
        async with self._lock:
            clients = list(self.active_connections.keys())

        for websocket in clients:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected.append(websocket)

        # 清理断开的连接
        for ws in disconnected:
            await self.disconnect(ws)

    def get_connection_count(self) -> int:
        """获取活跃连接数"""
        return len(self.active_connections)


# 全局连接管理器
connection_manager = ConnectionManager()


class StartMonitorRequest(BaseModel):
    """启动监控请求"""
    group_ids: List[int] = []
    user_ids: List[int] = []


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    group_ids: Optional[str] = Query(None, description="群组ID,逗号分隔"),
    user_ids: Optional[str] = Query(None, description="用户ID,逗号分隔")
):
    """
    Telegram群组/用户监控WebSocket端点

    连接后自动开始接收指定群组和用户的消息推送

    参数:
    - group_ids: 群组ID列表,逗号分隔 (例: -1001234567890,-1009876543210)
    - user_ids: 用户ID列表,逗号分隔 (例: 123456789,987654321)

    消息协议:
    - 客户端 -> 服务端: {"type": "ping"} / {"type": "get_status"}
    - 服务端 -> 客户端: {"type": "message", "data": {...}} / {"type": "pong"}
    """
    # 解析群组ID
    monitored_group_ids = []
    if group_ids:
        try:
            monitored_group_ids = [int(x.strip()) for x in group_ids.split(',') if x.strip()]
        except ValueError as e:
            logger.error(f"Invalid group_ids format: {group_ids}, error: {e}")
            await websocket.close(code=1008, reason="Invalid group_ids format")
            return

    # 解析用户ID
    monitored_user_ids = []
    if user_ids:
        try:
            monitored_user_ids = [int(x.strip()) for x in user_ids.split(',') if x.strip()]
        except ValueError as e:
            logger.error(f"Invalid user_ids format: {user_ids}, error: {e}")
            await websocket.close(code=1008, reason="Invalid user_ids format")
            return

    # 如果没有指定群组,使用配置中的默认群组
    if not monitored_group_ids:
        try:
            from tg.config import telegram_config
            monitored_group_ids = telegram_config.get_group_ids()
        except Exception as e:
            logger.error(f"Failed to get default group_ids: {e}")

    # 如果没有指定用户,使用配置中的默认用户
    if not monitored_user_ids:
        try:
            from tg.config import telegram_config
            monitored_user_ids = telegram_config.get_user_ids()
        except Exception as e:
            logger.error(f"Failed to get default user_ids: {e}")

    # 合并所有监控的实体ID
    monitored_ids = monitored_group_ids + monitored_user_ids

    if not monitored_ids:
        await websocket.close(code=1008, reason="No group_ids or user_ids specified or configured")
        return

    # 连接客户端
    await connection_manager.connect(websocket, monitored_ids)

    try:
        # 获取监控服务实例
        monitor_service = await TelegramMonitorService.get_instance(monitored_group_ids, monitored_user_ids)

        # 添加WebSocket客户端到监控器
        await monitor_service.add_websocket_client(websocket)

        # 启动监控服务(如果还未启动)
        if not monitor_service.is_running:
            try:
                logger.info(f"Starting monitor service for {len(monitored_group_ids)} groups and {len(monitored_user_ids)} users")
                await monitor_service._safe_start()
                logger.info(f"Monitor service started successfully, is_running={monitor_service.is_running}")
            except Exception as e:
                logger.error(f"Failed to start monitor service: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "code": "MONITOR_START_FAILED",
                    "message": f"Failed to start monitor: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })
                # 启动失败后关闭连接
                await websocket.close(code=1011, reason=f"Monitor start failed: {str(e)}")
                return
        else:
            logger.info(f"Monitor service already running")

        # 发送连接成功消息
        monitored_entities = []
        if hasattr(monitor_service, 'monitored_entities'):
            # monitored_entities是list,不是dict
            monitored_entities = [
                {
                    "id": getattr(entity, 'id', None),
                    "name": getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                    "type": monitor_service._get_entity_type(entity)
                }
                for entity in monitor_service.monitored_entities
                if getattr(entity, 'id', None) in monitored_ids
            ]

        await websocket.send_json({
            "type": "connected",
            "status": "success",
            "message": "已连接到Telegram监控服务",
            "monitored_groups": monitored_group_ids,
            "monitored_users": monitored_user_ids,
            "monitored_entities": monitored_entities,
            "timestamp": datetime.now().isoformat()
        })

        # 保持连接,处理客户端消息
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                # 处理客户端请求
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })

                elif message.get("type") == "get_status":
                    status = monitor_service.get_status()
                    await websocket.send_json({
                        "type": "status",
                        "data": status
                    })

                elif message.get("type") == "subscribe":
                    # 添加更多群组到监控 (未来功能)
                    new_groups = message.get("group_ids", [])
                    if new_groups:
                        logger.info(f"Client requested subscribe to groups: {new_groups}")
                        # TODO: 实现动态添加群组功能

                elif message.get("type") == "unsubscribe":
                    # 移除群组监控 (未来功能)
                    remove_groups = message.get("group_ids", [])
                    if remove_groups:
                        logger.info(f"Client requested unsubscribe from groups: {remove_groups}")
                        # TODO: 实现动态移除群组功能

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from client: {e}")
                await websocket.send_json({
                    "type": "error",
                    "code": "INVALID_JSON",
                    "message": "Invalid JSON format",
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected normally")

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "code": "INTERNAL_ERROR",
                "message": f"服务器内部错误: {str(e)}",
                "timestamp": datetime.now().isoformat()
            })
        except:
            pass

    finally:
        # 清理资源
        if 'monitor_service' in locals():
            await monitor_service.remove_websocket_client(websocket)
        await connection_manager.disconnect(websocket)


@router.get("/status", response_model=Dict[str, Any], tags=["telegram"])
async def get_monitor_status():
    """
    获取监控器状态 (HTTP接口)

    返回监控器运行状态、统计信息和连接状态
    """
    try:
        # 尝试获取现有实例
        monitor_service = await TelegramMonitorService.get_instance()
        status = monitor_service.get_status()

        # 将status转为dict (如果是Pydantic模型)
        if hasattr(status, 'dict'):
            status_dict = status.dict()
        elif hasattr(status, 'model_dump'):
            status_dict = status.model_dump()
        elif isinstance(status, dict):
            status_dict = status
        else:
            status_dict = dict(status)

        return {
            "status": "success",
            "data": {
                **status_dict,
                "websocket_connections": connection_manager.get_connection_count()
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get monitor status: {e}")
        return {
            "status": "error",
            "message": str(e),
            "data": {
                "is_running": False,
                "websocket_connections": connection_manager.get_connection_count()
            },
            "timestamp": datetime.now().isoformat()
        }


@router.post("/start", tags=["telegram"])
async def start_monitor(request: StartMonitorRequest):
    """
    启动监控 (HTTP接口)

    参数:
    - group_ids: 要监控的群组ID列表
    - user_ids: 要监控的用户ID列表

    注意: 通常通过WebSocket连接自动启动,此接口用于手动控制
    """
    try:
        if not request.group_ids and not request.user_ids:
            raise HTTPException(status_code=400, detail="At least one of group_ids or user_ids must be provided")

        monitor_service = await TelegramMonitorService.get_instance(request.group_ids, request.user_ids)

        if monitor_service.is_running:
            return {
                "status": "info",
                "message": "监控器已在运行",
                "group_ids": request.group_ids,
                "user_ids": request.user_ids,
                "timestamp": datetime.now().isoformat()
            }

        await monitor_service._safe_start()

        return {
            "status": "success",
            "message": "监控已启动",
            "group_ids": request.group_ids,
            "user_ids": request.user_ids,
            "timestamp": datetime.now().isoformat()
        }

    except TelegramMonitorError as e:
        logger.error(f"Failed to start monitor: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start monitor: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error starting monitor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/stop", tags=["telegram"])
async def stop_monitor():
    """
    停止监控 (HTTP接口)

    停止Telegram监控服务,断开所有连接

    注意: 会影响所有WebSocket客户端
    """
    try:
        monitor_service = await TelegramMonitorService.get_instance()

        if not monitor_service.is_running:
            return {
                "status": "info",
                "message": "监控器未在运行",
                "timestamp": datetime.now().isoformat()
            }

        await monitor_service._safe_stop()

        # 通知所有WebSocket客户端
        await connection_manager.broadcast({
            "type": "monitor_stopped",
            "message": "监控服务已停止",
            "timestamp": datetime.now().isoformat()
        })

        return {
            "status": "success",
            "message": "监控已停止",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to stop monitor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop monitor: {str(e)}")


@router.get("/connections", tags=["telegram"])
async def get_connections():
    """
    获取WebSocket连接信息

    返回当前活跃的WebSocket连接数
    """
    return {
        "status": "success",
        "data": {
            "active_connections": connection_manager.get_connection_count(),
            "timestamp": datetime.now().isoformat()
        }
    }
