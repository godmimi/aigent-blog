import os
import io
import json
import base64
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
import anthropic
from google import genai
from google.genai import types

ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']
GOOGLE_CLIENT_ID = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
BLOG_ID = os.environ['BLOG_ID']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
IMGBB_API_KEY = os.environ['IMGBB_API_KEY']
CHARACTER_IMAGE_URL = os.environ.get('CHARACTER_IMAGE_URL', '')
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# =============================================
# 텔레그램 함수
# =============================================

def telegram_send(text):
    data = json.dumps({'chat_id': TELEGRAM_CHAT_ID, 'text': text}).encode()
    req = urllib.request.Request(
        f"{TELEGRAM_API}/sendMessage", data=data,
        headers={'Content-Type': 'application/json'}
    )
    urllib.request.urlopen(req)


def get_updates():
    url = f"{TELEGRAM_API}/getUpdates?timeout=5"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())['result']


def acknowledge_updates(updates):
    if not updates:
        return
    last_id = max(u['update_id'] for u in updates)
    url = f"{TELEGRAM_API}/getUpdates?offset={last_id + 1}&limit=1"
    urllib.request.urlopen(url)


def fetch_url_content(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:3000]
    except Exception as e:
        return None


# =============================================
# 구글 인증
# =============================================

def get_access_token():
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': GOOGLE_REFRESH_TOKEN,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())['access_token']


# =============================================
# 이미지 생성 함수
# =============================================

def generate_manga_prompt(client, title, intro_text):
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": f"""다음 블로그 글의 도입부 내용을 바탕으로 2컷 흑백 만화 생성 프롬프트를 영어로 만들어줘.

규칙:
- 1컷: 독자가 공감할 수 있는 문제 상황 (캐릭터가 곤란하거나 놀란 표정)
- 2컷: 해결책을 발견한 기쁜 표정
- 흑백 만화 스타일, 두 컷을 가로로 나란히 배치
- 말풍선 없이 표정과 몸짓만으로 상황 전달
- no text, no speech bubbles

글 제목: {title}
도입부: {intro_text[:300]}

프롬프트만 출력, 다른 말 없이."""}]
    )
    return msg.content[0].text.strip()


def load_character_image():
    if not CHARACTER_IMAGE_URL:
        return None
    try:
        req = urllib.request.Request(CHARACTER_IMAGE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"캐릭터 이미지 로드 실패: {e}")
        return None


def generate_manga_image(prompt, character_bytes=None):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        if character_bytes:
            contents = [
                types.Part.from_bytes(data=character_bytes, mime_type="image/png"),
                types.Part.from_text(
                    text=f"{prompt}\n\n"
                    "스타일 규칙:\n"
                    "- 위 이미지의 캐릭터 외모(단발머리, 얼굴형)만 레퍼런스로 사용해줘. 마이크나 특정 소품은 따라 그리지 마.\n"
                    "- 흑백 만화 스타일, 선명한 검은 선\n"
                    "- 두 컷을 가로로 나란히 배치\n"
                    "- do NOT draw any speech bubbles or text in the image\n"
                    "- no color, white background"
                )
            ]
        else:
            contents = [
                types.Part.from_text(
                    text=f"{prompt}\n\n"
                    "스타일 규칙:\n"
                    "- 단발머리 귀여운 여성 캐릭터\n"
                    "- 흑백 만화 스타일, 선명한 검은 선\n"
                    "- 두 컷을 가로로 나란히 배치\n"
                    "- do NOT draw any speech bubbles or text\n"
                    "- no color, white background"
                )
            ]
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"])
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                return part.inline_data.data, part.inline_data.mime_type
        raise Exception("이미지 파트 없음")
    except Exception as e:
        print(f"Gemini 이미지 생성 실패: {type(e).__name__}: {e}")
        return None, None


def upload_to_imgbb(image_bytes):
    try:
        b64 = base64.b64encode(image_bytes).decode()
        data = urllib.parse.urlencode({'key': IMGBB_API_KEY, 'image': b64}).encode()
        req = urllib.request.Request('https://api.imgbb.com/1/upload', data=data, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get('success'):
                url = result['data']['url']
                print(f"imgbb 업로드 성공: {url}")
                return url
    except Exception as e:
        print(f"imgbb 업로드 실패: {type(e).__name__}: {e}")
        return None


def generate_image_and_upload(client, title, intro_text):
    character_bytes = load_character_image()
    manga_prompt = generate_manga_prompt(client, title, intro_text)
    print(f"만화 프롬프트: {manga_prompt}")
    image_bytes, mime_type = generate_manga_image(manga_prompt, character_bytes)
    if image_bytes:
        return upload_to_imgbb(image_bytes)
    return None


# =============================================
# 글 유형 판단
# =============================================

def classify_topic(client, topic):
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": f"""다음 블로그 주제가 튜토리얼/사용법(A)인지 뉴스/이슈분석(B)인지 판단해줘.
A: 사용법, 설치법, 활용법, 입문 가이드, 비교 추천
B: 사건사고, 신규 출시 뉴스, 정책변화, 보안이슈, 트렌드 분석

주제: {topic}

A 또는 B 중 하나만 출력해."""}]
    )
    result = msg.content[0].text.strip().upper()
    return 'B' if 'B' in result else 'A'


# =============================================
# SYSTEM PROMPT
# =============================================

SYSTEM_PROMPT = """너는 한국어 AI/테크 블로그 콘텐츠 전문 작가야.
직장인 및 AI 입문자를 타깃으로 실용적인 글을 써줘.
마크다운 사용 금지. 오직 HTML만 출력해. 코드블록(```) 감싸지 마.

[출력 형식]
TITLE: [제목]
TYPE: [A 또는 B]
LABELS: [라벨1, 라벨2, 라벨3]
INTRO: [도입부 텍스트만 따로]
HTML:
[HTML 전체 내용]

[글 유형 판단 규칙]
TYPE A — 튜토리얼/사용법/입문 가이드
TYPE B — 뉴스/이슈 분석/트렌드 정리

[제목 형식]
- TYPE A: [핵심 주제] [N단계/N가지] - [결과나 혜택] [이모지] [2026년]
- TYPE B: [핵심 이슈] [N가지 핵심] - [한줄 요약] [이모지] [2026년]
- N은 3~7 사이 자유롭게, 이모지는 매번 다르게

[라벨 규칙]
아래 목록에서 2~4개 선택:
AI활용법, ChatGPT, Claude, 바이브코딩, 업무자동화,
AI입문, 생산성, AI이미지, 프롬프트, 노코드,
직장인AI, AI툴추천, LLM꿀팁, AI시작하기, 블로그자동화, AI뉴스

[공통 HTML 작성 규칙]
1. 아래 컴포넌트 구조 절대 변경 금지
2. 텍스트 내용만 채워 넣기
3. 한 <p> 태그 안에 2문장 초과 금지
4. 도입부는 문장 하나당 <p> 태그 하나씩, 반드시 5개
5. TYPE B에서는 준비물/실행방법/프롬프트 섹션 절대 사용 금지"""


# =============================================
# TYPE A 템플릿
# =============================================

USER_PROMPT_TYPE_A = """다음 주제로 한국어 블로그 글을 HTML 형식으로 작성해줘. (TYPE A — 튜토리얼)

주제: {topic}

TITLE: [핵심 주제 + N단계/N가지] - [결과나 혜택] [이모지] [2026년]
TYPE: A
LABELS: [관련 라벨 2~4개]
INTRO: [도입부 5문장 텍스트]
HTML:

[이미지 자리 — 코드에서 자동 삽입됨]

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 2px;">안녕하세요</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 20px;">하루에 2번, 우리 일상에 도움이 될 AI 꿀팁을 전해드리는 AIgent Labs 입니다🤖</p>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[공감형 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[두 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[세 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[격려 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[응원 마무리😊]</p>

<div style="border-left:3px solid #2563EB;padding:12px 16px;background:#f8fafc;margin-bottom:24px;">
<p style="font-size:14px;color:#1e293b;line-height:1.7;margin:0;">💡 <strong>핵심 포인트</strong> — [한 문장 핵심 요약]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:28px;">
<div style="display:flex;align-items:center;gap:8px;padding:12px 16px;background:#f8fafc;border-bottom:0.5px solid #e2e8f0;">
<span style="font-size:13px;font-weight:600;color:#1e293b;">&#128203; 목차</span>
<span style="font-size:11px;color:#2563EB;background:#EFF6FF;padding:1px 7px;border-radius:99px;border:0.5px solid #BFDBFE;">[가이드 유형]</span>
</div>
<div style="padding:4px 0 8px;">
<div style="display:flex;align-items:center;gap:10px;padding:7px 16px;"><div style="width:6px;height:6px;border-radius:50%;background:#2563EB;flex-shrink:0;"></div><span style="font-size:13px;color:#475569;">작업에 필요한 준비물</span></div>
<div style="display:flex;align-items:center;gap:10px;padding:7px 16px;"><div style="width:6px;height:6px;border-radius:50%;background:#2563EB;flex-shrink:0;"></div><span style="font-size:13px;color:#475569;">실행 방법</span></div>
<div style="display:flex;align-items:center;gap:10px;padding:7px 16px;"><div style="width:6px;height:6px;border-radius:50%;background:#2563EB;flex-shrink:0;"></div><span style="font-size:13px;color:#475569;">바로 쓰는 프롬프트 템플릿</span></div>
<div style="display:flex;align-items:center;gap:10px;padding:7px 16px;"><div style="width:6px;height:6px;border-radius:50%;background:#D97706;flex-shrink:0;"></div><span style="font-size:13px;color:#475569;">&#9888; 주의사항</span></div>
</div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">작업에 필요한 준비물</h2>

<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:0.5px solid #e2e8f0;">
<div style="width:10px;height:10px;min-width:10px;border-radius:50%;background:#2563EB;margin-top:5px;"></div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물]</strong> — [설명]</p>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:0.5px solid #e2e8f0;">
<div style="width:10px;height:10px;min-width:10px;border-radius:50%;background:#2563EB;margin-top:5px;"></div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물]</strong> — [설명]</p>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;">
<div style="width:10px;height:10px;min-width:10px;border-radius:50%;background:#2563EB;margin-top:5px;"></div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물]</strong> — [설명]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">실행 방법</h2>

<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">
<div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:#2563EB;display:flex;align-items:center;justify-content:center;margin-top:2px;"><span style="font-size:12px;font-weight:600;color:#fff;">1</span></div>
<div><p style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 4px;">[단계 제목]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;">[첫 번째 문장]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[두 번째 문장]</p></div>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">
<div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:#2563EB;display:flex;align-items:center;justify-content:center;margin-top:2px;"><span style="font-size:12px;font-weight:600;color:#fff;">2</span></div>
<div><p style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 4px;">[단계 제목]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;">[첫 번째 문장]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[두 번째 문장]</p></div>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">
<div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:#2563EB;display:flex;align-items:center;justify-content:center;margin-top:2px;"><span style="font-size:12px;font-weight:600;color:#fff;">3</span></div>
<div><p style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 4px;">[단계 제목]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;">[첫 번째 문장]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[두 번째 문장]</p></div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">📋 바로 쓰는 프롬프트 템플릿</h2>

<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 01 — [용도]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[실전 프롬프트]</p>
</div>
<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 02 — [용도]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[실전 프롬프트]</p>
</div>
<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 03 — [용도]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[실전 프롬프트]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항</h2>

<div style="margin-bottom:16px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="font-size:11px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;white-space:nowrap;">⚠ 01</span><span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span></div><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[설명 2]</p></div>
<div style="margin-bottom:16px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="font-size:11px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;white-space:nowrap;">⚠ 02</span><span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span></div><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[설명 2]</p></div>
<div style="margin-bottom:16px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="font-size:11px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;white-space:nowrap;">⚠ 03</span><span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span></div><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[설명 2]</p></div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 8px;">[마무리 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[행동 유도 마무리]</p>

<div style="background:#f8fafc;border-radius:10px;padding:14px 18px;border:0.5px solid #e2e8f0;">
<p style="font-size:13px;color:#64748b;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">AIgent Labs는</strong> 매일 AI에 관련된 최신 내용들을 업데이트하며, 모든 포스팅은 Claude를 이용해 자동으로 생성됩니다 🤖</p>
</div>

[어투] 친근한 존댓말, 800~1200자, 마크다운/코드블록 금지"""


# =============================================
# TYPE B 템플릿
# =============================================

USER_PROMPT_TYPE_B = """다음 주제로 한국어 블로그 글을 HTML 형식으로 작성해줘. (TYPE B — 뉴스/이슈 분석)

주제: {topic}

TITLE: [핵심 이슈 + N가지 핵심] - [한줄 요약] [이모지] [2026년]
TYPE: B
LABELS: [관련 라벨 2~4개, AI뉴스 포함]
INTRO: [도입부 5문장 텍스트]
HTML:

[이미지 자리 — 코드에서 자동 삽입됨]

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 2px;">안녕하세요</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 20px;">하루에 2번, 우리 일상에 도움이 될 AI 꿀팁을 전해드리는 AIgent Labs 입니다🤖</p>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[이슈 공감 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[이슈 파장 두 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[일반 사용자 영향 세 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[쉽게 설명하겠다는 네 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[응원 마무리😊]</p>

<div style="border-left:3px solid #2563EB;padding:12px 16px;background:#f8fafc;margin-bottom:24px;">
<p style="font-size:14px;color:#1e293b;line-height:1.7;margin:0;">💡 <strong>핵심 포인트</strong> — [이슈 한 문장 요약]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:28px;">
<div style="display:flex;align-items:center;gap:8px;padding:12px 16px;background:#f8fafc;border-bottom:0.5px solid #e2e8f0;">
<span style="font-size:13px;font-weight:600;color:#1e293b;">📌 팩트체크</span>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:0.5px solid #f1f5f9;"><span style="font-size:11px;font-weight:700;color:#166534;background:#dcfce7;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">✅ 사실</span><span style="font-size:13px;color:#475569;line-height:1.7;">[확인된 사실 1]</span></div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:0.5px solid #f1f5f9;"><span style="font-size:11px;font-weight:700;color:#166534;background:#dcfce7;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">✅ 사실</span><span style="font-size:13px;color:#475569;line-height:1.7;">[확인된 사실 2]</span></div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:0.5px solid #f1f5f9;"><span style="font-size:11px;font-weight:700;color:#991b1b;background:#fee2e2;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">❌ 오해</span><span style="font-size:13px;color:#475569;line-height:1.7;">[퍼지고 있는 오해]</span></div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;"><span style="font-size:11px;font-weight:700;color:#92400e;background:#fef3c7;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">❓ 미확인</span><span style="font-size:13px;color:#475569;line-height:1.7;">[불분명한 내용]</span></div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">이슈 분석</h2>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;"><span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">01 무슨 일이 있었나</span><h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 2]</p></div>
<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;"><span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">02 왜 중요한가</span><h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 2]</p></div>
<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;"><span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">03 나에게 미치는 영향</span><h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 2]</p></div>
<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;"><span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">04 지금 당장 할 것</span><h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 2]</p></div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항</h2>

<div style="margin-bottom:16px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="font-size:11px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;white-space:nowrap;">⚠ 01</span><span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span></div><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[설명 2]</p></div>
<div style="margin-bottom:16px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="font-size:11px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;white-space:nowrap;">⚠ 02</span><span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span></div><p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[설명 1]</p><p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[설명 2]</p></div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 8px;">[마무리 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[행동 유도 마무리]</p>

<div style="background:#f8fafc;border-radius:10px;padding:14px 18px;border:0.5px solid #e2e8f0;">
<p style="font-size:13px;color:#64748b;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">AIgent Labs는</strong> 매일 AI에 관련된 최신 내용들을 업데이트하며, 모든 포스팅은 Claude를 이용해 자동으로 생성됩니다 🤖</p>
</div>

[어투] 친근한 존댓말, 800~1200자
[TYPE B 절대 금지] 준비물/실행방법/프롬프트 템플릿 섹션 사용 금지"""


# =============================================
# 글 생성
# =============================================

def generate_post(content):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    topic = content[:1500]

    post_type = classify_topic(client, topic)
    print(f"글 유형: TYPE {post_type}")

    user_prompt_template = USER_PROMPT_TYPE_A if post_type == 'A' else USER_PROMPT_TYPE_B
    user_prompt = user_prompt_template.format(topic=topic)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    raw = message.content[0].text.strip()

    title_match = re.search(r"TITLE:\s*(.+)", raw)
    labels_match = re.search(r"LABELS:\s*(.+)", raw)
    intro_match = re.search(r"INTRO:\s*([\s\S]+?)(?=HTML:)", raw)
    html_match = re.search(r"HTML:\s*([\s\S]+)", raw)

    title = title_match.group(1).strip() if title_match else "AI 소식 2026"
    labels = [l.strip() for l in labels_match.group(1).split(',')] if labels_match else ['AI활용법', 'AI뉴스']
    intro_text = intro_match.group(1).strip() if intro_match else topic
    html = html_match.group(1).strip() if html_match else raw

    image_url = generate_image_and_upload(client, title, intro_text)
    if image_url:
        img_tag = f'<img src="{image_url}" alt="{title}" style="width:100%;max-width:800px;height:auto;margin:0 0 24px;border-radius:10px;" />'
        html = html.replace("[이미지 자리 — 코드에서 자동 삽입됨]", img_tag)
        if img_tag not in html:
            html = img_tag + "\n" + html
    else:
        html = html.replace("[이미지 자리 — 코드에서 자동 삽입됨]", "")

    return title, html, labels, image_url


# =============================================
# Blogger 포스팅
# =============================================

def post_to_blogger(access_token, title, content, labels, image_url=None):
    url = f'https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/'
    post_data = {
        'kind': 'blogger#post',
        'title': title,
        'content': content,
        'labels': labels
    }
    if image_url:
        post_data['images'] = [{'url': image_url}]
    data = json.dumps(post_data).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    })
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"포스팅 완료: {result.get('url', 'unknown')}")
            return result
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8', errors='replace')
        print(f"Blogger 에러 {e.code}: {error_msg}")
        raise


# =============================================
# 메인
# =============================================

def main():
    updates = get_updates()
    if not updates:
        print("No new messages.")
        return

    acknowledge_updates(updates)

    for update in updates:
        msg = update.get('message', {})
        chat_id = str(msg.get('chat', {}).get('id', ''))
        text = msg.get('text', '').strip()

        if chat_id != TELEGRAM_CHAT_ID:
            continue
        if not text:
            continue

        if text.startswith('http'):
            print(f"URL 처리: {text}")
            telegram_send("📥 URL 받았어요! 글 생성 중...")
            content = fetch_url_content(text)
            if not content:
                telegram_send("❌ URL 내용을 가져오지 못했어요.")
                continue
        else:
            if len(text) < 50:
                continue
            print(f"텍스트 처리: {text[:50]}...")
            telegram_send("📥 내용 받았어요! 글 생성 중... (1~2분 소요)")
            content = text[:3000]

        try:
            title, html, labels, image_url = generate_post(content)
            access_token = get_access_token()
            result = post_to_blogger(access_token, title, html, labels, image_url)
            post_url = result.get('url', 'unknown')
            telegram_send(f"✅ 포스팅 완료!\n📝 {title}\n🏷 {', '.join(labels)}\n🔗 {post_url}")
            print(f"완료: {post_url}")
        except Exception as e:
            error_msg = str(e)[:200]
            telegram_send(f"❌ 포스팅 실패\n오류: {error_msg}")
            print(f"에러: {e}")
        break


if __name__ == '__main__':
    main()
