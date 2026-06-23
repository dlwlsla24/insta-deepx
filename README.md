# insta-deepx

AI 반도체 스타트업 **딥엑스(DeepX)** 관련 기사를 자동으로 요약해 한국어 카드뉴스
(1080×1080 캐러셀)로 인스타그램에 게시하는 봇.

```
Naver 뉴스 검색 → 기사 본문·이미지 추출 → Gemini 요약 → PIL 카드 합성 → Cloudinary → Instagram
```

`insta-cardnews-bot`을 기반으로 하되 3가지가 다르다:

1. **AI 이미지 생성 안 함** — 기사에 있는 대표 이미지(og:image)를 커버로 쓰고,
   이미지가 없으면 PIL로 **세련된 mesh 그라데이션 배경**을 직접 생성한다.
2. **딥엑스 전용** — Naver 검색 API로 "딥엑스" 관련 기사만 모으고, Gemini 관련성
   게이트로 동명이인·타사 'DeepX'·단순 언급 기사를 한 번 더 거른다.
3. **항상 새 기사** — 게시한 기사 URL과 정규화된 제목을 기록해 같은 기사를 다시
   요약하지 않는다.

## Quick start

```bash
# 1. 키 채우기
cp .env.example .env   # 편집기로 키 입력

# 2. 한 줄 셋업 (venv + deps + 카드 합성 테스트)
./setup.sh

# 3. 단계별 실행
source .venv/bin/activate
STAGE=compose python -m src.main   # 검색 + 요약 + 카드 생성까지
STAGE=upload  python -m src.main   # 위 + Cloudinary 업로드까지
STAGE=full    python -m src.main   # 위 + 인스타 게시 (기본값)
```

**STAGE별 필요한 키**:

| STAGE | NAVER_* | GEMINI | CLOUDINARY_* | INSTAGRAM_* |
|-------|:-:|:-:|:-:|:-:|
| `compose` | ✅ | ✅ | ❌ | ❌ |
| `upload` | ✅ | ✅ | ✅ | ❌ |
| `full` | ✅ | ✅ | ✅ | ✅ |

API 호출 없이 카드 디자인만 보려면: `python -m src.card_composer` (샘플 카피 + 생성 배경).
배경 추출만 확인하려면: `python -m src.background <기사URL>`.

## API 키 발급

| 키 | 발급 방법 |
|----|----------|
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | https://developers.naver.com/apps → 애플리케이션 등록 → "검색" API 추가 |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `CLOUDINARY_*` (3개) | https://cloudinary.com/users/register/free — Dashboard에서 복사 |
| `INSTAGRAM_ACCESS_TOKEN` | developers.facebook.com → Business 앱 생성 → **Instagram → API setup with Instagram business login** → **Generate token** (60일 토큰) |
| `INSTAGRAM_BUSINESS_ID` | `curl "https://graph.instagram.com/v23.0/me?fields=user_id,username&access_token=<토큰>"` 의 `user_id` |

> ⚠️ 게시 대상 인스타 계정은 **프로페셔널(비즈니스/크리에이터)** 이어야 합니다(개인 계정 불가).
> 이 방식(Instagram Login)은 **Facebook 페이지가 필요 없습니다.** 본인 계정 게시는 App Review도 불필요.
> 토큰은 60일짜리지만, 봇이 만료 임박 시 자동 갱신해 `output/ig_token.json`에 저장하므로
> 60일 안에 한 번이라도 실행되면 계속 유지됩니다.

## 브랜딩 (확정 필요)

기본값으로 들어가 있으니 운영 계정에 맞게 `src/config.py`에서 바꾸세요.

- `BRAND_NAME` = `"딥엑스 인사이트"`
- `INSTAGRAM_HANDLE` = `"deepx.insight"`
- `assets/logo.png` — 현재 플레이스홀더. 실제 로고로 교체.
- 색상 팔레트(`BRAND_*`)도 `config.py`에서 조정 가능.

## 자동 실행 (cron-job.org)

`.github/workflows/daily-post.yml` 가 `workflow_dispatch`로만 동작한다(자체 cron 미사용).
[cron-job.org](https://cron-job.org)에서 GitHub API로 이 워크플로우를 원하는 주기로 트리거.

1. GitHub repo Settings → Secrets and variables → Actions 에 위 키들을 등록
   (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `GEMINI_API_KEY`, `CLOUDINARY_CLOUD_NAME`,
   `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `INSTAGRAM_ACCESS_TOKEN`,
   `INSTAGRAM_BUSINESS_ID`).
2. GitHub Personal Access Token(workflow 권한) 발급.
3. cron-job.org에서 아래 엔드포인트를 POST로 호출하도록 등록:
   ```
   POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/daily-post.yml/dispatches
   Header: Authorization: Bearer <PAT>, Accept: application/vnd.github+json
   Body:   {"ref":"main"}
   ```

> 딥엑스는 단일 회사라 매일 새 기사가 없을 수 있다. 새 기사가 없으면 봇은 아무것도
> 게시하지 않고 정상 종료하므로, 하루 1회 정도 주기를 권장한다.

## 구조

```
src/
├── config.py            상수 (Naver 키, 검색어, 색상, 브랜드, 환경변수)
├── crawler.py           Naver 검색 + 중복 방지(URL + 제목 정규화)
├── summarizer.py        Gemini 전문·정보형 요약 + 딥엑스 관련성 게이트
├── background.py        기사 이미지 추출 + 세련된 mesh 배경 생성 (AI 생성 X)
├── card_composer.py     PIL로 1080×1080 카드 합성
├── uploader.py          Cloudinary + Instagram Graph API
├── token_manager.py     Instagram 장기 토큰 자동 갱신
└── main.py              오케스트레이션 (STAGE=compose|upload|full)
```

설계 노트는 `CLAUDE.md` 참고.
