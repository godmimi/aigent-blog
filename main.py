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
    url = 'https://news.google.com/rss/search?q=Claude+AI+OR+AI+agent+OR+LLM+OR+Anthropic&hl=ko&gl=KR&ceid=KR:ko'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            items = root.findall('.//item')[:5]
            return [item.find('title').text for item in items if item.find('title') is not None]
    except Exception as e:
        print(f"News fetch error: {e}")
        return ["Claude AI latest update", "AI agent tips", "LLM trends"]


def generate_post(topics):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    topic_list = '\n'.join(f'- {t}' for t in topics)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Write a Korean blog post based on these AI news trends.

Topics:
{topic_list}

Requirements:
- Title: SEO-optimized Korean title using <h1>title</h1> on first line
- Length: 800-1000 characters
- Audience: general public interested in AI/tech
- Tone: friendly and professional
- Structure: intro, body (2-3 sections), conclusion
- End with 5 relevant hashtags

Output ONLY pure HTML without any markdown code blocks. Start with <h1> tag, use <h2> and <p> tags."""
        }]
    )
    html = message.content[0].text.strip()
    if html.startswith('```html'):
        html = html[7:]
    elif html.startswith('```'):
        html = html[3:]
    if html.endswith('```'):
        html = html[:-3]
    return html.strip()


def extract_title(html_content):
    try:
        start = html_content.index('<h1>') + 4
        end = html_content.index('</h1>')
        return html_content[start:end].strip()
    except ValueError:
        return f"AI Trend Report - {datetime.now().strftime('%Y.%m.%d')}"


def post_to_blogger(access_token, title, content):
    url = f'https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/'
    data = json.dumps({
        'kind': 'blogger#post',
        'title': title,
        'content': content,
        'labels': ['AI', 'Claude', 'LLM', 'tech']
    }).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    })
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"Posted: {result.get('url', 'unknown')}")
        return result


def main():
    print(f"Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    topics = get_trending_topics()
    print(f"Topics: {len(topics)}")
    html_content = generate_post(topics)
    title = extract_title(html_content)
    print(f"Title: {title}")
    access_token = get_access_token()
    post_to_blogger(access_token, title, html_content)
    print("Done!")


if __name__ == '__main__':
    main()
