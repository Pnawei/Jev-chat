"""Signal Engine：证据抽取、趋势聚合、回复策略提示。

对应架构：
    Jev（12 维判断）
        ↓
    Signal Engine
        - Evidence   本地规则抽取（每条证据 literal 引用原句，可被验证）
        - Trend      各 0-100 指标 首条→末条 变化
        - Aggregation 会话级聚合（均值、主导动机、整体方向）
        - Strategy   基于规则的回复策略提示（供 LLM 参考 / 兜底展示）
"""

import re
from collections import Counter
from typing import Dict, List, Optional

from jev_questions import DIRECTION_NAMES, MOTIVATION_NAMES

# ============================================================
# ⑫ Evidence：证据类型（预制 taxonomy，全部可被原句支持或反驳）
# ============================================================

EVIDENCE_LABELS = {
    "direct_question": "直接提问",
    "follow_up_question": "追问",
    "self_disclosure": "自我暴露",
    "personal_detail": "个人细节",
    "emotional_response": "情绪反应",
    "compliment": "称赞",
    "teasing": "调侃",
    "inside_joke": "内部梗",
    "future_plan": "未来计划",
    "meetup_suggestion": "提出见面",
    "reengagement": "重新开启对话",
    "memory_of_user": "记得你的细节",
    "concern": "关心",
    "flirty_language": "暧昧表达",
    "boundary": "设边界",
    "topic_avoidance": "回避话题",
    "conversation_closing": "结束对话",
}

# 每类证据的匹配规则（按顺序尝试；一条句子可命中多类，去重输出）
_SENT_SPLIT_RE = re.compile(r"[。！？!?~\n]+")

_EVIDENCE_RULES = [
    ("flirty_language", re.compile(r"想你了?|喜欢你|抱抱|亲亲|宝贝|心动|撩|暧昧")),
    ("boundary", re.compile(r"别问了|不想说|不方便|别联系|不合适|别多想|到此为止|先不聊这个")),
    ("topic_avoidance", re.compile(r"不说这个|换个话题|别提了|无所谓|随便吧|不想聊")),
    ("conversation_closing", re.compile(r"拜拜|先走了|晚安|回聊|下次聊|不聊了|去忙|先这样")),
    ("meetup_suggestion", re.compile(r"一起(去|吃|看|玩)|见面|我?约你|在(.{0,6})等你|来找你|见你")),
    ("future_plan", re.compile(r"下次|改天|以后|回头|打算|周末(去|有空)?")),
    ("reengagement", re.compile(r"在吗|好久不见|最近怎么样|突然想起你|又来找我")),
    ("memory_of_user", re.compile(r"你上次|你之前|你说过|你提到|记得你|你那个")),
    ("concern", re.compile(r"注意安全|早点休息|多喝|别熬夜|小心|照顾好自己|到了(吗|了没)|路上.{0,4}安全")),
    ("teasing", re.compile(r"你(真|太|好)(笨|傻|二|皮|逗)|小笨蛋|傻瓜|笑死|服了你")),
    ("compliment", re.compile(r"厉害|优秀|真棒|不错|好看|可爱|聪明|靠谱|有意思")),
    ("emotional_response", re.compile(r"哈哈|嘿嘿|嘻|天哪|哇|真的假的|不会吧|我靠|啊这")),
    ("self_disclosure", re.compile(r"我(其实|最近|一直|特别|挺|还是)[^。！？!?\n]{1,20}|我(喜欢|讨厌|害怕|担心|压力|累|烦|开心|难过|想)")),
    ("personal_detail", re.compile(r"我(在|家|们)?(工作|上班|上学|专业|老板|同事|室友|同学)|我家|我住")),
    ("follow_up_question", re.compile(r"(那|所以|然后|后来|接着)[^。！？!?\n]*[？?]")),
    ("direct_question", re.compile(r"[？?]|(吗|呢|多少|几|什么|怎么|哪|是不是|能不能|要不要)")),
]


def extract_evidence(text: str) -> List[Dict[str, str]]:
    """从一条消息中抽取证据列表 [{type, label, text}]。

    text 为 literal 引用消息中的原句（可被用户直接验证）。
    """
    evidence = []
    seen = set()
    for raw in _SENT_SPLIT_RE.split(text or ""):
        sentence = raw.strip()
        if not sentence:
            continue
        for etype, pattern in _EVIDENCE_RULES:
            if pattern.search(sentence):
                key = (etype, sentence)
                if key not in seen:
                    seen.add(key)
                    evidence.append({
                        "type": etype,
                        "label": EVIDENCE_LABELS[etype],
                        "text": sentence,
                    })
    return evidence


# ============================================================
# Trend / Aggregation / Dashboard
# ============================================================

def _trend(delta: float) -> str:
    if delta >= 15:
        return "rising"
    if delta <= -15:
        return "falling"
    return "stable"


def build_dashboard(analyses: List[dict]) -> Optional[dict]:
    """把按时间顺序排列的各条分析聚合成会话级 dashboard。

    analyses: 每项为 parse_jev_response 的输出（已附 evidence），
              顺序即对方消息在对话中的顺序。空列表返回 None。
    """
    if not analyses:
        return None

    # --- 7 个 0-100 指标：均值 + 趋势 ---
    scores: Dict[str, dict] = {}
    for name in analyses[0].get("scores", {}):
        values = [
            a["scores"][name]["value"]
            for a in analyses
            if a.get("scores", {}).get(name, {}).get("value") is not None
        ]
        if not values:
            scores[name] = {"avg": None, "first": None, "last": None, "delta": 0, "trend": "stable"}
            continue
        delta = values[-1] - values[0]
        scores[name] = {
            "avg": round(sum(values) / len(values)),
            "first": values[0],
            "last": values[-1],
            "delta": delta,
            "trend": _trend(delta),
        }

    # --- Choice 分布 ---
    direction_counts = Counter(
        a["conversation_direction"]["key"] for a in analyses if a.get("conversation_direction")
    )
    motivation_counts = Counter(
        a["motivation"]["key"] for a in analyses if a.get("motivation")
    )

    # 整体方向：以最近 3 条的主导方向为准（"聊天正在往哪里发展"）
    recent_dirs = [a["conversation_direction"]["key"] for a in analyses[-3:] if a.get("conversation_direction")]
    overall_key = Counter(recent_dirs).most_common(1)[0][0] if recent_dirs else "unclear"
    dom_mot_key = motivation_counts.most_common(1)[0][0] if motivation_counts else "unclear"

    # --- 证据汇总（带消息序号）---
    evidence_all = []
    for i, a in enumerate(analyses):
        for ev in a.get("evidence", []):
            evidence_all.append({**ev, "index": i})

    # --- 规则策略提示（供 LLM 参考，也在 LLM 失败时兜底展示）---
    strategy_hint = _strategy_hint(
        overall_key=overall_key,
        dominant_motivation=dom_mot_key,
        scores=scores,
        evidence_all=evidence_all,
    )

    return {
        "scores": scores,
        "direction_counts": dict(direction_counts),
        "motivation_counts": dict(motivation_counts),
        "overall_direction": {"key": overall_key, "label": DIRECTION_NAMES.get(overall_key, overall_key)},
        "dominant_motivation": {"key": dom_mot_key, "label": MOTIVATION_NAMES.get(dom_mot_key, dom_mot_key)},
        "evidence": evidence_all,
        "strategy_hint": strategy_hint,
        "reply_strategy": None,
        "reply_suggestions": [],
        "reply_error": None,
    }


def _strategy_hint(overall_key, dominant_motivation, scores, evidence_all) -> str:
    """基于规则的回复策略提示。识别降温/边界信号同样重要，不做无脑推动。"""
    hint_parts = []
    types = {e["type"] for e in evidence_all}

    if overall_key in ("end", "deescalate") or "boundary" in types:
        hint_parts.append("对方在降温或设立边界：放缓节奏、留出空间，不要连续追问或强行推进")
    elif overall_key == "meetup":
        hint_parts.append("对方有推进现实见面的意愿：可以给出具体的时间/地点选项，把约定敲定")
    elif overall_key in ("deepen", "personalize"):
        hint_parts.append("对方在深入话题或转向个人化：可以分享一点自己的相关经历，再留一个开放式问题")
    elif overall_key == "escalate":
        hint_parts.append("对方在提高互动亲密度：可以适度回应升温，同时观察对方后续反馈")
    elif overall_key == "play":
        hint_parts.append("对方想保持轻松玩笑氛围：用幽默接住，不要突然转严肃")
    else:
        hint_parts.append("保持当前节奏，围绕对方提到的内容自然继续")

    if dominant_motivation == "testing":
        hint_parts.append("对方在试探你的态度：回应时轻松但明确地表达真实想法")
    if dominant_motivation == "care" or "concern" in types:
        hint_parts.append("对方表达了关心：先接住这份关心（回应+感谢），再继续话题")
    if scores.get("flirtiness", {}).get("avg") is not None and scores["flirtiness"]["avg"] >= 60:
        hint_parts.append("互动温度已偏高：可以适度升级表达，但保持对等，避免单方面推进过快")
    if scores.get("vulnerability", {}).get("avg") is not None and scores["vulnerability"]["avg"] >= 60:
        hint_parts.append("对方暴露了较多脆弱/私密内容：认真回应这份信任，不要轻描淡写带过")

    return "；".join(hint_parts) + "。"
