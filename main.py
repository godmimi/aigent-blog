import os
import json
import base64
import re
import urllib.request
import urllib.parse
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
    url = f'https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko'
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


def generate_image_prompt(client, title, summary):
    """글 내용 기반 캐릭터 일러스트 이미지 프롬프트 생성 (Haiku 유지)"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": f"""다음 블로그 글의 대표 이미지 프롬프트를 영어로 만들어줘.

조건:
- 글의 주제와 인트로 상황에 딱 맞는 장면으로 시각화
- 귀여운 단일 캐릭터가 해당 상황을 연기하는 장면
- flat illustration style, 2D vector art
- soft pastel colors, minimal clean background
- no text in image
- 40단어 이내

제목: {title}
요약: {summary[:200]}

프롬프트만 출력, 다른 말 없이."""}]
    )
    return msg.content[0].text.strip()


def get_image_base64(prompt):
    """Gemini로 인트로 상황에 맞는 캐릭터 일러스트 생성"""
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            )
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
                b64 = base64.b64encode(image_bytes).decode()
                mime = part.inline_data.mime_type
                print(f"Gemini 이미지 생성 성공")
                return f"data:{mime};base64,{b64}"
        raise Exception("이미지 파트 없음")
    except Exception as e:
        print(f"Gemini 이미지 생성 실패: {type(e).__name__}: {e}")
        return None


SYSTEM_PROMPT = """너는 한국어 AI/테크 블로그 콘텐츠 전문 작가야.
직장인 및 AI 입문자를 타깃으로 실용적인 글을 써줘.
마크다운 사용 금지. 오직 HTML만 출력해. 코드블록(```) 감싸지 마.

[출력 형식]
TITLE: [제목]
LABELS: [라벨1, 라벨2, 라벨3]
HTML:
[HTML 전체 내용]

[제목 형식 규칙]
- [핵심 주제] [N단계/N가지] - [결과나 혜택] [이모지] [2026년]
- N은 주제에 따라 3~7 사이에서 자유롭게 결정해. 5로 고정하지 마.
- 결과/혜택 표현을 매번 다양하게 써:
  예) 완전 정복하기, 무료로 시작하기, 10분 만에 세팅하기,
      비용 절반으로 줄이기, 초보자도 바로 쓰는 법,
      실전 적용 가이드, 한 번에 끝내기, 5분이면 충분해
- 이모지는 매번 다르게 (🚀 ⚡ 💡 🔥 ✅ 🎯 🛠️ 📌 중 하나)
- 반드시 하이픈(-)으로 앞뒤 구분
- 끝에 반드시 [2026년] 포함
- 같은 패턴 반복 금지

[라벨 규칙]
아래 목록에서 글 내용에 맞는 것 2~4개 선택:
AI활용법, ChatGPT, Claude, 바이브코딩, 업무자동화,
AI입문, 생산성, AI이미지, 프롬프트, 노코드,
직장인AI, AI툴추천, LLM꿀팁, AI시작하기, 블로그자동화

[HTML 작성 규칙 - 반드시 준수]
1. 아래 제공된 컴포넌트 구조를 절대 변경하지 마. 색상, 스타일, 태그 구조 모두 그대로.
2. 텍스트 내용만 채워 넣어.
3. 한 <p> 태그 안에 2문장 초과 금지. 길면 새 <p> 태그로 분리.
4. 각 항목 설명은 핵심만 간결하게. 4줄 이상 금지.
5. 도입부는 문장 하나당 <p> 태그 하나씩.
6. 실행 방법은 HTML 컴포넌트 없이 텍스트로만 작성.
7. 프롬프트 템플릿은 실제로 복붙해서 쓸 수 있는 구체적인 내용으로 작성."""

USER_PROMPT_TEMPLATE = """다음 주제로 한국어 블로그 글을 HTML 형식으로 작성해줘.

주제: {topic}

아래 HTML 구조에 내용만 채워서 출력해. 구조와 스타일은 절대 바꾸지 마.

TITLE: [핵심 주제 + N단계/N가지] - [결과나 혜택] [이모지] [2026년]
LABELS: [관련 라벨 2~4개]
HTML:

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 4px;">안녕하세요</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 16px;">하루에 2번, 우리 일상에 도움이 될 AI 꿀팁을 전해드리는 Geez 입니다🤖</p>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[~하고 있지 않으신가요? 공감형 첫 문장 — 글 주제와 딱 맞는 상황 묘사]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[공감 이어가는 두 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[상황을 더 구체화하는 세 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[격려하는 네 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[쉽게 따라하실 수 있을 거예요 류의 응원 마무리 문장]</p>

[이미지 자리 — 코드에서 자동 삽입됨]

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

<div style="border-left:3px solid #2563EB;padding:12px 16px;background:#f8fafc;margin-bottom:24px;">
<p style="font-size:14px;color:#1e293b;line-height:1.7;margin:0;">💡 <strong>핵심 포인트</strong> — [한 문장 핵심 요약]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">작업에 필요한 준비물</h2>

<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:0.5px solid #e2e8f0;">
<div style="font-size:12px;font-weight:600;color:#2563EB;background:#EFF6FF;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">1</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물 이름]</strong> — [한 줄 설명]</p>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:0.5px solid #e2e8f0;">
<div style="font-size:12px;font-weight:600;color:#2563EB;background:#EFF6FF;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">2</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물 이름]</strong> — [한 줄 설명]</p>
</div>
<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;">
<div style="font-size:12px;font-weight:600;color:#2563EB;background:#EFF6FF;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">3</div>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;"><strong style="color:#1e293b;">[준비물 이름]</strong> — [한 줄 설명]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">실행 방법</h2>

<p style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 4px;">① [첫 번째 단계 제목]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 6px;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 16px;">[두 번째 문장]</p>

<p style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 4px;">② [두 번째 단계 제목]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 6px;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 16px;">[두 번째 문장]</p>

<p style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 4px;">③ [세 번째 단계 제목]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 6px;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0 0 16px;">[두 번째 문장]</p>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">📋 바로 쓰는 프롬프트 템플릿</h2>

<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 01 — [용도 설명]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[실제로 복붙해서 쓸 수 있는 구체적인 프롬프트 내용]</p>
</div>

<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 02 — [용도 설명]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[실제로 복붙해서 쓸 수 있는 구체적인 프롬프트 내용]</p>
</div>

<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
<p style="font-size:11px;font-weight:600;color:#94a3b8;margin:0 0 8px;letter-spacing:0.05em;">TEMPLATE 03 — [용도 설명]</p>
<p style="font-size:12px;color:#e2e8f0;line-height:1.9;margin:0;">[실제로 복붙해서 쓸 수 있는 구체적인 프롬프트 내용]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항</h2>

<div style="border:1px solid #D97706;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#B45309;border:0.5px solid #D97706;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">⚠ 주의 01</span>
<h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">[주의 제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[주의 설명 두 번째 문장]</p>
</div>

<div style="border:1px solid #D97706;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#B45309;border:0.5px solid #D97706;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">⚠ 주의 02</span>
<h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">[주의 제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[주의 설명 두 번째 문장]</p>
</div>

<div style="border:1px solid #D97706;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#B45309;border:0.5px solid #D97706;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">⚠ 주의 03</span>
<h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">[주의 제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[주의 설명 두 번째 문장]</p>
</div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 8px;">[의미 있는 마무리 첫 문장 — 독자가 얻은 가치를 한 번 더 상기시키는 내용]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[행동 유도 마무리 문장 — 오늘 당장 해볼 수 있는 작은 행동 권유]</p>

<div style="background:#f8fafc;border-radius:10px;padding:14px 18px;border:0.5px solid #e2e8f0;">
<p style="font-size:13px;color:#64748b;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">Geez on AI는</strong> 매일 AI에 관련된 최신 내용들을 업데이트하며, 모든 포스팅은 Claude를 이용해 자동으로 생성됩니다 🤖</p>
</div>

[어투] 친근한 존댓말(~요, ~어요), 독자에게 직접 말하는 느낌, 어렵지 않게
[분량] 태그 제외 텍스트 기준 800~1200자
[절대 금지] 스타일/색상/구조 변경 금지, 마크다운 금지, 코드블록 금지, 한 <p>에 3문장 이상 금지
[프롬프트 템플릿] 반드시 실제로 복붙해서 쓸 수 있는 구체적인 내용으로 작성할 것. 예시가 아닌 실전용."""


def generate_post(topics):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    main_topic = topics[0] if topics else "AI 자동화"
    ref_topics = ', '.join(topics[1:3]) if len(topics) > 1 else ""
    topic_str = main_topic + (f" (관련 트렌드: {ref_topics})" if ref_topics else "")
    user_prompt = USER_PROMPT_TEMPLATE.format(topic=topic_str)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    raw = message.content[0].text.strip()

    title_match = re.search(r"TITLE:\s*(.+)", raw)
    labels_match = re.search(r"LABELS:\s*(.+)", raw)
    html_match = re.search(r"HTML:\s*([\s\S]+)", raw)

    title = title_match.group(1).strip() if title_match else "AI 자동화 가이드 2026"
    labels = [l.strip() for l in labels_match.group(1).split(',')] if labels_match else ['AI활용법', 'ChatGPT', 'AI입문']
    html = html_match.group(1).strip() if html_match else raw

    # 이미지 생성 — 인트로 내용 기반 캐릭터 일러스트
    img_prompt = generate_image_prompt(client, title, topic_str)
    print(f"이미지 프롬프트: {img_prompt}")
    img_src = get_image_base64(img_prompt)

    if img_src:
        img_tag = f'<img src="{img_src}" alt="{title}" style="width:100%;max-width:800px;height:auto;margin:0 0 28px;border-radius:10px;" />'
        # "[이미지 자리 — 코드에서 자동 삽입됨]" 플레이스홀더를 이미지로 교체
        html = html.replace("[이미지 자리 — 코드에서 자동 삽입됨]", img_tag)
        # 플레이스홀더가 없으면 글 맨 앞에 삽입
        if img_tag not in html:
            html = img_tag + "\n" + html
    else:
        html = html.replace("[이미지 자리 — 코드에서 자동 삽입됨]", "")
        print("이미지 생성 실패 — 이미지 없이 포스팅 진행")

    return title, html, labels


def post_to_blogger(access_token, title, content, labels):
    url = f'https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/'
    data = json.dumps({
        'kind': 'blogger#post',
        'title': title,
        'content': content,
        'labels': labels
    }).encode()
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
    title, html_content, labels = generate_post(topics)
    print(f"제목: {title}")
    print(f"라벨: {labels}")
    access_token = get_access_token()
    post_to_blogger(access_token, title, html_content, labels)
    print("완료!")


if __name__ == '__main__':
    main()
