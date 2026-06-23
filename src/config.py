import os
from pathlib import Path

from dotenv import load_dotenv

# .env 는 로컬 개발용. CI(GitHub Actions)에선 secrets 가 직접 env 로 들어온다.
# 파일이 없거나 깨져도 조용히 건너뜀.
try:
    load_dotenv()
except (UnicodeDecodeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
FONT_DIR = ROOT / "assets" / "fonts"
LOGO_PATH = ROOT / "assets" / "logo.png"
POSTED_LOG = OUTPUT_DIR / "posted.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 뉴스 수집: Naver 검색 API
#   - 발급: https://developers.naver.com/apps → 검색 API 사용 신청
#   - "딥엑스"(DeepX, 한국 AI 반도체/NPU 스타트업, 김녹원 대표) 관련 기사만 모은다.
# ---------------------------------------------------------------------------
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "").strip()
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "").strip()

# 여러 검색어로 모아 originallink 기준 중복 제거. 동명이인/타사 'DeepX'는
# summarizer 의 관련성 게이트가 한 번 더 거른다.
NAVER_SEARCH_QUERIES = [
    "딥엑스",
    "딥엑스 NPU",
    "딥엑스 김녹원",
    "DeepX 반도체",
]
NAVER_DISPLAY = 30  # 검색어당 가져올 기사 수 (최대 100)

# 한 번 실행에 게시할 기사 수 / 본문 카드 수 / 정사각 크기
ARTICLES_PER_RUN = 1
CONTENT_CARDS = 5
IMAGE_SIZE = 1080

# ---------------------------------------------------------------------------
# 브랜딩 (딥엑스 전용 새 계정)
#   ⚠️ 아래 BRAND_NAME / INSTAGRAM_HANDLE 은 기본값. 실제 운영 계정에 맞춰 교체.
# ---------------------------------------------------------------------------
INSTAGRAM_HANDLE = "deepx.insight"
BRAND_NAME = "딥엑스 인사이트"
BRAND_TAGLINE = "딥엑스(DeepX) 소식을 한눈에"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# gemini-2.0-flash 는 2026-06-01 종료. flash-lite 는 무료 일일 한도(RPD)가
# 더 크고 요약 품질엔 충분 — flash(무료 20/일)는 테스트만 몇 번 해도 금방 소진된다.
GEMINI_TEXT_MODEL = "gemini-2.5-flash-lite"

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "").strip()
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

# Instagram API with Instagram Login 방식.
#  - INSTAGRAM_ACCESS_TOKEN: 앱 대시보드 'Generate token' 으로 받은 60일 장기 토큰
#  - INSTAGRAM_BUSINESS_ID: graph.instagram.com/me?fields=user_id 로 얻는 IG 프로페셔널 계정 ID
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
INSTAGRAM_BUSINESS_ID = os.environ.get("INSTAGRAM_BUSINESS_ID", "").strip()

# ---------------------------------------------------------------------------
# 컬러 팔레트 — 반도체/딥테크 톤 (딥네이비 + 일렉트릭 시안 액센트)
# ---------------------------------------------------------------------------
BRAND_PRIMARY = (15, 23, 42)     # deep navy (slate-900)
BRAND_ACCENT = (56, 189, 248)    # electric cyan (sky-400) — 어두운 배경용
BRAND_ACCENT_INK = (29, 78, 216)  # blue-700 — 밝은 본문 카드에서 쓰는 진한 액센트
BRAND_ACCENT_DEEP = (37, 99, 235)  # blue-600 (그라데이션 짝)
BRAND_BG = (248, 250, 252)       # light (slate-50)
BRAND_TEXT = (15, 23, 42)        # 본문 텍스트
BRAND_SUBTEXT = (100, 116, 139)  # 보조 텍스트 (slate-500)

# 생성 배경(mesh)용 기본 팔레트 — 기사 이미지가 없을 때 사용
GENERATED_BG_PALETTE = [
    (15, 23, 42),    # deep navy
    (30, 58, 138),   # blue-900
    (37, 99, 235),   # blue-600
    (56, 189, 248),  # cyan
    (14, 116, 144),  # cyan-800
]
