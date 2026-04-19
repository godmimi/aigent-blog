import os
import re
import json
import urllib.request
from main import fetch_content, classify_type, generate_html_post, generate_text_post
from blogger import get_access_token, post_to_blogger

TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']


# ──────────────────────────────────────────
# Telegram API
# ──────────────────────────────────────────

def tg(method, **params):
    data = json.dumps(params).encode()
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}',
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def send(text):
    tg('sendMessage', chat_id=TELEGRAM_CHAT_ID, text=text[:4000])


def get_updates():
    try:
        result = tg('getUpdates', timeout=5)
        return result.get('result', [])
    except Exception as e:
        print(f"getUpdates 실패: {e}")
        return []


def acknowledge(updates):
    if not updates:
        return
    max_id = max(u['update_id'] for u in updates)
    tg('getUpdates', offset=max_id + 1, timeout=0)


def strip_html(html):
    return re.sub(r'<[^>]+>', '', html).strip()


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────

def main():
    updates = get_updates()
    if not updates:
        print("새 메시지 없음")
        return

    acknowledge(updates)

    for update in updates:
        msg = update.get('message', {})
        chat_id = str(msg.get('chat', {}).get('id', ''))
        text = msg.get('text', '').strip()

        if chat_id != TELEGRAM_CHAT_ID:
            continue
        if len(text) < 10:
            continue

        # URL이면 크롤링
        if re.match(r'https?://', text):
            send("🔍 URL 분석 중...")
            content = fetch_content(text)
            url = text
            if not content:
                send("⚠️ 내용을 가져오지 못했어요. 텍스트를 직접 붙여넣어 주세요.")
                continue
        else:
            content = text
            url = ''

        send("✍️ 글 생성 중...")

        try:
            post_type = classify_type(content)

            # 구글 블로그용 HTML 생성 → 자동 포스팅
            html_result = generate_html_post(content, url, post_type)
            try:
                access_token = get_access_token()
                post_url = post_to_blogger(
                    access_token,
                    html_result['title'],
                    html_result['html_content'],
                    '',  # 이미지 없음
                    html_result['labels']
                )
                send(f"✅ 구글 블로그 포스팅 완료!\n{post_url}")
            except Exception as e:
                send(f"⚠️ 구글 블로그 포스팅 실패: {e}")

            # 네이버 블로그용 텍스트 생성 → Telegram 전송
            text_post = generate_text_post(content, url, post_type)
            send(f"📝 [네이버 블로그용]\n\n{text_post}")

        except Exception as e:
            send(f"❌ 글 생성 실패: {e}")
            continue

        break


if __name__ == '__main__':
    main()
