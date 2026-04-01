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
        'LLM+꾸네팅+OR+AI+프롬프트+작성+OR+AI+활용법',
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
            return topics if topics else ["Claude AI", "AI 자동화", "LLM 활용법"]
    except Exception as e:
        print(f"News fetch error: {e}")
        fallbacks = [
            ["ChatGPT 처음 시작하는 법", "일반인을 위한 AI 사용법", "AI로 업무 시간 줄이기"],
            ["바이브코딩으로 앱 만들기", "코딩 모르는 다도 AI로 개발하기", "노코드 AI 도구 추천"],
            ["Claude vs ChatGPT 비교", "AI 툴 선택 방법", "2026년 AI 코핑 알감"],
            ["AI 이미지 생성 무료로 시작하기", "AI 그림 만드는 법", "미드저니 한국어 사용법"],
            ["Claude 설치부터 시작하기", "스마트폰으로 Claude 쓰는 법", "Anthropic 무료 플랜 활용법"],
            ["LLM 꾸네팅 10가지", "AI 프롬프트 잘 쓰는 법", "ChatGPT 활용 놓치고 있는 기능"],
            ["직장인을 위한 AI 툴 추천", "AI로 보고서 작성하기", "회의록 AI 자동 요약"],
            ["컨텐츠 AI 자동 제작", "블로그 AI로 운영하기", "SNS 콘텐츠 AI 자동화"],
        ]
        return random.choice(fallbacks)


def generate_image_prompt(client, title, summary):
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        messages=[{"role": "user", "content": f"""다음 블로그 글의 대표 이미지 프롬프트를 영어로 만들어줘.
조건:
- 글의 핵심 개념 1~2개만 시각화
- flat infographic illustration style
- isometric icons, soft blue and teal pastel colors
- white background, no text, no people, 2D vector art
- 30단어 이내

제목: {title}
요약: {summary[:200]}

프롬프트만 출력, 다른 말 없이."""}]
    )
    return msg.content[0].text.strip()


def get_image_base64(prompt):
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
글을 생성할 때 반드시 아래 HTML 컴포넌트 형식으로만 출력해.
마크다운 사용 금지. 오직 HTML만 출력해. 코드블록(```) 감싸지 마.

[출력 형식]
TITLE: [제목]
HTML:
[HTML 전체 내용]

[HTML 작성 규칙 - 반드시 준수]
1. 아래 제공된 컴포넌트 구조를 절대 변경하지 마. 색상, 스타일, 태그 구조 모두 그대로 사용.
2. 텍스트 내용만 채워 넣어.
3. 한 <p> 태그 안에 2문장을 초과하지 마. 문장이 길면 반드시 새 <p> 태그로 분리해.
4. 카드/단계 설명은 핵심만 간결하게. 한 항목에 4줄 이상 넣지 마.
5. 도입부는 문장 하나당 <p> 태그 하나씩 분리해.

[제목 형식 규칙]
- [핵심 주제] [N단계/N가지] - [결과나 혜택] [이모지] [2026년]
- N은 주제에 따라 3~7 사이에서 자유롭게 결정해. 5로 고정하지 마.
- 결과/혜택 표현을 매번 다양하게 써:
  예) 완전 정복하기, 무료로 시작하기, 10분 만에 세팅하기,
      비용 절반으로 줄이기, 초보자도 바로 쓰는 법,
      실전 적용 가이드, 완벽 세팅법, 한 번에 끝내기,
      업무 자동화 완성하기, 생산성 극대화하기
- 이모지는 매번 다르게 선택 (🚀 ⚡ 💡 🔥 ✅ 🎯 🛠️ 📌 중 하나)
- 반드시 하이픈(-)으로 앞뒤 구분
- 끝에 반드시 [2026년] 포함
- 같은 패턴 반복 금지. 매번 신선한 제목 만들기."""

USER_PROMPT_TEMPLATE = """다음 주제로 한국어 블로그 글을 HTML 형식으로 작성해줘.

주제: {topic}

아래 HTML 구조에 내용만 채워서 출력해. 구조와 스타일은 절대 바꾸지 마.

TITLE: [핵심 주제 + N단계/N가지] - [결과나 혜택] [주제에 맞는 이모지] [2026년]
HTML:

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 16px;">안녕하세요, AI 소식을 전해드리는 Geez 입니다😊</p>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[~하고 있지 않으신가요? 공감형 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 8px;">[두 번째 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[본문 연결 문장]</p>

<div style="border-left:3px solid #2563EB;padding:12px 16px;background:#f8fafc;margin-bottom:24px;">
<p style="font-size:14px;color:#1e293b;line-height:1.7;margin:0;">💡 <strong>핵심 포인트</strong> — [한 문장 핵심 요약]</p>
</div>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:28px;">
<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#f8fafc;">
<div style="display:flex;align-items:center;gap:8px;">
<span style="font-size:13px;font-weight:600;color:#1e293b;">&#128203; 목차</span>
<span style="font-size:11px;color:#2563EB;background:#EFF6FF;padding:1px 7px;border-radius:99px;border:0.5px solid #BFDBFE;">[N단계 가이드]</span>
</div>
</div>
<div style="padding:4px 0 8px;border-top:0.5px solid #e2e8f0;">
<div style="display:flex;align-items:center;gap:10px;padding:7px 16px;">
<div style="width:6px;height:6px;border-radius:50%;background:#2563EB;flex-shrink:0;"></div>
<span style="font-size:13px;color:#475569;">01. [단계 제목]</span>
</div>
[단계 수만큼 반복]
<div style="display:flex;align-items:center;gap:10px;padding:7px 16px;">
<div style="width:6px;height:6px;border-radius:50%;background:#D97706;flex-shrink:0;"></div>
<span style="font-size:13px;color:#475569;">&#9888; 주의사항과 흔한 실수 3가지</span>
</div>
</div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">[주제] N단계 마스터</h2>

<div style="display:flex;">
<div style="display:flex;flex-direction:column;align-items:center;width:28px;min-width:28px;">
<div style="width:8px;height:8px;border-radius:50%;background:#2563EB;margin-top:5px;flex-shrink:0;"></div>
<div style="width:1px;flex:1;background:#e2e8f0;min-height:16px;"></div>
</div>
<div style="padding:0 0 20px 12px;">
<h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 4px;">[단계 제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[첫 번째 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[두 번째 문장]</p>
</div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">실제 활용 예시 3가지</h2>

<div style="border:0.5px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#2563EB;border:0.5px solid #2563EB;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">사례 01</span>
<h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">🎯 [예시 제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[예시 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[예시 설명 두 번째 문장]</p>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항과 흔한 실수 3가지</h2>

<div style="border:1px solid #D97706;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff;">
<span style="font-size:11px;font-weight:600;color:#B45309;border:0.5px solid #D97706;padding:1px 8px;border-radius:99px;display:inline-block;margin-bottom:8px;">⚠ 주의 01</span>
<h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">[주의 제목]</h3>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[주의 설명 첫 문장]</p>
<p style="font-size:13px;color:#475569;line-height:1.7;margin:6px 0 0;">[주의 설명 두 번째 문장]</p>
</div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 8px;">[의미 있는 마무리 첫 문장]</p>
<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:0 0 24px;">[행동 유도 마무리 문장]</p>

<div style="background:#f8fafc;border-radius:10px;padding:14px 18px;border:0.5px solid #e2e8f0;">
<p style="font-size:13px;color:#64748b;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">Geez on AI는</strong> 매일 AI에 관련된 최신 내용들을 업데이트하며, 모든 포스팅은 Claude를 이용해 자동으로 생성됩니다 🤖</p>
</div>

[어투] 친근한 존댓말(~요, ~어요), 독자에게 직접 말하는 느낌
[분량] 태그 제외 텍스트 기준 700~1000자
[절대 금지] 스타일/색상/구조 변경 금지, 마크다운 금지, 코드블록 금지, 한 <p>에 3문장 이상 금지"""


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
    html_match = re.search(r"HTML:\s*([\s\S]+)", raw)
    title = title_match.group(1).strip() if title_match else "AI 자동화 가이드 2026"
    html = html_match.group(1).strip() if html_match else raw

    img_prompt = generate_image_prompt(client, title, topic_str)
    print(f"이미지 프롬프트: {img_prompt}")
    img_src = get_image_base64(img_prompt)

    if img_src:
        img_tag = f'<img src="{img_src}" alt="{title}" style="width:100%;max-width:800px;height:auto;margin:20px 0;border-radius:8px;" />'
        html = img_tag + "\n" + html
    else:
        print("이미지 생성 실패 — 이미지 없이 포스팅 진행")

    return title, html


def post_to_blogger(access_token, title, content):
    url = f'https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/'
    data = json.dumps({
        'kind': 'blogger#post',
        'title': title,
        'content': content,
        'labels': ['AI', 'Claude', 'LLM', 'Productivity', 'Tech Tips']
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
    title, html_content = generate_post(topics)
    print(f"제목: {title}")
    access_token = get_access_token()
    post_to_blogger(access_token, title, html_content)
    print("완료!")


if __name__ == '__main__':
    main()
