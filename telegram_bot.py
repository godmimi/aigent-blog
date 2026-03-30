import os
import json
import base64
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


def get_image_base64(keyword):
    """Try Pollinations first, fall back to Picsum."""
    # Try Pollinations
    clean = urllib.parse.quote(f"{keyword[:60]}, anime style, digital illustration, futuristic, vibrant colors")
    poll_url = f"https://image.pollinations.ai/prompt/{clean}?width=800&height=420&model=flux-anime&nologo=true"
    for url in [poll_url, "https://picsum.photos/800/420"]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=90) as resp:
                content_type = resp.headers.get('Content-Type', 'image/jpeg')
                data = resp.read()
                if data[:4] in (b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\x89PNG'):
                    mime = 'image/jpeg' if data[:2] == b'\xff\xd8' else 'image/png'
                    b64 = base64.b64encode(data).decode()
                    print(f"Image ok from: {url[:40]}")
                    return f"data:{mime};base64,{b64}"
        except Exception as e:
            print(f"Image error ({url[:40]}): {e}")
    return None


def generate_post(content, source_url):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Write an English blog post based on this article content:

{content}

Style rules (follow strictly):
- Title: short and punchy, max 8 words, no colons
- Open with a relatable "have you ever..." hook
- Friendly, conversational "you" tone. Short paragraphs (max 3 lines).
- Use icons instead of numbers: 🔹 for steps, ✅ for pros, ❌ for cons/mistakes, 💡 for tips
- Include one comparison or summary <table> with 2-3 columns
- Structure: Hook → What changed → 3 key points (with icons) → Mistakes (❌) → Tips (💡) → TL;DR summary box → CTA
- TL;DR box: <div style="background:#f0f4ff;padding:16px;border-radius:8px;margin:20px 0"><strong>TL;DR</strong><br>3 bullet points max</div>
- End with 5 hashtags

Output pure HTML only. Start with <h1>SEO title</h1>, use <h2><p> tags. 700-900 words. No code blocks."""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}]
    )
    html = message.content[0].text.strip()
    for tag in ['```html', '```']:
        if html.startswith(tag):
            html = html[len(tag):]
    if html.endswith('```'):
        html = html[:-3]
    html = html.strip()

    # Extract title for image prompt
    try:
        keyword = html[html.index('<h1>') + 4:html.index('</h1>')]
        keyword = urllib.parse.unquote(keyword).replace('<', '').replace('>', '')
    except ValueError:
        keyword = "AI technology"

    img_src = get_image_base64(keyword)
    if img_src:
        img_tag = f'<img src="{img_src}" alt="AI illustration" style="width:100%;max-width:800px;height:auto;margin:20px 0;border-radius:8px;" />'
        html = html.replace('</h1>', f'</h1>\n{img_tag}', 1)

    return html


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

        html = generate_post(content, text)
        title = extract_title(html)
        access_token = get_access_token()
        result = post_to_blogger(access_token, title, html)
        post_url = result.get('url', 'unknown')

        telegram_send(f"✅ Posted!\n📝 {title}\n🔗 {post_url}")
        print(f"Done: {post_url}")
        break  # process only one message per run


if __name__ == '__main__':
    main()
