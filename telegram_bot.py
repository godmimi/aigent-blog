import os
import re
import json
import urllib.request
import urllib.parse
from main import generate_post, fetch_x_content

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
        if len(text) < 30:
            continue

        # URL이면 크롤링
        if re.match(r'https?://', text):
            send("🔍 URL 분석 중...")
            content = fetch_x_content(text)
            url = text
            if not content:
                send("⚠️ 내용을 가져오지 못했어요. 텍스트를 직접 붙여넣어 주세요.")
                continue
        else:
            content = text
            url = ''

        send("✍️ 글 생성 중...")

        try:
            result = generate_post(content, url, 'auto')
        except Exception as e:
            send(f"❌ 글 생성 실패: {e}")
            continue

        # 미리보기 전송
        plain = strip_html(result['html_content'])
        send(f"📝 {result['title']}\n\n{plain[:1000]}")
        break


if __name__ == '__main__':
    main()
