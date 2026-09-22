"""DeepSeek 客户端：仅用于会话级回复策略生成。

意图/动机/关系信号等判断全部由 Jev（预制 taxonomy）完成；
DeepSeek 只读取 Signal Engine 聚合后的 dashboard + 近期消息，
给出回复策略说明与 2-3 条具体回复建议。

依赖：仅 Python 标准库 urllib（无新增第三方依赖）。
"""

import json
import os
import urllib.error
import urllib.request
from typing import List, Tuple

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT = 30

SYSTEM_PROMPT = (
    "你是聊天策略助手。输入是系统对一段对话的结构化分析："
    "整体聚合（对话方向/主导动机/指标均值/规则策略提示）+ 每条对方消息的逐条分析"
    "（index、原文、意图、动机、对话方向、证据）。你的任务：\n"
    "1. strategy：一句话回复策略说明（针对整段对话当前状态）；\n"
    "2. replies：2-3 条针对最新一条对方消息的回复建议；\n"
    "3. per_message：为输入中的每一条对方消息（按 index）各给出 1-2 条回复建议，"
    "要贴合该消息自身的意图/动机/方向判断和上下文。\n"
    "通用要求：回复自然、口语化、每条不超过 25 字；"
    "语气必须匹配关系热度（参考 warmth/intimacy/flirtiness 均值）："
    "双方已经很熟时，就像平时发微信一样说话——可以随意、带点玩笑或语气词（呀/啊/哈哈/~），"
    "严禁'您好''非常感谢''不好意思麻烦你'这类客套生疏的表达，"
    "也不要每句都用'呀啊哈哈'堆砌，自然就好；"
    "关系还生疏时才用礼貌但友好的语气。"
    "如果对方在降温或设边界，建议应留出空间而不是继续推进；"
    "不要表白话术或操控感情的话术。\n"
    "只返回 JSON 对象，格式："
    '{"strategy": "一句话策略", "replies": ["..."], '
    '"per_message": [{"index": 0, "replies": ["..."]}]}'
)


def suggest_replies(payload: dict, api_key: str | None = None) -> Tuple[str, List[str], List[dict]]:
    """基于 dashboard + 逐条分析生成 (策略, 整体建议, 每条消息建议)。

    per_message: [{"index": int, "replies": [str]}]。失败抛 RuntimeError。
    """
    key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    payload = {
        "overall_direction": payload.get("overall_direction"),
        "dominant_motivation": payload.get("dominant_motivation"),
        "scores_avg": payload.get("scores_avg"),
        "strategy_hint": payload.get("strategy_hint"),
        "recent_evidence": payload.get("recent_evidence", [])[:8],
        "recent_messages": payload.get("recent_messages", [])[-6:],
        "messages_analysis": payload.get("messages_analysis", [])[-20:],
    }

    body = json.dumps(
        {
            "model": DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "对话结构化分析：\n"
                    + json.dumps(payload, ensure_ascii=False, indent=1),
                },
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "temperature": 0.7,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP {e.code}: {detail}") from None
    except Exception as e:
        raise RuntimeError(f"DeepSeek 请求失败：{e}") from e

    try:
        content = json.loads(raw)["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"DeepSeek 响应解析失败：{e}；原始：{raw[:200]}") from e

    return _parse_payload(content)


def _parse_payload(content: str) -> Tuple[str, List[str], List[dict]]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        first, last = text.find("{"), text.rfind("}")
        if first != -1 and last != -1:
            text = text[first : last + 1]

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"DeepSeek 输出非合法 JSON：{e}；内容：{content[:200]}") from e
    if not isinstance(obj, dict):
        raise RuntimeError(f"DeepSeek 输出非对象：{content[:200]}")

    strategy = str(obj.get("strategy", "")).strip()

    def _clean_str_list(raw) -> List[str]:
        out: List[str] = []
        if isinstance(raw, list):
            for r in raw:
                if isinstance(r, str) and r.strip():
                    out.append(r.strip())
        return out

    replies = _clean_str_list(obj.get("replies"))[:3]

    per_message: List[dict] = []
    raw_pm = obj.get("per_message")
    if isinstance(raw_pm, list):
        for item in raw_pm:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            msg_replies = _clean_str_list(item.get("replies"))[:2]
            if msg_replies:
                per_message.append({"index": idx, "replies": msg_replies})

    if not replies and not per_message:
        raise RuntimeError(f"DeepSeek 未返回回复建议：{content[:200]}")

    return strategy, replies, per_message
