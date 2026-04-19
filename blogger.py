import os
import json
import urllib.request
import urllib.parse
import urllib.error

BLOG_ID = os.environ['BLOG_ID']
GOOGLE_CLIENT_ID = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']


def get_access_token() -> str:
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': GOOGLE_REFRESH_TOKEN,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())['access_token']


def post_to_blogger(access_token: str, title: str, html_content: str, image_url: str, labels: list) -> str:
    """Blogger에 포스팅. 성공 시 포스트 URL 반환."""
    url = f'https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/'

    img_tag = (
        f'<img src="{image_url}" alt="{title}" '
        f'style="width:100%;max-width:800px;height:auto;margin:0 0 24px;border-radius:10px;" />\n'
    ) if image_url else ''

    post_data = {
        'title': title,
        'content': img_tag + html_content,
    }
    if labels:
        post_data['labels'] = labels

    data = json.dumps(post_data).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    })
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            post_url = result.get('url', '')
            print(f"Blogger 포스팅 완료: {post_url}")
            return post_url
    except urllib.error.HTTPError as e:
        print(f"Blogger 에러 {e.code}: {e.read().decode('utf-8', errors='replace')}")
        raise
