import os
import json
import base64
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import anthropic
import fal_client

ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']
GOOGLE_CLIENT_ID = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
BLOG_ID = os.environ['BLOG_ID']
FAL_KEY = os.environ['FAL_KEY']
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
    url = 'https://news.google.com/rss/search?q=Claude+AI+OR+AI+에이전트+OR+LLM+OR+Anthropic&hl=ko&gl=KR&ceid=KR:ko'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            items = root.findall('.//item')[:5]
            topics = [item.find('title').text for item in items if item.find('title') is not None]
            return topics
    except Exception as e:
        print(f"News fetch error: {e}")
        return ["Claude AI", "AI agent", "LLM trends"]


def generate_image_prompt(client, title, summary):
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        messages=[{"role": "user", "content": f"""다음 블로그 글의 대표 이미지 프롬프트를 영어로 만들어줘.
조건:
- 글의 핵심 개념 1~2개만 시각화
- manga illustration style, black and white line art
- 캐릭터가 해당 개념을 설명하거나 행동하는 장면
- 배경에 관련 아이콘/인포그래픽 요소 포함
- no color, clean white background
- 30단어 이내

제목: {title}
요약: {summary[:200]}

프롬프트만 출력, 다른 말 없이."""}]
    )
    return msg.content[0].text.strip()


def get_image_base64(prompt):
    if not CHARACTER_IMAGE_URL:
        print("CHARACTER_IMAGE_URL 환경변수가 없습니다.")
        return None
    try:
        os.environ['FAL_KEY'] = FAL_KEY
        result = fal_client.subscribe(
            "fal-ai/flux-pro/v1/redux",
            arguments={
                "image_url": CHARACTER_IMAGE_URL,
                "prompt": prompt,
                "num_images": 1,
                "image_size": "landscape_16_9",
                "guidance_scale": 3.5,
                "num_inference_steps": 28,
            }
        )
        image_url = result["images"][0]["url"]
        print(f"fal.ai 이미지 생성 성공: {image_url[:60]}")
        req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) < 10000:
                raise Exception(f"이미지 너무 작음: {len(data)} bytes")
            mime = 'image/jpeg' if data[:2] == b'\xff\xd8' else 'image/png'
            b64 = base64.b64encode(data).decode()
            print(f"이미지 변환 완료 ({len(data)} bytes)")
            return f"data:{mime};base64,{b64}"
    except Exception as e:
        print(f"fal.ai 실패: {e}")
        return None


SYSTEM_PROMPT = """너는 한국어 AI/테크 블로그 콘텐츠 전문 작가야.
글을 생성할 때 반드시 아래 HTML 컴포넌트 형식으로 출력해.
마크다운 사용 금지. 오직 HTML만 출력해. 코드블록(```) 감싸지 마.

[출력 형식]
TITLE: [제목]
HTML:
[HTML 전체 내용]"""

USER_PROMPT_TEMPLATE = """다음 주제로 한국어 블로그 글을 HTML 형식으로 작성해줘.

주제: {topic}

[출력 규칙]
1. 제목: 주제 + N가지/N단계 + 결과 + "2026" 포함
2. 글 전체를 아래 HTML 구조로 출력:

<div style="border-left:3px solid #0EA5E9;padding:12px 16px;background:#F0F9FF;margin-bottom:24px;"><p style="font-size:14px;color:#0C4A6E;line-height:1.7;margin:0;">💡 <strong>핵심 포인트</strong> — [한 문장 핵심 요약]</p></div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin-bottom:24px;">[~하고 있지 않으신가요? 로 시작하는 2~3문장 도입부]</p>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">[주제] N단계 마스터</h2>

<div style="display:flex;gap:0;margin-bottom:0;">
  <div style="display:flex;flex-direction:column;align-items:center;width:28px;min-width:28px;">
    <div style="width:10px;height:10px;border-radius:50%;background:#0EA5E9;margin-top:4px;flex-shrink:0;"></div>
    <div style="width:2px;flex:1;background:#E0F2FE;min-height:16px;"></div>
  </div>
  <div style="padding:0 0 22px 10px;">
    <h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">[단계 제목]</h3>
    <p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[단계 설명]</p>
  </div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">실제 활용 예시 3가지</h2>

<div style="display:flex;border:0.5px solid #e2e8f0;border-radius:12px;overflow:hidden;margin-bottom:10px;background:#fff;">
  <div style="width:4px;min-width:4px;background:#14B8A6;"></div>
  <div style="padding:13px 16px;">
    <span style="font-size:11px;font-weight:600;color:#0F766E;background:#CCFBF1;padding:2px 8px;border-radius:99px;display:inline-block;margin-bottom:6px;">사례 01</span>
    <h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">🎯 [예시 제목]</h3>
    <p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[예시 설명]</p>
  </div>
</div>

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항과 흔한 실수 3가지</h2>

<div style="display:flex;border:0.5px solid #e2e8f0;border-radius:12px;overflow:hidden;margin-bottom:10px;background:#fff;">
  <div style="width:4px;min-width:4px;background:#F59E0B;"></div>
  <div style="padding:13px 16px;">
    <span style="font-size:11px;font-weight:600;color:#92400E;background:#FEF3C7;padding:2px 8px;border-radius:99px;display:inline-block;margin-bottom:6px;">주의 01</span>
    <h3 style="font-size:14px;font-weight:600;color:#1e293b;margin:0 0 5px;">[주의 제목]</h3>
    <p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">[주의 설명]</p>
  </div>
</div>

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 24px;">[마무리 문단]</p>

<div style="background:#f8fafc;border-radius:12px;padding:16px 20px;border:0.5px solid #e2e8f0;"><p style="font-size:13px;color:#475569;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">GeezonAI는</strong> 매일 AI 자동화 최신 내용을 업데이트합니다. 구독하고 놓치지 마세요! 🔔</p></div>

[어투] 친근한 존댓말(~요, ~어요), 독자에게 직접 말하는 느낌, 800~1200자(태그 제외)
[절대 금지] 마크다운 사용 금지, 코드블록(```) 감싸기 금지"""


def generate_post(topics):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    main_topic = topics[0] if topics else "AI 자동화"
    ref_topics = ', '.join(topics[1:3]) if len(topics) > 1 else ""
    topic_str = main_topic + (f" (관련 트렌드: {ref_topics})" if ref_topics else "")
    user_prompt = USER_PROMPT_TEMPLATE.format(topic=topic_str)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
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
