"""Instagram User Access Token 자동 갱신 (Instagram API with Instagram Login).

앱 대시보드의 'Generate token' 으로 받은 토큰은 60일짜리 장기(long-lived) 토큰이다.
`ig_refresh_token` 으로 (24시간 이상 지난) 토큰을 갱신하면 60일 더 연장된다.

이 봇은 매일 실행되므로 만료가 임박하면 자동 갱신하고, 갱신된 토큰을
`output/ig_token.json` 에 저장한다. GitHub Actions 워크플로우가 이 파일을 캐시하므로
(posted.json 과 동일한 패턴) 봇이 60일 안에 한 번이라도 돌면 토큰이 무한히 굴러간다.
"""

from __future__ import annotations

import json
import time

import requests

from src.config import INSTAGRAM_ACCESS_TOKEN, OUTPUT_DIR

GRAPH = "https://graph.instagram.com"
TOKEN_CACHE = OUTPUT_DIR / "ig_token.json"

# 남은 수명이 이 값 미만이면 갱신 시도 (10일)
_REFRESH_THRESHOLD_SECONDS = 10 * 24 * 60 * 60
# IG 장기 토큰 기본 수명 (60일)
_LONG_LIVED_SECONDS = 60 * 24 * 60 * 60

_cached_token: str | None = None


def _load_cache() -> dict | None:
    if TOKEN_CACHE.exists():
        try:
            return json.loads(TOKEN_CACHE.read_text())
        except (ValueError, OSError):
            return None
    return None


def _save_cache(token: str, expires_at: int) -> None:
    try:
        TOKEN_CACHE.write_text(
            json.dumps({"access_token": token, "expires_at": expires_at})
        )
    except OSError as e:
        print(f"[token_manager] 토큰 캐시 저장 실패(무시): {e}")


def _refresh(token: str) -> tuple[str | None, int | None]:
    """ig_refresh_token 으로 장기 토큰 갱신. (새 토큰, 만료 epoch) 또는 (None, None)."""
    try:
        resp = requests.get(
            f"{GRAPH}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
            timeout=30,
        )
        if resp.ok:
            data = resp.json()
            new_token = data.get("access_token")
            if new_token:
                expires_at = int(time.time()) + int(
                    data.get("expires_in", _LONG_LIVED_SECONDS)
                )
                print("[token_manager] ✅ IG 토큰 갱신 성공 (60일 연장)")
                return new_token, expires_at
        # 토큰이 24시간 미만이거나 만료된 경우 등 — 갱신 불가
        print(f"[token_manager] 토큰 갱신 불가: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        print(f"[token_manager] 토큰 갱신 요청 실패: {e}")
    return None, None


def get_valid_token(force_refresh: bool = False) -> str:
    """유효한 Instagram User Access Token 반환.

    캐시된 토큰을 우선 쓰고, 만료가 임박(또는 만료 정보 없음)하면 자동 갱신한다.
    갱신 실패 시에는 가지고 있는 토큰을 그대로 반환한다(최소한 시도).
    """
    global _cached_token  # noqa: PLW0603

    if _cached_token and not force_refresh:
        return _cached_token

    cache = _load_cache()
    now = int(time.time())
    if cache:
        token = cache.get("access_token", INSTAGRAM_ACCESS_TOKEN)
        expires_at = int(cache.get("expires_at", 0))
    else:
        token = INSTAGRAM_ACCESS_TOKEN
        expires_at = 0

    needs_refresh = force_refresh or (expires_at - now) < _REFRESH_THRESHOLD_SECONDS
    if needs_refresh:
        new_token, new_exp = _refresh(token)
        if new_token:
            token, expires_at = new_token, new_exp
            _save_cache(token, expires_at)
    else:
        days_left = (expires_at - now) // 86400
        print(f"[token_manager] IG 토큰 유효 (남은 {days_left}일)")

    _cached_token = token
    return token
