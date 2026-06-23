# insta-deepx

AI 반도체 스타트업 딥엑스(DeepX) 관련 기사를 Naver 검색으로 수집 → 본문·이미지 추출 →
Gemini로 한국어 요약 → PIL로 1080×1080 카드뉴스 합성 → Cloudinary 업로드 →
Instagram Graph API 캐러셀 게시하는 자동화 봇. `insta-cardnews-bot`에서 파생.

## Architecture

```
Naver 뉴스 검색 API ("딥엑스" 등 여러 쿼리)
  → src/crawler.py        (requests, posted.json + 제목 정규화로 중복 방지)
  → src/background.py     (trafilatura로 본문 + og:image 추출)
  → src/summarizer.py     (Gemini 2.5 Flash, 전문·정보형 요약 + 딥엑스 관련성 게이트)
  → src/background.py     (이미지 있으면 커버에 사용, 없으면 mesh 배경 직접 생성)
  → src/card_composer.py  (PIL, 1080×1080 카드 합성)
  → src/uploader.py       (Cloudinary → 공개 URL → Instagram API w/ Instagram Login)
  → src/main.py           (오케스트레이션)
```

GitHub Actions `workflow_dispatch`(`.github/workflows/daily-post.yml`)를 cron-job.org가
트리거하는 구조.

## insta-cardnews-bot 과의 핵심 차이

1. **뉴스 소스**: 일반 IT RSS → **Naver 검색 API**. `originallink`로 실제 언론사 URL을
   직접 얻어 이미지/본문 스크래핑이 가능하다.
2. **이미지**: AI 생성(Pollinations) 제거. `image_generator.py` → **`background.py`**.
   - 기사 og:image 가 있으면 정사각 crop 해서 **타이틀 카드 커버**로 사용.
   - 본문/아웃트로 카드는 (사진 위 텍스트 가독성 때문에) 그 사진의 대표색으로 만든
     **mesh 그라데이션 배경**을 쓴다.
   - 이미지가 아예 없으면 브랜드 팔레트로 mesh 배경 생성.
   - mesh = 어두운 대각 그라데이션 + 팔레트 색 blob 여러 개 + 강한 블러 + 비네팅 + 그레인.
     `seed`(기사 URL 해시)로 매번 다른 구도. **모두 PIL only, AI 없음.**
3. **요약 톤**: 일반 대중용 클릭베이트 → **전문·정보형**. 정확성 우선, 과장 금지.
   summarizer 프롬프트에 **딥엑스 관련성 게이트**가 있어 동명이인/타사/단순 언급 기사는
   `{"skip": true}`로 거른다.
4. **시크릿**: 원본의 git-crypt 제거. 로컬 `.env`(gitignore) + GitHub Actions Secrets.

## 카드 배경 처리 (card_composer)

생성된 mesh 배경은 **어둡다**. 카드별 처리:
- 타이틀: 커버 이미지(사진 or mesh) + 블러 + 어둡게 + 상하단 그라디언트 → 흰 텍스트.
- 본문: `_apply_bg_light()` 로 흰색 오버레이(0.74) → 밝은 틴트 배경 + 어두운 텍스트.
  밝은 배경에서는 밝은 시안이 안 보이므로 마크업 강조색을 `BRAND_ACCENT_INK`(진한 블루)로.
- 아웃트로: `_apply_bg_dark()` → 어두운 배경 + 흰/시안 텍스트.

## 중복 방지 ("늘 새로운 기사")

1. `output/posted.json` — 게시 완료한 `originallink` 집합. crawler가 필터.
2. 제목 정규화(공백·특수문자 제거·소문자) 키로 같은 사건의 타 언론사 중복 보도 제외.
3. GitHub Actions `actions/cache`로 `posted.json` 영속화.
4. 관련성 게이트가 reject 한 기사도 `mark_posted` 하여 재시도 방지.

## Commands

```bash
./setup.sh                          # venv + deps + 카드 합성 테스트
source .venv/bin/activate
python -m src.card_composer         # 카드 디자인만 (API 불필요)
python -m src.background <URL>      # 기사 이미지/배경 추출 테스트
python -m src.crawler               # Naver 검색 결과 확인 (NAVER_* 필요)
STAGE=compose python -m src.main    # 검색→요약→카드
python -m src.main                  # 전체 (게시까지)
```

## Gotchas

- Naver 뉴스 검색 API는 **이미지를 안 준다**. og:image는 `background.py`가 기사 페이지를
  직접 fetch 해서 추출한다. 일부 언론사는 스크래핑을 막거나 og:image가 없을 수 있고,
  그 경우 자동으로 생성 mesh 배경으로 폴백한다.
- og:image 가 로고/아이콘처럼 작으면(`_MIN_IMAGE_DIM` 미만) 사진으로 안 쓰고 폴백.
- **인스타 연동 방식**: Instagram API with **Instagram Login** (Facebook 페이지 불필요).
  uploader 는 `graph.instagram.com/v23.0/{IG_USER_ID}/media(_publish)` 호출. `INSTAGRAM_BUSINESS_ID`
  는 `me?fields=user_id` 로 얻는 IG 프로페셔널 계정 ID. (구버전 Facebook Login 방식 아님)
- **토큰**: 대시보드 'Generate token' = 60일 장기 토큰. token_manager 가 만료 임박 시
  `ig_refresh_token` 으로 자동 갱신하고 `output/ig_token.json` 에 저장. 워크플로우가 이 파일을
  캐시하므로 60일 안에 한 번이라도 실행되면 토큰이 무한 연장됨 (FACEBOOK_APP_* 불필요).
- Instagram API는 이미지 URL이 24시간 내 만료되면 안 됨 — Cloudinary `secure_url`은 영구라 OK.
- `instagrapi` 등 비공식 라이브러리는 계정 정지 위험. 공식 API만 사용.
- Gemini 무료 티어 분당 제한 주의 (1회 1기사라 보통 문제 없음).
- 브랜드명/핸들/로고는 `config.py`/`assets/logo.png`의 플레이스홀더 — 운영 계정에 맞게 교체.
