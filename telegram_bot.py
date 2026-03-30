import os
import json
import base64
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import anthropic

ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']
GOOGLE_CLIENT_ID = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
BLOG_ID = os.environ['BLOG_ID']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


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
    """Mark all updates as read so they won't be processed again."""
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
        import re
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:3000]
    except Exception as e:
        return None


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


def generate_image_prompt(client, title, summary):
    """Use Claude to create a relevant image prompt."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=60,
        messages=[{"role": "user", "content": f"Make an image prompt in English (max 30 words):\n- Visualize 1-2 core concepts from this blog\n- flat vector illustration style, soft pastel colors\n- no text, no faces, simple background\n\nTitle: {title}\nSummary: {summary[:200]}\n\nOutput prompt only."}]
    )
    return msg.content[0].text.strip()


def get_image_base64(prompt):
    """Try Pollinations first, fall back to Picsum."""
    clean = urllib.parse.quote(prompt)
    poll_url = f"https://image.pollinations.ai/prompt/{clean}?width=800&height=420&model=flux-anime&nologo=true"
    for url in [poll_url, "https://picsum.photos/800/420"]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=90) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                data = resp.read()
                if len(data) < 10000:
                    raise Exception(f"Image too small: {len(data)} bytes")
                if data[:2] not in (b'\xff\xd8', b'\x89P'):
                    raise Exception("Not a valid image")
                mime = 'image/jpeg' if data[:2] == b'\xff\xd8' else 'image/png'
                b64 = base64.b64encode(data).decode()
                print(f"Image ok from: {url[:40]} ({len(data)} bytes)")
                return f"data:{mime};base64,{b64}"
        except Exception as e:
            print(f"Image failed ({url[:40]}): {e}")
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
[타임라인 단계 블록 반복]

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">실제 활용 예시 3가지</h2>
[청록 카드 3개]

<h2 style="font-size:17px;font-weight:600;color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin:32px 0 16px;">주의사항과 흔한 실수 3가지</h2>
[앰버 카드 3개]

<p style="font-size:15px;line-height:1.8;color:#1e293b;margin:32px 0 24px;">[마무리 문단]</p>

<div style="background:#f8fafc;border-radius:12px;padding:16px 20px;border:0.5px solid #e2e8f0;"><p style="font-size:13px;color:#475569;margin:0;line-height:1.7;">📌 <strong style="color:#1e293b;">GeezonAI는</strong> 매일 AI 자동화 최신 내용을 업데이트합니다. 구독하고 놓치지 마세요! 🔔</p></div>

[어투] 친근한 존댓말, 독자에게 직접 말하는 느낌, 800~1200자(태그 제외)"""


def generate_post(content, source_url):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = USER_PROMPT_TEMPLATE.format(topic=content[:1500])

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    raw = message.content[0].text.strip()

    title_match = re.search(r"TITLE:\s*(.+)", raw)
    html_match = re.search(r"HTML:\s*([\s\S]+)", raw)
    title = title_match.group(1).strip() if title_match else "AI 자동화 가이드 2026"
    html = html_match.group(1).strip() if html_match else raw

    # Generate image and insert
    img_prompt = generate_image_prompt(client, title, content[:200])
    print(f"Image prompt: {img_prompt}")
    img_src = get_image_base64(img_prompt)
    if img_src:
        img_tag = f'<img src="{img_src}" alt="{title}" style="width:100%;max-width:800px;height:auto;margin:20px 0;border-radius:8px;" />'
        html = img_tag + "\n" + html

    return title, html


def extract_title(html):
    try:
        return html[html.index('<h1>') + 4:html.index('</h1>')].strip()
    except ValueError:
        return f"AI Report - {datetime.now().strftime('%Y.%m.%d')}"


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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    updates = get_updates()
    if not updates:
        print("No new messages.")
        return

    # Acknowledge all updates first to prevent re-processing
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
            print(f"Processing URL: {text}")
            telegram_send("📥 URL received! Generating post...")
            content = fetch_url_content(text)
            if not content:
                telegram_send("❌ Failed to fetch URL content.")
                continue
        else:
            if len(text) < 50:
                continue
            print(f"Processing text: {text[:50]}...")
            telegram_send("📥 Text received! Generating post...")
            content = text[:3000]

        title, html = generate_post(content, text)
        access_token = get_access_token()
        result = post_to_blogger(access_token, title, html)
        post_url = result.get('url', 'unknown')

        telegram_send(f"✅ Posted!\n📝 {title}\n🔗 {post_url}")
        print(f"Done: {post_url}")
        break  # process only one message per run


if __name__ == '__main__':
    main()
