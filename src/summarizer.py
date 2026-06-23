import json
from dataclasses import dataclass

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from src.config import CONTENT_CARDS, GEMINI_API_KEY, GEMINI_TEXT_MODEL


def _is_retryable(exc: BaseException) -> bool:
    """일시적 에러만 재시도. 500/503 과 분당(RPM) 429 는 재시도하지만,
    일일 한도(RPD) 소진 429 는 재시도해도 회복 안 되므로 즉시 실패시킨다
    (재시도하면 남은 quota 만 더 까먹음)."""
    if not isinstance(exc, (APIError, ClientError)):
        return False

    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    msg = str(exc).lower()
    is_429 = code == 429 or "429" in msg or "resource_exhausted" in msg

    if is_429:
        # "...RequestsPerDay..." 류는 일일 한도 → 재시도 무의미
        compact = msg.replace(" ", "")
        if "perday" in compact:
            return False
        return True  # 분당 한도 등 — 잠시 뒤 회복됨
    if code in (500, 503):
        return True
    return any(kw in msg for kw in ("unavailable", "503", "500"))


@dataclass
class ContentCard:
    section: str   # 짧은 라벨 (예: "핵심", "배경", "기술", "의미", "전망")
    title: str     # 카드 헤드라인 (28자 이내)
    body: str      # 본문 (220~280자, \n\n 으로 단락 분리)


@dataclass
class CardCopy:
    headline: str
    subheadline: str
    cards: list[ContentCard]
    hashtags: list[str]


class NonRelevantArticleError(Exception):
    """기사가 AI 반도체 회사 딥엑스(DeepX)와 무관해 게이트에서 reject 한 경우."""


SYSTEM_PROMPT = f"""너는 AI 반도체 스타트업 **딥엑스(DeepX)** 관련 뉴스를 한국어 인스타그램
카드뉴스로 정리하는 테크 에디터다.

## 딥엑스가 누구인가 (판단 기준)
- 한국의 AI 반도체(NPU, Neural Processing Unit) 설계 스타트업. 대표는 김녹원.
- 엣지(on-device) AI에 특화된 NPU 칩(예: DX-M1 등)을 만든다. 클라우드가 아니라
  기기 자체에서 AI를 돌리는 저전력 추론용 칩이 주력.
- 키워드: NPU, 엣지 AI, 온디바이스, 추론(inference), 팹리스, 투자/시리즈, 양산, 고객사.

## 관련성 게이트 (반드시 먼저 판단)
입력 기사가 **위의 AI 반도체 회사 딥엑스(DeepX)에 관한 실질적인 내용**이 아니면
(동명이인·타사 'DeepX'·단순 한 줄 언급뿐인 기사 등) **반드시 다음 JSON만 출력하고 종료**:
```
{{"skip": true, "reason": "이 기사는 AI 반도체 기업 딥엑스(DeepX)에 관한 내용이 아닙니다"}}
```
헤드라인/카드를 절대 만들지 말 것. 관련 기사면 아래 정상 스키마로 출력.

## 톤 & 독자
- **전문·정보형.** 정확성과 신뢰가 최우선. 과장·낚시성 표현 금지.
- 독자: 반도체/AI/스타트업/투자에 관심 있는 일반 테크 독자. 업계 종사자는 아닐 수 있음.
- 전문용어(NPU, 엣지 AI, 팹리스, TOPS 등)는 처음 1회만 괄호로 짧게 풀이.
  예: "NPU(AI 연산 전용 칩)", "팹리스(설계만 하고 생산은 위탁하는 반도체 회사)".
- 차분하고 명료한 문체. "~했다", "~이다", "~로 보인다" 같은 정보 전달형 종결.

## 출력 스키마 (JSON만, 코드블럭 금지)
```
{{
  "headline": "타이틀 카드 헤드라인 (22자 이내). 핵심 사실을 명료하게. 회사명/숫자 등 핵심 1군데만 **로 강조",
  "subheadline": "헤드라인 보조 (30자 이내, 누가/무엇/언제 요약)",
  "cards": [
    {{
      "section": "섹션 라벨 (5자 이내: 핵심, 배경, 기술, 의미, 전망 등)",
      "title": "카드 헤드라인 (28자 이내, 두 줄까지)",
      "body": "본문 (220~280자, 4~6문장. \\n\\n 으로 2~3 단락 분리. 핵심 1~2군데만 **로 강조)"
    }}
    ... 정확히 {CONTENT_CARDS}개
  ],
  "hashtags": ["#딥엑스", "#DeepX", "#AI반도체", "#NPU", ...]
}}
```

## 5장 흐름 (정보형 구성)
1. **핵심** — 무슨 일이 있었나. 기사의 한 줄 요약(누가·무엇을·언제).
2. **배경** — 왜 지금 이 소식이 나왔나. 맥락·이전 상황.
3. **기술/제품** — 딥엑스의 NPU·제품·기술이 어떻게 관련되는지. 어려운 개념은 풀어서.
4. **의미** — 시장·산업·경쟁(엔비디아 등)·고객·투자 관점에서 왜 중요한가.
5. **전망** — 앞으로의 계획·과제·한국 반도체 생태계에 주는 시사점.

## 마크업(`**...**`) 규칙
- **허용 필드**: `headline`, `cards[*].body` 만. 렌더 시 별표는 안 보이고 그 부분만 색이 다름.
- **금지 필드**: `subheadline`, `cards[*].section`, `cards[*].title`, `hashtags`.
- 강조 대상: 회사명·제품명·숫자/스케일·핵심 결과. 카드당 1~2군데까지만.

## 출력 규칙
- 반드시 JSON만. 마크다운 코드블럭 금지.
- cards 는 정확히 {CONTENT_CARDS}개.
- 각 body 는 **반드시 220~280자**, **\\n\\n 으로 2~3 단락 분리**. 한 덩어리로 쓰지 말 것.
- 기사에 없는 사실을 지어내지 말 것. 불확실하면 단정하지 말고 "~로 알려졌다" 식으로.
- hashtags 는 6~8개. 반드시 "#딥엑스", "#DeepX" 를 포함.
"""


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=10, min=10, max=60),
    before_sleep=lambda rs: print(
        f"[summarizer] Gemini API 일시 에러 (시도 {rs.attempt_number}/4), "
        f"{rs.next_action.sleep}초 후 재시도..."
    ),
    reraise=True,
)
def summarize(title: str, body: str, source: str) -> CardCopy:
    client = genai.Client(api_key=GEMINI_API_KEY)

    user_input = f"[출처] {source}\n[제목] {title}\n[본문]\n{body}"

    response = client.models.generate_content(
        model=GEMINI_TEXT_MODEL,
        contents=user_input,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.5,
        ),
    )

    data = json.loads(response.text)

    if data.get("skip") is True:
        raise NonRelevantArticleError(data.get("reason", "딥엑스 무관 기사"))

    def _strip_md(s: str) -> str:
        return s.replace("**", "").replace("__", "")

    cards = [
        ContentCard(
            section=_strip_md(c["section"]),
            title=_strip_md(c["title"]),
            body=c["body"],
        )
        for c in data["cards"][:CONTENT_CARDS]
    ]
    return CardCopy(
        headline=data["headline"],
        subheadline=_strip_md(data["subheadline"]),
        cards=cards,
        hashtags=[_strip_md(h) for h in data.get("hashtags", [])],
    )
