"""Jev 问题定义与响应解析（MVP v1 taxonomy）。

所有选项均为预制 taxonomy，可被聊天证据支持或反驳：
- 4 个 Choice：表层意图 / 核心动机 / 关系信号 / 对话方向
- 1 个 Choice：情绪（辅助）
- 7 个 Score（11 级，展示时 ×10 映射为 0-100）：
  主动性 / 投入度 / 温度 / 亲密程度 / 暧昧程度 / 暴露程度 / 对你的关注
- confidence：4 个 Choice 置信度的平均值

Evidence（证据）不在 Jev 中产生（SDK 无自由文本题型），
由 signal_engine.extract_evidence 在本地做规则抽取，每条证据 literal 引用原句。
"""

from typesafe_sdk import Choice, Score


# ============================================================
# Taxonomy：key → 中文标签
# ============================================================

INTENT_NAMES = {
    "answer": "回答你的问题",
    "ask": "向你提问",
    "share": "主动分享信息",
    "react": "对你的内容做反应",
    "continue": "主动延续当前话题",
    "change_topic": "主动切换话题",
    "close": "试图结束当前对话",
    "avoid": "回避当前问题",
}

MOTIVATION_NAMES = {
    "information": "获取信息",
    "conversation": "寻找/维持聊天",
    "attention": "获得你的注意",
    "connection": "拉近彼此关系",
    "self_expression": "表达自己、分享生活",
    "emotional_support": "寻求情绪支持",
    "validation": "寻求认可/肯定",
    "playfulness": "玩笑、调侃、轻松氛围",
    "flirting": "暧昧/调情",
    "testing": "试探你的态度或反应",
    "care": "表达关心",
    "planning": "推进现实见面/活动",
    "ending": "礼貌结束互动",
    "avoidance": "回避某个话题或互动",
    "unclear": "证据不足，无法判断",
}

RELATIONSHIP_NAMES = {
    "neutral": "普通社交",
    "friendly": "友好",
    "personal": "比普通聊天更私人",
    "emotionally_close": "情绪上的亲近",
    "playful": "熟悉/玩闹",
    "flirty": "暧昧",
    "vulnerable": "暴露脆弱或私密信息",
    "boundary": "表达边界/距离",
}

DIRECTION_NAMES = {
    "maintain": "保持当前互动",
    "deepen": "深入当前话题",
    "personalize": "转向个人生活/感受",
    "escalate": "提高互动亲密程度",
    "meetup": "向现实见面/活动推进",
    "play": "保持轻松玩笑",
    "change": "换一个话题",
    "deescalate": "降低互动强度",
    "end": "结束聊天",
    "unclear": "无法判断",
}

EMOTION_NAMES = {
    "happy": "开心",
    "warm": "温暖 / 亲近",
    "neutral": "中性",
    "curious": "好奇",
    "hopeful": "期待",
    "sad": "难过",
    "disappointed": "失望",
    "annoyed": "烦躁",
    "angry": "生气",
    "anxious": "焦虑 / 不安",
    "mixed": "混合情绪",
    "unclear": "暂时无法确定",
}

SCORE_DIMS = {
    "initiative": (
        "主动性：TA 是否在主动推动这段关系/对话，而不仅仅是在回应你。"
        "考虑：主动发起话题、主动提问、主动分享、主动延续、主动提出见面、主动重新开启聊天。"
    ),
    "engagement": (
        "投入度：TA 在这次互动中投入了多少。"
        "考虑：回复是否有内容、是否回答完整、是否追问、是否延续话题、是否提供新信息、是否对你的内容表现出兴趣。"
        "注意：不要简单用字数长短判断投入度。"
    ),
    "warmth": (
        "温度：互动的亲切程度。"
        "考虑：语气、表达方式、情绪回应、玩笑、积极反馈、对你的回应是否有温度。"
    ),
    "intimacy": (
        "亲密程度：这段聊天是否出现了比普通朋友聊天更私人、更深入的内容。"
        "普通信息→低；个人经历→中；个人感受→中高；脆弱/秘密→高；关系话题→高。"
    ),
    "flirtiness": (
        "暧昧程度：语言行为中的暧昧程度（不是判断 TA 喜不喜欢你）。"
        "普通聊天→很低；轻微调侃→偏低；明显特殊关注→中等；暧昧表达→偏高；明显调情→很高。"
    ),
    "vulnerability": (
        "暴露程度：TA 有没有主动暴露自己（脆弱、压力、私密信息、行踪、看法）。"
        "例如'其实我最近压力挺大'远强于'今天好累'。"
    ),
    "attention_toward_user": (
        "对你的关注程度：TA 的注意力是否落在你本人身上。"
        "泛泛聊天→低；问你的事情→中；记得你的细节→中高；主动追踪你的近况→高；主动关心你的情绪→很高。"
    ),
}


def _scale_criteria(dim_desc: str):
    """生成 10 级 Score criteria（0-9，SDK 上限 10 级）。展示时映射为 0-100。"""
    return [
        f"0分：完全没有。{dim_desc}方面没有任何表现。",
        "1分：极弱，几乎察觉不到。",
        "2分：很弱，仅有微弱迹象。",
        "3分：偏弱。",
        "4分：略低于中等。",
        "5分：中等，普通聊天常见水平。",
        "6分：略高于中等。",
        "7分：偏强，有明确表现。",
        "8分：强，多处明确表现。",
        f"9分：极强。{dim_desc}方面表现极其突出、毋庸置疑。",
    ]


def build_questions():
    """构建 Jev questions 字典。每次调用返回全新实例，避免状态污染。"""
    questions = {
        # ① 表层行为 Intent
        "intent": Choice(
            instructions="判断发送者在这段对话中表面行为上在做什么（TA 在做什么？）。必须结合上下文选最符合的一个。",
            criteria={
                "answer": "回答你之前提出的问题",
                "ask": "向你提出问题（信息、确认、反问）",
                "share": "主动分享信息、近况或自己的事",
                "react": "对你的内容做纯粹的反应（笑、惊讶、附和）",
                "continue": "主动延续当前话题（追问、接话、展开）",
                "change_topic": "主动切换到另一个话题",
                "close": "试图结束当前对话（告别、收尾、去忙）",
                "avoid": "回避当前问题或话题（不接、绕开、敷衍）",
            },
        ),
        # ② 核心聊天动机 Motivation
        "motivation": Choice(
            instructions="判断发送者这句话背后的核心聊天动机（TA 为什么这么说？）。必须结合上下文选最符合的一个；证据不足必须选 unclear，不要猜。",
            criteria={
                "information": "获取信息（想了解某件事或你的情况）",
                "conversation": "寻找/维持聊天本身（想聊、想有人陪聊）",
                "attention": "获得你的注意（希望你关注、回应、在意）",
                "connection": "拉近彼此关系（增加熟悉感和联结）",
                "self_expression": "表达自己、分享自己的生活感受",
                "emotional_support": "寻求安慰、理解或情绪支持",
                "validation": "寻求认可、肯定或夸奖",
                "playfulness": "玩笑、调侃、制造轻松氛围",
                "flirting": "暧昧、调情、制造张力",
                "testing": "试探你的态度、反应或你在乎程度",
                "care": "表达关心、照顾你的状态",
                "planning": "推进现实中的见面或共同活动",
                "ending": "礼貌地结束互动",
                "avoidance": "回避某个话题或互动",
                "unclear": "证据不足，无法可靠判断",
            },
        ),
        # ③ 关系信号 Relationship Signal
        "relationship_signal": Choice(
            instructions="判断这句话透露了什么关系层面的信息（这句话透露了什么关系信息？）。",
            criteria={
                "neutral": "普通社交，无明显关系信号",
                "friendly": "友好、善意",
                "personal": "比普通聊天更私人（涉及个人生活细节）",
                "emotionally_close": "情绪上的亲近、信任",
                "playful": "熟悉、玩闹、可开玩笑",
                "flirty": "暧昧、带张力",
                "vulnerable": "暴露脆弱或私密信息",
                "boundary": "表达边界、距离或拒绝",
            },
        ),
        # ④ 对话方向 Conversation Direction
        "conversation_direction": Choice(
            instructions="判断发送者想让聊天往哪里走（TA 想让聊天往哪里走？）。结合上下文判断。",
            criteria={
                "maintain": "保持当前互动节奏",
                "deepen": "深入当前话题（追问、展开）",
                "personalize": "转向个人生活或感受",
                "escalate": "提高互动亲密程度",
                "meetup": "向现实见面或共同活动推进",
                "play": "保持轻松玩笑氛围",
                "change": "换一个话题",
                "deescalate": "降低互动强度、降温",
                "end": "结束聊天",
                "unclear": "无法判断",
            },
        ),
        # 情绪（辅助维度）
        "emotion": Choice(
            instructions="判断发送者在这段聊天中最主要的情绪状态。",
            criteria={
                "happy": "开心、兴奋、轻松",
                "warm": "温柔、亲近、在乎",
                "neutral": "基本中性，没有明显情绪",
                "curious": "好奇、期待得到信息",
                "hopeful": "期待、希望对方做出积极回应",
                "sad": "难过、失落、沮丧",
                "disappointed": "失望、落差感",
                "annoyed": "烦躁、不耐烦",
                "angry": "明显生气或愤怒",
                "anxious": "焦虑、不安、担心",
                "mixed": "存在明显的混合情绪",
                "unclear": "无法可靠判断",
            },
        ),
    }

    # ⑤-⑪ 七个 0-100 Score
    for name, desc in SCORE_DIMS.items():
        questions[name] = Score(
            instructions=f"评估：{desc}必须结合上下文打分。",
            criteria=_scale_criteria(desc.split("：", 1)[0]),
        )

    return questions


# ============================================================
# 答案读取
# ============================================================

def _get_answer(response, name):
    try:
        return response.answers[name]
    except Exception:
        return None


def _get_choice(response, name):
    answer = _get_answer(response, name)
    if answer is None:
        return "未知", 0.0
    choice = getattr(answer, "choice", None)
    confidence = getattr(answer, "confidence", 0.0) or 0.0
    return (choice if choice else "未知"), float(confidence)


def _get_choice_dist(response, name, names_map, top=3):
    """提取该 Choice 的概率分布，按概率降序取前 top 个。

    返回 [{"key", "label", "probability"}]，probability 为 0-1。
    """
    answer = _get_answer(response, name)
    if answer is None:
        return []
    probs = getattr(answer, "probabilities", None) or {}
    rows = [
        {
            "key": key,
            "label": names_map.get(key, key),
            "probability": float(prob),
        }
        for key, prob in probs.items()
    ]
    rows.sort(key=lambda r: r["probability"], reverse=True)
    return rows[:top]


def _get_score(response, name):
    answer = _get_answer(response, name)
    if answer is None:
        return None
    value = getattr(answer, "score", None)
    return None if value is None else float(value)


def _to_100(value):
    """10 级 Score（0-9）→ 0-100 整数。"""
    if value is None:
        return None
    return int(round(max(0.0, min(9.0, value)) * 100 / 9))


def parse_jev_response(response):
    """把 TypeSafeClient 响应对象转成可 JSON 序列化的 dict（MVP v1 结构）。"""
    intent, intent_conf = _get_choice(response, "intent")
    motivation, motivation_conf = _get_choice(response, "motivation")
    relationship, relationship_conf = _get_choice(response, "relationship_signal")
    direction, direction_conf = _get_choice(response, "conversation_direction")
    emotion, emotion_conf = _get_choice(response, "emotion")

    scores = {}
    for name in SCORE_DIMS:
        scores[name] = {"value": _to_100(_get_score(response, name))}

    # 顶层置信度 = 4 个核心 Choice 置信度的平均值
    confs = [intent_conf, motivation_conf, relationship_conf, direction_conf]
    confidence = round(sum(confs) / len(confs), 3)

    return {
        "intent": {
            "key": intent,
            "label": INTENT_NAMES.get(intent, intent),
            "confidence": intent_conf,
            "probabilities": _get_choice_dist(response, "intent", INTENT_NAMES),
        },
        "motivation": {
            "key": motivation,
            "label": MOTIVATION_NAMES.get(motivation, motivation),
            "confidence": motivation_conf,
            "probabilities": _get_choice_dist(response, "motivation", MOTIVATION_NAMES),
        },
        "relationship_signal": {
            "key": relationship,
            "label": RELATIONSHIP_NAMES.get(relationship, relationship),
            "confidence": relationship_conf,
            "probabilities": _get_choice_dist(
                response, "relationship_signal", RELATIONSHIP_NAMES
            ),
        },
        "conversation_direction": {
            "key": direction,
            "label": DIRECTION_NAMES.get(direction, direction),
            "confidence": direction_conf,
            "probabilities": _get_choice_dist(
                response, "conversation_direction", DIRECTION_NAMES
            ),
        },
        "emotion": {
            "key": emotion,
            "label": EMOTION_NAMES.get(emotion, emotion),
            "confidence": emotion_conf,
        },
        "scores": scores,
        "confidence": confidence,
    }
