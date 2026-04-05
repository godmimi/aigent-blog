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


def get_trending_topics():
    import random
    queries = [
        'ChatGPT+사용법+OR+AI+시작하기+OR+AI+초보',
        '바이브코딩+OR+요즘+AI+OR+코딩+없이+앱',
        'AI+업무+활용+OR+AI+생산성+OR+직장인+AI',
        'ChatGPT+vs+Claude+OR+AI+툴+비교+OR+AI+추천',
        'AI+이미지+생성+OR+AI+그림+OR+미드저니+한국어',
        'Claude+설치+OR+Claude+사용법+OR+Anthropic+시작',
        'LLM+꿀팁+OR+AI+프롬프트+작성+OR+AI+활용법',
        'AI+자동화+OR+업무+자동화+OR+스마트워크',
    ]
    query = random.choice(queries)
    encoded_query = urllib.parse.quote(query.replace('+', ' '))
    url = f'https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            try:
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                content = raw.decode('utf-8', errors='ignore')
            import io
            tree = ET.parse(io.StringIO(content))
            root = tree.getroot()
            items = root.findall('.//item')[:5]
            topics = [item.find('title').text for item in items if item.find('title') is not None]
            print(f"뉴스 수집 성공: {len(topics)}개 ({query})")
            return topics if topics else ["ChatGPT 시작하기", "AI 업무 활용", "AI 자동화"]
    except Exception as e:
        print(f"News fetch error: {e}")
        import random
        fallbacks = [
            ["ChatGPT 처음 시작하는 법", "일반인을 위한 AI 사용법", "AI로 업무 시간 줄이기"],
            ["바이브코딩으로 앱 만들기", "코딩 모르는 다도 AI로 개발하기", "노코드 AI 도구 추천"],
            ["Claude vs ChatGPT 비교", "AI 툴 선택 방법", "2026년 AI 코딩 알감"],
            ["AI 이미지 생성 무료로 시작하기", "AI 그림 만드는 법", "미드저니 한국어 사용법"],
            ["Claude 설치부터 시작하기", "스마트폰으로 Claude 쓰는 법", "Anthropic 무료 플랜 활용법"],
            ["LLM 꿀팁 10가지", "AI 프롬프트 잘 쓰는 법", "ChatGPT 활용 놓치고 있는 기능"],
            ["직장인을 위한 AI 툴 추천", "AI로 보고서 작성하기", "회의록 AI 자동 요약"],
            ["콘텐츠 AI 자동 제작", "블로그 AI로 운영하기", "SNS 콘텐츠 AI 자동화"],
        ]
        return random.choice(fallbacks)


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
                    "- young boy with medium-length black hair, black and white manga art style\n"
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
            else:
                raise Exception(f"imgbb 응답 오류: {result}")
    except Exception as e:
        print(f"imgbb 업로드 실패: {type(e).__name__}: {e}")
        return None


def generate_image_and_upload(client, title, intro_text):
    """이미지 생성 → imgbb 업로드 → URL 반환"""
    character_bytes = load_character_image()
    if character_bytes:
        print(f"캐릭터 이미지 로드 성공: {len(character_bytes)} bytes")

    manga_prompt = generate_manga_prompt(client, title, intro_text)
    print(f"만화 프롬프트: {manga_prompt}")

    image_bytes, mime_type = generate_manga_image(manga_prompt, character_bytes)
    if image_bytes:
        return upload_to_imgbb(image_bytes)
    return None


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
  → 준비물, 실행방법, 프롬프트 템플릿 포함
  예) Claude 설치법, ChatGPT 회의록 자동화, AI 이미지 생성 방법

TYPE B — 뉴스/이슈 분석/트렌드 정리
  → 팩트체크, 이슈 분석 카드 포함. 준비물/실행방법/프롬프트 없음
  예) AI 업계 사건사고, 신규 모델 출시, 정책 변화, 보안 이슈

주제를 보고 A/B 중 자동으로 판단해서 해당 HTML 구조를 사용해.

[제목 형식 규칙]
- TYPE A: [핵심 주제] [N단계/N가지] - [결과나 혜택] [이모지] [2026년]
- TYPE B: [핵심 이슈] [N가지 핵심] - [한줄 요약] [이모지] [2026년]
- N은 3~7 사이 자유롭게
- 이모지는 매번 다르게 (🚀 ⚡ 💡 🔥 ✅ 🎯 🛠️ 📌 중 하나)
- 반드시 하이픈(-)으로 앞뒤 구분
- 끝에 반드시 [2026년] 포함
- 같은 패턴 반복 금지

[라벨 규칙]
아래 목록에서 글 내용에 맞는 것 2~4개 선택:
AI활용법, ChatGPT, Claude, 바이브코딩, 업무자동화,
AI입문, 생산성, AI이미지, 프롬프트, 노코드,
직장인AI, AI툴추천, LLM꿀팁, AI시작하기, 블로그자동화, AI뉴스

[공통 HTML 작성 규칙]
1. 아래 제공된 컴포넌트 구조를 절대 변경하지 마.
2. 텍스트 내용만 채워 넣어.
3. 한 <p> 태그 안에 2문장 초과 금지.
4. 도입부는 문장 하나당 <p> 태그 하나씩. 반드시 5개 문장.
5. TYPE B에서는 준비물/실행방법/프롬프트 섹션 절대 사용 금지."""


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
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 20px;">하루에 2번, 우리 일상에 도움이 될 AI 꿀팁을 전해드리는 Geez 입니다🤖</p>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[~하고 있지 않으신가요? 글 주제와 딱 맞는 공감형 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[공감 이어가는 두 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[공감 세 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[격려 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[응원 마무리 — "천천히 따라오시면 쉽게 하실 수 있을 거예요😊" 류]</p>

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
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물 이름]</strong> — [한 줄 설명]</p>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:0.5px solid #e2e8f0;">
<div style="width:10px;height:10px;min-width:10px;border-radius:50%;background:#2563EB;margin-top:5px;"></div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물 이름]</strong> — [한 줄 설명]</p>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;">
<div style="width:10px;height:10px;min-width:10px;border-radius:50%;background:#2563EB;margin-top:5px;"></div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물 이름]</strong> — [한 줄 설명]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">실행 방법</h2>

<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">
<div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:#2563EB;display:flex;align-items:center;justify-content:center;margin-top:2px;"><span style="font-size:12px;font-weight:600;color:#fff;">1</span></div>
<div>
<p style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 4px;">[단계 제목]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[두 번째 문장]</p>
</div>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">
<div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:#2563EB;display:flex;align-items:center;justify-content:center;margin-top:2px;"><span style="font-size:12px;font-weight:600;color:#fff;">2</span></div>
<div>
<p style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 4px;">[단계 제목]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[두 번째 문장]</p>
</div>
</div>
<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px;">
<div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:#2563EB;display:flex;align-items:center;justify-content:center;margin-top:2px;"><span style="font-size:12px;font-weight:600;color:#fff;">3</span></div>
<div>
<p style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 4px;">[단계 제목]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[두 번째 문장]</p>
</div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">📋 바로 쓰는 프롬프트 템플릿</h2>

<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 01 — [용도 설명]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[복붙 가능한 실전 프롬프트]</p>
</div>
<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 02 — [용도 설명]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[복붙 가능한 실전 프롬프트]</p>
</div>
<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 03 — [용도 설명]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[복붙 가능한 실전 프롬프트]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항</h2>

<div style="margin-bottom:16px;">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
<span style="font-size:12px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;">⚠ 주의 01</span>
<span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span>
</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[주의 설명 두 번째 문장]</p>
</div>
<div style="margin-bottom:16px;">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
<span style="font-size:12px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;">⚠ 주의 02</span>
<span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span>
</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[주의 설명 두 번째 문장]</p>
</div>
<div style="margin-bottom:16px;">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
<span style="font-size:12px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;">⚠ 주의 03</span>
<span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span>
</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[주의 설명 두 번째 문장]</p>
</div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 8px;">[마무리 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[행동 유도 마무리 문장]</p>

<div style="background:#f8fafc;border-radius:10px;padding:14px 18px;border:0.5px solid #e2e8f0;">
<p style="font-size:13px;color:#64748b;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">Geez on AI는</strong> 매일 AI에 관련된 최신 내용들을 업데이트하며, 모든 포스팅은 Claude를 이용해 자동으로 생성됩니다 🤖</p>
</div>

[어투] 친근한 존댓말(~요, ~어요), 어렵지 않게
[분량] 800~1200자
[절대 금지] 스타일/색상/구조 변경 금지, 마크다운 금지, 코드블록 금지"""


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
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 20px;">하루에 2번, 우리 일상에 도움이 될 AI 꿀팁을 전해드리는 Geez 입니다🤖</p>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[이슈를 처음 접한 독자 입장의 공감형 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[이슈의 파장이나 중요성을 설명하는 두 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[일반 사용자에게도 영향이 있다는 세 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[복잡하지 않게 설명하겠다는 네 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[천천히 따라오면 이해할 수 있다는 응원 문장😊]</p>

<div style="border-left:3px solid #2563EB;padding:12px 16px;background:#f8fafc;margin-bottom:24px;">
<p style="font-size:14px;color:#1e293b;line-height:1.7;margin:0;">💡 <strong>핵심 포인트</strong> — [이슈 전체를 한 문장으로 요약]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:28px;">
<div style="display:flex;align-items:center;gap:8px;padding:12px 16px;background:#f8fafc;border-bottom:0.5px solid #e2e8f0;">
<span style="font-size:13px;font-weight:600;color:#1e293b;">📌 팩트체크</span>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:0.5px solid #f1f5f9;">
<span style="font-size:11px;font-weight:700;color:#166534;background:#dcfce7;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">✅ 사실</span>
<span style="font-size:13px;color:#475569;line-height:1.7;">[확인된 사실 1]</span>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:0.5px solid #f1f5f9;">
<span style="font-size:11px;font-weight:700;color:#166534;background:#dcfce7;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">✅ 사실</span>
<span style="font-size:13px;color:#475569;line-height:1.7;">[확인된 사실 2]</span>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:0.5px solid #f1f5f9;">
<span style="font-size:11px;font-weight:700;color:#991b1b;background:#fee2e2;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">❌ 오해</span>
<span style="font-size:13px;color:#475569;line-height:1.7;">[퍼지고 있는 오해나 루머]</span>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 16px;">
<span style="font-size:11px;font-weight:700;color:#92400e;background:#fef3c7;padding:2px 8px;border-radius:99px;flex-shrink:0;margin-top:1px;">❓ 미확인</span>
<span style="font-size:13px;color:#475569;line-height:1.7;">[아직 불분명한 내용]</span>
</div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">이슈 분석</h2>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">01 무슨 일이 있었나</span>
<h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 두 번째 문장]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">02 왜 중요한가</span>
<h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 두 번째 문장]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">03 나에게 미치는 영향</span>
<h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 두 번째 문장]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">04 지금 당장 할 것</span>
<h3 style="font-size:14px;font-weight:500;color:#1e293b;margin:0 0 5px;">[소제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[설명 두 번째 문장]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항</h2>

<div style="margin-bottom:16px;">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
<span style="font-size:12px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;">⚠ 주의 01</span>
<span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span>
</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[주의 설명 두 번째 문장]</p>
</div>
<div style="margin-bottom:16px;">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
<span style="font-size:12px;font-weight:600;color:#B45309;background:#FEF3C7;padding:3px 10px;border-radius:99px;border:0.5px solid #D97706;">⚠ 주의 02</span>
<span style="font-size:14px;font-weight:500;color:#1e293b;">[주의 제목]</span>
</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 4px;padding-left:4px;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;padding-left:4px;">[주의 설명 두 번째 문장]</p>
</div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 8px;">[이슈에서 얻을 수 있는 교훈이나 시사점 마무리 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[독자에게 앞으로 어떻게 대처하면 좋을지 행동 유도 문장]</p>

<div style="background:#f8fafc;border-radius:10px;padding:14px 18px;border:0.5px solid #e2e8f0;">
<p style="font-size:13px;color:#64748b;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">Geez on AI는</strong> 매일 AI에 관련된 최신 내용들을 업데이트하며, 모든 포스팅은 Claude를 이용해 자동으로 생성됩니다 🤖</p>
</div>

[어투] 친근한 존댓말(~요, ~어요), 어렵지 않게
[분량] 800~1200자
[절대 금지] 스타일/색상/구조 변경 금지, 마크다운 금지, 코드블록 금지
[TYPE B 절대 금지] 준비물 섹션, 실행방법 섹션, 프롬프트 템플릿 섹션 사용 금지"""


def classify_topic(client, topic):
    """주제를 분석해서 A/B 유형 판단"""
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


def generate_post(topics, force_type=None):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    main_topic = topics[0] if topics else "AI 자동화"
    ref_topics = ', '.join(topics[1:3]) if len(topics) > 1 else ""
    topic_str = main_topic + (f" (관련 트렌드: {ref_topics})" if ref_topics else "")

    # 유형 판단
    post_type = force_type if force_type else classify_topic(client, topic_str)
    print(f"글 유형: TYPE {post_type}")

    user_prompt_template = USER_PROMPT_TYPE_A if post_type == 'A' else USER_PROMPT_TYPE_B
    user_prompt = user_prompt_template.format(topic=topic_str)

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
    intro_text = intro_match.group(1).strip() if intro_match else topic_str
    html = html_match.group(1).strip() if html_match else raw

    # 이미지 생성 및 삽입
    image_url = generate_image_and_upload(client, title, intro_text)
    if image_url:
        img_tag = f'<img src="{image_url}" alt="{title}" style="width:100%;max-width:800px;height:auto;margin:0 0 24px;border-radius:10px;" />'
        html = html.replace("[이미지 자리 — 코드에서 자동 삽입됨]", img_tag)
        if img_tag not in html:
            html = img_tag + "\n" + html
        print(f"이미지 삽입 완료: {image_url}")
    else:
        html = html.replace("[이미지 자리 — 코드에서 자동 삽입됨]", "")
        print("이미지 없이 포스팅 진행")

    return title, html, labels, image_url


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
        print(f"Blogger 에러 {e.code}: {e.read().decode('utf-8', errors='replace')}")
        raise


def main():
    print(f"시작: {datetime.now()}")
    topics = get_trending_topics()
    print(f"트렌드 토픽: {topics[:3]}")
    title, html_content, labels, image_url = generate_post(topics)
    print(f"제목: {title}")
    print(f"라벨: {labels}")
    access_token = get_access_token()
    post_to_blogger(access_token, title, html_content, labels, image_url)
    print("완료!")


if __name__ == '__main__':
    main()
