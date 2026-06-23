import time
from pathlib import Path

import cloudinary
import cloudinary.uploader
import requests

from src.config import (
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
    CLOUDINARY_CLOUD_NAME,
    INSTAGRAM_BUSINESS_ID,
)
from src.token_manager import get_valid_token

# Instagram API with Instagram Login → graph.instagram.com 호스트 사용
GRAPH = "https://graph.instagram.com/v23.0"


def _graph_post(endpoint: str, params: dict, *, _retried: bool = False) -> dict:
    """Graph API POST. 토큰 만료(에러코드 190) 시 강제 갱신 후 1회 재시도."""
    resp = requests.post(f"{GRAPH}/{endpoint}", data=params, timeout=60)
    if not resp.ok:
        print(f"[uploader] Graph API {resp.status_code} 에러: {resp.text}")

        # 토큰 만료 에러(코드 190)면 강제 갱신 후 재시도 (1회만)
        if not _retried and resp.status_code in (400, 401):
            try:
                code = resp.json().get("error", {}).get("code")
            except ValueError:
                code = None
            if code == 190:
                print("[uploader] 토큰 만료 감지 → 강제 갱신 후 재시도...")
                new_token = get_valid_token(force_refresh=True)
                params["access_token"] = new_token
                return _graph_post(endpoint, params, _retried=True)

        resp.raise_for_status()
    return resp.json()


cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)


def upload_to_cloudinary(image_path: Path) -> str:
    """이미지를 Cloudinary에 업로드하고 공개 HTTPS URL 반환."""
    result = cloudinary.uploader.upload(
        str(image_path),
        folder="insta-deepx",
        resource_type="image",
        use_filename=True,
        unique_filename=True,
        overwrite=False,
    )
    return result["secure_url"]


def _create_image_container(image_url: str, is_carousel_item: bool) -> str:
    params = {
        "image_url": image_url,
        "access_token": get_valid_token(),
    }
    if is_carousel_item:
        params["is_carousel_item"] = "true"
    return _graph_post(f"{INSTAGRAM_BUSINESS_ID}/media", params)["id"]


def _create_carousel_container(children_ids: list[str], caption: str) -> str:
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": get_valid_token(),
    }
    return _graph_post(f"{INSTAGRAM_BUSINESS_ID}/media", params)["id"]


def _publish(creation_id: str) -> str:
    params = {
        "creation_id": creation_id,
        "access_token": get_valid_token(),
    }
    return _graph_post(f"{INSTAGRAM_BUSINESS_ID}/media_publish", params)["id"]


def upload_all_to_cloudinary(image_paths: list[Path]) -> list[str]:
    """카드 여러 장을 Cloudinary에 올리고 공개 URL 리스트 반환."""
    print(f"[uploader] Cloudinary 업로드 ({len(image_paths)}장)...")
    return [upload_to_cloudinary(p) for p in image_paths]


def publish_carousel(image_urls: list[str], caption: str) -> str:
    """이미 업로드된 공개 URL들로 인스타 캐러셀 게시. 게시된 미디어 ID 반환."""
    if not (2 <= len(image_urls) <= 10):
        raise ValueError("Instagram carousel은 2~10장만 지원")

    print("[uploader] 인스타 자식 컨테이너 생성...")
    children = [
        _create_image_container(url, is_carousel_item=True) for url in image_urls
    ]

    print("[uploader] 캐러셀 컨테이너 생성...")
    carousel_id = _create_carousel_container(children, caption)

    # 인스타가 처리할 시간 필요
    time.sleep(5)

    print("[uploader] 게시 중...")
    return _publish(carousel_id)


def post_carousel(image_paths: list[Path], caption: str) -> str:
    """편의 함수: Cloudinary 업로드 + 인스타 게시 한 번에."""
    image_urls = upload_all_to_cloudinary(image_paths)
    return publish_carousel(image_urls, caption)
