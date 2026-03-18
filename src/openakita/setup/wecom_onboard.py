"""
企业微信智能机器人扫码配置

用于 Setup Center QR 扫码快速获取 bot_id + secret：
- 调用企微 /ai/qc/generate 生成二维码（返回 qr_url + qr_id）
- 轮询 /ai/qc/query_result 获取扫码结果（返回 bot_id + secret）

接口来自企业微信智能机器人管理后台（非公开 API，基于 openclaw-plugin-wecom 逆向）。

所有 HTTP 调用均为 async（httpx），bridge.py 通过 asyncio.run() 驱动。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WECOM_QC_BASE = "https://developer.work.weixin.qq.com"
QC_GENERATE_PATH = "/ai/qc/generate"
QC_QUERY_RESULT_PATH = "/ai/qc/query_result"


class WecomOnboardError(Exception):
    """扫码配置过程中的业务错误"""


class WecomOnboard:
    """企业微信智能机器人扫码配置

    Flow:
    1. generate() → 获取 qr_url (二维码链接) + qr_id
    2. poll(qr_id) → 查询扫码结果，成功返回 bot_id + secret
    """

    def __init__(self, *, timeout: float = 30.0):
        self._timeout = timeout

    async def generate(self) -> dict[str, Any]:
        """Step 1: 生成二维码

        Returns:
            dict with at least:
                qr_url: str   — 二维码图片 URL / 扫码链接
                qr_id: str    — 用于后续轮询的标识
                expire_in: int — 有效期（秒）
        """
        data = await self._post(QC_GENERATE_PATH)
        if not data.get("qr_url") and not data.get("qr_id"):
            raise WecomOnboardError(f"generate 未返回有效数据: {data}")
        return data

    async def poll(self, qr_id: str) -> dict[str, Any]:
        """Step 2: 查询扫码结果

        Returns:
            成功: {bot_id: str, secret: str, ...}
            等待: {status: "pending"}
            过期: {status: "expired"}
            失败: {status: "error", error: "..."}
        """
        data = await self._post(QC_QUERY_RESULT_PATH, qr_id=qr_id)

        if data.get("bot_id") and data.get("secret"):
            data["status"] = "success"
            return data

        status = data.get("status", "")
        if not status:
            if data.get("errcode") or data.get("error"):
                data["status"] = "error"
            else:
                data["status"] = "pending"
        return data

    async def poll_until_done(
        self,
        qr_id: str,
        *,
        interval: float = 3.0,
        max_attempts: int = 100,
    ) -> dict[str, Any]:
        """持续轮询直到用户扫码完成或超时

        Returns:
            成功时的完整响应 (含 bot_id / secret)

        Raises:
            WecomOnboardError: 轮询超时或二维码过期
        """
        for _ in range(max_attempts):
            result = await self.poll(qr_id)

            if result.get("bot_id") and result.get("secret"):
                return result

            status = result.get("status", "")
            if status in ("expired", "error"):
                raise WecomOnboardError(
                    f"扫码终止: {status} - {result.get('error', '')}"
                )

            await asyncio.sleep(interval)

        raise WecomOnboardError(
            f"轮询超时: {max_attempts} 次尝试后仍未完成扫码"
        )

    async def _post(self, path: str, **json_fields: str) -> dict[str, Any]:
        """发送 JSON POST 请求到企微 QR 配置端点"""
        url = WECOM_QC_BASE + path
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                json=json_fields if json_fields else {},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
