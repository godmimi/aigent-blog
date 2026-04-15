import os
import base64
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY")


def generate_image(title: str) -> str:
    """Gemini로 이미지 생성 → imgbb 업로드 → URL 반환"""
    image_data = _generate_with_gemini(title)
    if not image_data:
        return ""
    return _upload_to_imgbb(image_data)


def _generate_with_gemini(title: str) -> bytes | None:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"블로그 썸네일 이미지: '{title}' 주제. "
            "미니멀한 일러스트 스타일, 밝은 색감, 한국적 감성. "
            "텍스트 없음, 사람 얼굴 없음."
        )
        response = client.models.generate_image(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImageConfig(
                number_of_images=1,
                aspect_ratio="16:9",
            )
        )
        if response.generated_images:
            return response.generated_images[0].image.image_bytes
    except Exception as e:
        print(f"[Gemini 이미지 생성 실패] {e}")
    return None


def _upload_to_imgbb(image_data: bytes) -> str:
    """imgbb에 업로드하고 URL 반환"""
    try:
        b64 = base64.b64encode(image_data).decode("utf-8")
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()["data"]["url"]
    except Exception as e:
        print(f"[imgbb 업로드 실패] {e}")
        return ""


def upload_user_image(image_bytes: bytes) -> str:
    """사용자가 텔레그램으로 보낸 이미지 → imgbb 업로드"""
    return _upload_to_imgbb(image_bytes)
