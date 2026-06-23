import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable

import requests

from src.config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_DISPLAY,
    NAVER_SEARCH_QUERIES,
    POSTED_LOG,
)

NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Article:
    title: str
    url: str           # originallink — 실제 언론사 URL (스크래핑/카드 출처)
    summary: str       # Naver description (본문 추출 실패 시 폴백)
    source: str        # 언론사 도메인
    published: datetime


def _clean(text: str) -> str:
    """Naver 응답의 <b> 태그 / HTML 엔티티 제거."""
    return unescape(_TAG_RE.sub("", text or "")).strip()


def _normalize_title(title: str) -> str:
    """제목 정규화 — 같은 사건의 타 언론사 중복 보도를 걸러내기 위한 키."""
    t = _clean(title).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", t)


def _domain(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else url


def _load_posted_urls() -> set[str]:
    if not POSTED_LOG.exists():
        return set()
    return set(json.loads(POSTED_LOG.read_text()))


def _save_posted_urls(urls: Iterable[str]) -> None:
    POSTED_LOG.write_text(json.dumps(sorted(urls), ensure_ascii=False, indent=2))


def mark_posted(url: str) -> None:
    posted = _load_posted_urls()
    posted.add(url)
    _save_posted_urls(posted)


def _search_naver(query: str) -> list[dict]:
    """Naver 뉴스 검색 API 호출. 키 없거나 실패 시 빈 리스트."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("[crawler] ⚠️  NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
        return []
    try:
        resp = requests.get(
            NAVER_NEWS_ENDPOINT,
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={"query": query, "display": NAVER_DISPLAY, "sort": "date"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except requests.RequestException as e:
        print(f"[crawler] Naver 검색 실패 (query={query!r}): {e}")
        return []


def fetch_recent_articles() -> list[Article]:
    """여러 검색어로 딥엑스 기사를 모아 중복 제거 후 최신순 반환.

    중복 방지 2단계:
      1) 이미 게시한 originallink (posted.json) 제외
      2) 제목 정규화 키로 같은 사건의 중복 보도 제외
    """
    posted = _load_posted_urls()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    articles: list[Article] = []

    for query in NAVER_SEARCH_QUERIES:
        for item in _search_naver(query):
            # originallink 가 비면 link(네이버 redirect)로 폴백
            url = (item.get("originallink") or item.get("link") or "").strip()
            if not url or url in posted or url in seen_urls:
                continue

            title = _clean(item.get("title", ""))
            if not title:
                continue
            title_key = _normalize_title(title)
            if title_key in seen_titles:
                continue

            pub_raw = item.get("pubDate", "")
            try:
                published = parsedate_to_datetime(pub_raw)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                published = datetime.now(timezone.utc)

            seen_urls.add(url)
            seen_titles.add(title_key)
            articles.append(
                Article(
                    title=title,
                    url=url,
                    summary=_clean(item.get("description", "")),
                    source=_domain(url),
                    published=published,
                )
            )

    articles.sort(key=lambda a: a.published, reverse=True)
    return articles


if __name__ == "__main__":
    found = fetch_recent_articles()
    print(f"[crawler] 새 기사 {len(found)}건")
    for a in found[:10]:
        print(f"  - {a.published:%Y-%m-%d} | {a.source} | {a.title}")
        print(f"    {a.url}")
