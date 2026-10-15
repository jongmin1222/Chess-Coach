"""로컬 LLM(Ollama) 연동과 프롬프트 생성. python-chess에 의존하지 않습니다."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Optional

from .errors import LLMError
from .rag import has_content

# 목적격 조사까지 붙인 표기 ("폰을", "나이트를" ...)
PIECE_KO_OBJ = {
    "pawn": "폰을",
    "knight": "나이트를",
    "bishop": "비숍을",
    "rook": "룩을",
    "queen": "퀸을",
}

LEVELS = {
    "beginner": "체스를 막 배운 초보자(레이팅 약 800 이하)입니다. 전문용어는 쉬운 말로 풀어 쓰고, 한 장면에서 교훈은 한 가지만 전달하세요.",
    "intermediate": "중급자(레이팅 약 800~1600)입니다. 포크·핀 같은 기본 전술 용어는 그대로 써도 됩니다.",
    "advanced": "상급자(레이팅 1600 이상)입니다. 군더더기 없이 간결하고 전문적으로 설명하세요.",
}

SYSTEM_PROMPT = """당신은 친절한 체스 코치입니다. Stockfish 엔진이 분석한 결과(JSON)를 바탕으로 사용자의 게임 복기 피드백을 작성합니다.

반드시 지킬 규칙:
1. 평가값, 최선수, 수순은 JSON에 있는 것만 인용하세요. 스스로 수를 평가하거나 JSON에 없는 수순·기물 위치를 만들어내지 마세요.
2. `hints`에 근거가 있으면 그것을 바탕으로 이유를 설명하세요. 근거가 없으면 이유를 지어내지 말고 "엔진은 이 수를 더 높게 평가했습니다" 정도로만 말하세요.
3. 핵심 장면 위주로 쓰고, 장면마다 (무슨 일이 있었는지 / 더 좋았던 수 / 배울 점)을 짧게 정리하세요.
4. 반드시 한국어로만 답하세요. 중국어·일본어·한자를 섞지 마세요. 수는 대수기보(SAN) 그대로 표기하세요. (예: Nf3, Qxe5)
5. 마지막에 다음 게임에서 의식할 점을 1~2가지 제안하세요.
6. 비난하지 말고 격려하는 톤을 유지하세요."""


RAG_RULES = """참고 자료(`knowledge`)와 `position_facts`가 함께 제공되면 아래 규칙도 지켜야 합니다.
7. `knowledge`는 체스 서적·노트에서 가져온 일반 원칙이며 엔진이 평가한 사실이 아닙니다. 이번 수가 틀린 직접적인 이유로 단정하지 마세요. `hints`나 `position_facts`가 뒷받침할 때만 "이 장면에서는 ~ 때문"이라고 말하고, 그렇지 않으면 "일반적으로 ~라고 알려져 있습니다"처럼 일반 원칙임을 밝히세요. `position_facts`는 코드가 직접 확인한 사실이므로 근거로 써도 됩니다.
8. 장면과 관련 없어 보이는 자료는 쓰지 마세요. 모든 자료를 억지로 인용할 필요는 없습니다.
9. 참고한 자료는 해당 문장 끝에 [K1] 형식의 번호로 표시하세요. 자료의 문장을 그대로 베끼지 말고 짧게 요약해서 쓰세요.
10. `knowledge`에 없는 오프닝 이름이나 수순을 만들지 마세요. 오프닝 이름은 `opening.family`에 있는 것만 쓰고, 없으면 오프닝 이름을 언급하지 마세요.
11. `knowledge`에 나오는 수순(예: 3.Bc4)은 그 오프닝의 일반 설명일 뿐 이 게임의 수순이 아닐 수 있습니다. 이 게임의 수는 `opening.line`과 `critical_moments`만 근거로 하세요."""


def describe_tag(tag: str) -> str:
    """분석 태그를 LLM이 그대로 인용할 수 있는 한국어 힌트로 바꾼다."""
    if tag == "missed_mate":
        return "강제 체크메이트가 가능했는데 이 수로 놓쳤습니다."
    if tag == "allowed_mate":
        return "이 수 때문에 상대에게 강제 체크메이트를 허용했습니다."
    if tag == "hung_moved_piece":
        return "방금 움직인 기물이 그대로 잡혀버렸습니다."
    for prefix, template in (
        ("missed_capture_of_", "엔진의 최선수는 상대 {p} 잡는 수였지만 놓쳤습니다."),
        ("allowed_capture_of_", "이 수 뒤에 상대가 내 {p} 잡을 수 있게 됐습니다."),
    ):
        if tag.startswith(prefix):
            piece = tag[len(prefix):]
            return template.format(p=PIECE_KO_OBJ.get(piece, piece))
    return tag


def _compact_moment(m: dict) -> dict:
    return {
        "label": m["label"],
        "phase": m["phase"],
        "played": m["played"],
        "classification": m["classification"],
        "win_chance_before_pct": m["win_before"],
        "win_chance_after_pct": m["win_after"],
        "eval_before": m["eval_before"],
        "eval_after": m["eval_after"],
        "engine_best_move": m["best_move"],
        "engine_best_line": m["best_line"],
        "opponent_best_reply_after_played_move": m["refutation"],
        "hints": [describe_tag(t) for t in m["tags"]],
        "turning_point": m["turning_point"],
    }


def build_messages(report: dict, level: str = "intermediate", knowledge: Optional[dict] = None) -> list[dict]:
    if level not in LEVELS:
        raise ValueError(f"level must be one of {list(LEVELS)}")
    side = report.get("analyzed_side")
    side_ko = {"white": "백", "black": "흑"}.get(side, "양쪽 모두")
    use_rag = has_content(knowledge)
    facts = (knowledge or {}).get("facts", {}) if use_rag else {}
    refs = (knowledge or {}).get("moments", {}) if use_rag else {}
    moments = []
    for m in report.get("critical_moments", []):
        cm = _compact_moment(m)
        if facts.get(m["label"]):
            cm["position_facts"] = facts[m["label"]]
        if refs.get(m["label"]):
            cm["related_knowledge"] = refs[m["label"]]
        moments.append(cm)
    payload: dict = {"game": report.get("game", {})}
    if use_rag and knowledge.get("opening"):
        payload["opening"] = knowledge["opening"]
        if knowledge.get("game"):
            payload["opening"] = {**knowledge["opening"], "knowledge": knowledge["game"]}
    payload.update(
        {
            "analyzed_side": side,
            "summary": report.get("summary", {}),
            "critical_moments": moments,
        }
    )
    if use_rag and knowledge.get("items"):
        payload["knowledge"] = [
            {"id": i["id"], "title": i["title"], "source": i["source"], "text": i["text"]}
            for i in knowledge["items"]
        ]
    user = (
        f"사용자 수준: {LEVELS[level]}\n"
        f"분석 대상: {side_ko}\n"
        "참고: win_chance는 그 수를 둔 쪽 기준 승률(%)이고, eval은 백 기준 평가값입니다(+는 백 우세, M3는 3수 내 메이트).\n"
        "critical_moments가 비어 있다면 큰 실수가 없었던 게임이니 잘한 점 위주로 짧게 써주세요.\n\n"
        "다음 형식으로 답하세요: `## 총평`, `## 핵심 장면`, `## 다음 게임을 위한 제안`\n"
        + ("참고 자료를 쓴 문장 끝에는 `knowledge`의 id를 [K1]처럼 표시하세요.\n" if use_rag else "")
        + "\n"
        "분석 결과(JSON):\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT + ("\n" + RAG_RULES if use_rag else "")},
        {"role": "user", "content": user},
    ]


def ollama_chat(
    messages: list[dict],
    model: str,
    host: str = "http://localhost:11434",
    *,
    timeout: float = 600.0,
    temperature: float = 0.3,
    num_ctx: int = 8192,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 404:
            raise LLMError(
                f"Ollama에 모델 '{model}'이(가) 없습니다. 먼저 `ollama pull {model}` 을 실행하세요."
            ) from e
        raise LLMError(f"Ollama 오류 (HTTP {e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(
            f"Ollama 서버({host})에 연결할 수 없습니다. Ollama가 설치·실행 중인지 확인하세요. ({e.reason})"
        ) from e

    text = (data.get("message") or {}).get("content", "")
    # 일부 모델(예: qwen3)이 출력하는 <think> 블록 제거
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


_REF_GROUP_RE = re.compile(r"[\[(（]\s*(K\d+(?:\s*[,，、/]\s*K\d+)*)\s*[\])）]")


def finalize_feedback(text: str, knowledge: Optional[dict]) -> str:
    """LLM이 붙인 [K1] 표기를 [1] 번호로 바꾸고, 실제로 인용된 자료만 끝에 '참고 자료'로 덧붙인다.

    출처 목록은 모델이 쓰지 않고 코드가 만든다. 존재하지 않는 K 번호는 지운다.
    """
    items = {i["id"]: i for i in (knowledge or {}).get("items", [])}
    if not items:
        return text
    order: list[str] = []

    def repl(m: "re.Match[str]") -> str:
        nums = []
        for kid in re.findall(r"K\d+", m.group(1)):
            if kid not in items:
                continue
            if kid not in order:
                order.append(kid)
            nums.append(order.index(kid) + 1)
        return "".join(f"[{n}]" for n in nums)

    out = _REF_GROUP_RE.sub(repl, text)
    if not order:
        return out
    lines = ["", "## 참고 자료"]
    for n, kid in enumerate(order, start=1):
        it = items[kid]
        label = it["source"] if it["title"] in it["source"] else f"{it['source']} — {it['title']}"
        lines.append(f"[{n}] {label}")
    return out.rstrip() + "\n" + "\n".join(lines)
