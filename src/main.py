import os
import sys

from src.background import build_backgrounds, fetch_article
from src.card_composer import compose_all
from src.config import ARTICLES_PER_RUN, INSTAGRAM_HANDLE
from src.crawler import fetch_recent_articles, mark_posted
from src.summarizer import ContentCard, NonRelevantArticleError, summarize
from src.uploader import publish_carousel, upload_all_to_cloudinary


VALID_STAGES = ("compose", "upload", "full")

BRAND_TAG = "#딥엑스"


def _strip_md(s: str) -> str:
    return s.replace("**", "").replace("__", "")


def build_caption(
    headline: str,
    subheadline: str,
    source: str,
    cards: list[ContentCard],
    hashtags: list[str],
    url: str,
) -> str:
    body_parts = []
    for c in cards:
        body_parts.append(f"▸ {_strip_md(c.section)}\n{_strip_md(c.body)}")
    body = "\n\n".join(body_parts)

    tag_list = [BRAND_TAG] + [t for t in hashtags if t != BRAND_TAG]
    tags = " ".join(tag_list)

    return (
        f"{_strip_md(headline)}\n"
        f"{_strip_md(subheadline)}\n\n"
        f"{body}\n\n"
        f"📰 출처: {source}\n"
        f"🔗 {url}\n\n"
        f"🔍 AI 반도체 기업 딥엑스(DeepX) 소식을 카드뉴스로 정리해드려요.\n"
        f"💙 팔로우하면 딥엑스 새 소식을 빠르게 → @{INSTAGRAM_HANDLE}\n\n"
        f"{tags}"
    )


def run(stage: str = "full") -> int:
    articles = fetch_recent_articles()
    if not articles:
        print("[main] 새 기사 없음")
        return 0

    # 게시(full)뿐 아니라 compose/upload 테스트에서도 ARTICLES_PER_RUN 만큼만
    # 처리하고 멈춘다 (그러지 않으면 검색된 기사를 전부 요약해 Gemini 할당량을 태움).
    processed_count = 0
    for article in articles:
        if processed_count >= ARTICLES_PER_RUN:
            break
        print(f"[main] 처리 중: {article.title}")

        # 기사 본문 + 대표 이미지 추출
        body, image = fetch_article(article.url)
        body_for_summary = body or article.summary
        print(f"[main] 본문 {len(body_for_summary)}자, 이미지 {'있음' if image else '없음'}")

        try:
            copy = summarize(article.title, body_for_summary, article.source)
        except NonRelevantArticleError as e:
            print(f"[main] 스킵 (딥엑스 무관): {e}")
            mark_posted(article.url)  # 같은 기사 재시도 방지
            continue
        print(f"[main] 요약 완료: {copy.headline}")

        backgrounds = build_backgrounds(article.url, image)
        print(f"[main] 배경 준비 완료 (source={backgrounds['source']})")

        paths = compose_all(
            backgrounds=backgrounds,
            headline=copy.headline,
            subheadline=copy.subheadline,
            source=article.source,
            cards=copy.cards,
            hashtags=copy.hashtags,
        )
        print(f"[main] 카드 {len(paths)}장 생성 완료 → {paths[0].parent}")

        if stage == "compose":
            print("[main] STAGE=compose → 카드만 생성하고 종료")
            for p in paths:
                print(f"  - {p}")
            processed_count += 1
            continue

        urls = upload_all_to_cloudinary(paths)
        for url in urls:
            print(f"  → {url}")

        if stage == "upload":
            print("[main] STAGE=upload → Cloudinary 업로드까지만. 인스타 게시 스킵")
            processed_count += 1
            continue

        caption = build_caption(
            copy.headline,
            copy.subheadline,
            article.source,
            copy.cards,
            copy.hashtags,
            article.url,
        )
        media_id = publish_carousel(urls, caption)
        print(f"[main] 게시 완료: {media_id}")

        mark_posted(article.url)
        processed_count += 1

    return 0


if __name__ == "__main__":
    stage = os.environ.get("STAGE", "full").lower()
    if stage not in VALID_STAGES:
        print(f"[main] STAGE는 {VALID_STAGES} 중 하나여야 합니다. 현재: {stage!r}")
        sys.exit(1)
    print(f"[main] STAGE={stage}")
    sys.exit(run(stage))
