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
            topics = [item.find('title').text for item in items if item.find('title') is not None]
            return topics
    except Exception as e:
        print(f"News fetch error: {e}")
        return ["Claude AI", "AI agent", "LLM"]


def generate_post(topics):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    topic_list = '\n'.join(f'- {t}' for t in topics)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": f"AI 뉴스 기반 한국어 블로그글 작성.\n토픽:\n{topic_list}\n\n<h1>제목</h1>으로 시작, <h2><p> 태그 사용, 800-1000자, 해시태그 5개 포함. 코드블록 없이 순수 HTML만 출력."}]
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
        return f"AI Report - {datetime.now().strftime('%Y.%m.%d')}"


def post_to_blogger(access_token, title, content):
    url = f'https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/'
    data = json.dumps({
        'kind': 'blogger#post',
        'title': title,
        'content': content,
        'labels': ['AI', 'Claude', 'LLM']
    }).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    })
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"Posted: {result.get('url', 'unknown')}")
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        print(f"Blogger Error {e.code}: {e.reason}")
        print(f"Error body: {error_body}")
        raise


def main():
    print(f"Start: {datetime.now()}")
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
