# -*- coding: utf-8 -*-
"""临时端到端测试脚本（验证后可删）。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BODY = {
    "messages": [
        {"sender": "A", "text": "我又把钥匙忘家里了"},
        {"sender": "B", "text": "哈哈你也太笨了吧"},
        {"sender": "B", "text": "等着，我给你送过去"},
        {"sender": "A", "text": "那多不好意思"},
        {"sender": "B", "text": "没事，顺便我还能见你一面"},
    ],
    "other_sender": "B",
}

req = urllib.request.Request(
    "http://localhost:8006/api/analyze",
    data=json.dumps(BODY, ensure_ascii=False).encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=180) as resp:
    data = json.loads(resp.read().decode("utf-8"))

d = data.get("dashboard")
print("dashboard is None:", d is None)
if d:
    print("overall:", d["overall_direction"], "| motiv:", d["dominant_motivation"])
    print("scores_avg:", {k: v["avg"] for k, v in d["scores"].items()})
    print("hint:", d["strategy_hint"])
    print("reply_strategy:", d["reply_strategy"])
    print("replies:", d["reply_suggestions"])
    print("reply_error:", d["reply_error"])
    print("evidence n:", len(d["evidence"]))
for r in data["results"]:
    a = r["analysis"]
    if "error" in a:
        print("msg:", r["text"], "-> ERROR:", a["error"])
    else:
        print(
            "msg:", r["text"],
            "| intent:", a["intent"]["label"],
            "| motiv:", a["motivation"]["label"],
            "| dir:", a["conversation_direction"]["label"],
            "| initiative:", a["scores"]["initiative"]["value"],
            "| evidence:", [e["label"] for e in a["evidence"]],
        )
