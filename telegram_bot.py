import os
import json
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


def get_updates(offset=None):
    url = f"{TELEGRAM_API}/getUpdates?timeout=5"
    if offset:
        url += f"&offset={offset}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())['result']


def fetch_url_content(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        # strip tags roughly
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


def get_image_url(keyword):
    prompt = urllib.parse.quote(f"{keyword}, anime style, digital illustration, futuristic, vibrant colors")
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1200&height=630&model=flux-anime&nologo=true"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=60)
    except Exception as e:
        print(f"Image preload: {e}")
    return url


def generate_post(content, source_url):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Write an English blog post based on this article content:

{content}

Source: {source_url}

Style rules (follow strictly):
- Open with a relatable reader pain point or "have you ever..." scenario
- Friendly, conversational "you" tone — like a knowledgeable friend explaining, not a textbook
- Short sentences. No jargon unless explained.
- Structure: Hook paragraph → What changed/why it matters → 2-3 practical numbered steps or use cases → "Common Mistakes" section (2 mistakes + fixes) → "Pro Tips" section (2 tips) → Upbeat CTA closing paragraph
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

    keyword = html[4:html.index('</h1>')] if '<h1>' in html else "AI technology"
    img_tag = f'<img src="{get_image_url(keyword[:50])}" alt="{keyword}" style="width:100%;max-width:1200px;height:auto;margin:20px 0;border-radius:8px;" />'
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
            telegram_send(f"📥 URL received! Generating post...")
            content = fetch_url_content(text)
            if not content:
                telegram_send("❌ Failed to fetch URL content.")
                continue
        else:
            if len(text) < 50:
                continue
            print(f"Processing text: {text[:50]}...")
            telegram_send(f"📥 Text received! Generating post...")
            content = text[:3000]

        html = generate_post(content, text)
        title = extract_title(html)
        access_token = get_access_token()
        result = post_to_blogger(access_token, title, html)
        post_url = result.get('url', 'unknown')

        telegram_send(f"✅ Posted!\n📝 {title}\n🔗 {post_url}")
        print(f"Done: {post_url}")


if __name__ == '__main__':
    main()
