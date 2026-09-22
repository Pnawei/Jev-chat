"""Jev 微信聊天判断 - FastAPI 后端。

流程：聊天记录 → Jev（预制 12 维 taxonomy，逐条对方消息）
              → Signal Engine（证据 / 趋势 / 聚合 / 策略提示）
              → Dashboard + DeepSeek（仅生成会话级回复策略）

提供：
- POST /api/parse  解析粘贴的聊天文本为结构化消息列表
- POST /api/analyze 逐条 Jev 分析 + 会话级 dashboard + 回复策略
"""

import asyncio
import os
import re
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import deepseek_client
import signal_engine
from jev_questions import build_questions, parse_jev_response
from typesafe_sdk import TypeSafeClient

# ============================================================
# 初始化
# ============================================================

load_dotenv()

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()

if not TYPESAFE_API_KEY:
    print("[WARN] TYPESAFE_API_KEY 未配置，/api/analyze 将无法工作")
    client = None
else:
    client = TypeSafeClient(api_key=TYPESAFE_API_KEY)

if not DEEPSEEK_API_KEY:
    print("[WARN] DEEPSEEK_API_KEY 未配置，回复策略将仅展示规则提示（strategy_hint）")

app = FastAPI(title="Jev Chat Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 解析 "A：xxx" / "A:xxx" / "A xxx" 行；冒号支持中英文，全半角空格可选
SEPARATOR_RE = re.compile(r"^([^:：\n]{1,30})\s*[:：]\s*(.*)$")


# ============================================================
# Schemas
# ============================================================

class ParseRequest(BaseModel):
    text: str


class Message(BaseModel):
    id: int
    sender: str
    text: str


class ParseResponse(BaseModel):
    messages: List[Message]
    senders: List[str]


class AnalyzeMessage(BaseModel):
    sender: str
    text: str


class AnalyzeRequest(BaseModel):
    messages: List[AnalyzeMessage]  # 完整对话（含双方所有消息）
    other_sender: str              # "对方"发送者名


# ============================================================
# Routes
# ============================================================

@app.get("/")
async def root():
    return {"status": "ok", "client_ready": client is not None}


@app.post("/api/parse", response_model=ParseResponse)
async def parse_chat(req: ParseRequest):
    """按行解析聊天文本。

    规则：
    - 形如 `A：xxx` / `A:xxx` 的行视为一条消息，冒号前为 sender
    - 不含冒号的非空行追加到上一条消息末尾（换行保留）
    - 空行跳过
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="聊天文本为空")

    messages: List[Message] = []
    senders: List[str] = []
    msg_id = 0

    for raw_line in req.text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = SEPARATOR_RE.match(line)
        if match:
            sender = match.group(1).strip()
            content = match.group(2).strip()
            msg_id += 1
            messages.append(Message(id=msg_id, sender=sender, text=content))
            if sender not in senders:
                senders.append(sender)
        else:
            # 追加到上一条
            if messages:
                messages[-1].text += "\n" + line
            # 没有上一条则忽略

    if not messages:
        raise HTTPException(status_code=400, detail="未识别到任何消息，请使用 'A：内容' 格式")

    return ParseResponse(messages=messages, senders=senders)


CONTEXT_BEFORE = 5  # 当前消息之前取几条
CONTEXT_AFTER = 4   # 当前消息之后取几条


def _build_context(all_msgs: List[AnalyzeMessage], idx: int) -> str:
    """拼接 idx 前 5 后 4 条（含当前，≤10 条）作为上下文。

    当前消息标注为「待分析」，让 Jev 聚焦判断这一条；
    上下文决定动机（同一句话在不同上下文中动机完全不同）。
    """
    start = max(0, idx - CONTEXT_BEFORE)
    end = min(len(all_msgs), idx + CONTEXT_AFTER + 1)
    lines = []
    for i in range(start, end):
        m = all_msgs[i]
        prefix = "【待分析】" if i == idx else ""
        lines.append(f"{prefix}{m.sender}：{m.text}")
    return "\n".join(lines)


@app.post("/api/analyze")
async def analyze_messages(req: AnalyzeRequest):
    """分析流程：

    1. 逐条"对方"消息：取前后 ≤10 条上下文 → Jev（预制 12 维 taxonomy）
    2. Signal Engine：本地证据抽取 + 趋势/聚合 → 会话级 dashboard
    3. DeepSeek：读 dashboard 聚合结果，生成会话级回复策略（一次调用；
       DEEPSEEK_API_KEY 缺失时仅返回规则提示 strategy_hint）
    """
    if client is None:
        raise HTTPException(status_code=500, detail="后端未配置 TYPESAFE_API_KEY")

    if not req.messages:
        raise HTTPException(status_code=400, detail="没有可分析的消息")

    if not req.other_sender:
        raise HTTPException(status_code=400, detail="未指定 other_sender")

    other_indices = [
        i for i, m in enumerate(req.messages) if m.sender == req.other_sender
    ]
    if not other_indices:
        raise HTTPException(status_code=400, detail="该发送者没有消息")

    sem = asyncio.Semaphore(4)
    questions = build_questions()  # 所有消息共用同一套预制 questions

    async def analyze_one(order: int, idx: int):
        async with sem:
            msg = req.messages[idx]
            context = _build_context(req.messages, idx)

            try:
                response = await asyncio.to_thread(
                    client.system_one,
                    state=context,
                    questions=questions,
                )
                analysis = parse_jev_response(response)
            except Exception as e:  # noqa: BLE001
                analysis = {"error": f"Jev 分析失败：{e}"}
                return {
                    "index": order,
                    "sender": msg.sender,
                    "text": msg.text,
                    "analysis": analysis,
                }

            # 证据在本地抽取（literal 引用原句）
            analysis["evidence"] = signal_engine.extract_evidence(msg.text)

            return {
                "index": order,
                "sender": msg.sender,
                "text": msg.text,
                "analysis": analysis,
            }

    tasks = [analyze_one(order, idx) for order, idx in enumerate(other_indices)]
    results = await asyncio.gather(*tasks)

    # ---- Signal Engine：会话级聚合 ----
    ok_analyses = [
        r["analysis"] for r in results if "error" not in r["analysis"]
    ]
    dashboard = signal_engine.build_dashboard(ok_analyses)

    # ---- DeepSeek：一次调用生成 整体策略 + 每条消息的回复建议 ----
    if dashboard is not None and DEEPSEEK_API_KEY:
        payload = {
            "overall_direction": dashboard["overall_direction"],
            "dominant_motivation": dashboard["dominant_motivation"],
            "scores_avg": {
                k: v["avg"] for k, v in dashboard["scores"].items()
            },
            "strategy_hint": dashboard["strategy_hint"],
            "recent_evidence": dashboard["evidence"][-8:],
            "recent_messages": [
                {"sender": m.sender, "text": m.text}
                for m in req.messages[-6:]
            ],
            "messages_analysis": [
                {
                    "index": r["index"],
                    "text": r["text"][:50],
                    "intent": r["analysis"]["intent"]["label"],
                    "motivation": r["analysis"]["motivation"]["label"],
                    "direction": r["analysis"]["conversation_direction"]["label"],
                    "evidence": [
                        f"{ev['label']}：{ev['text']}" for ev in r["analysis"]["evidence"][:2]
                    ],
                }
                for r in results
                if "error" not in r["analysis"]
            ],
        }
        try:
            strategy, replies, per_message = await asyncio.to_thread(
                deepseek_client.suggest_replies, payload, DEEPSEEK_API_KEY
            )
            dashboard["reply_strategy"] = strategy
            dashboard["reply_suggestions"] = replies
            per_map = {pm["index"]: pm["replies"] for pm in per_message}
            for r in results:
                if "error" not in r["analysis"]:
                    msg_replies = per_map.get(r["index"])
                    if msg_replies:
                        r["analysis"]["suggested_replies"] = msg_replies
        except Exception as e:  # noqa: BLE001
            dashboard["reply_error"] = f"回复策略生成失败：{e}"

    return {"results": list(results), "dashboard": dashboard}
