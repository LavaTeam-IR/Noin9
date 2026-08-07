#!/usr/bin/env python3
"""
اسکرپ آخرین پیام‌های چند کانال پابلیک تلگرام از صفحه‌ی پیش‌نمایش
https://t.me/s/<channel_username>
بدون نیاز به بات یا اکانت شخصی.

برای هر کانال:
  - یک فایل <channel>.txt با ۲۰ پیام متنی آخر (هر بار کامل بازنویسی می‌شه)
  - یک پوشه media/<channel>/ با فایل‌های مدیای ۲۰ پیام آخر (قدیمی‌ها پاک می‌شن)
"""

import os
import re
import time
import mimetypes
import requests
from bs4 import BeautifulSoup

CHANNELS_FILE = "channels.txt"
MEDIA_DIR = "media"
LAST_N = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def load_channels(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip().lstrip("@") for line in f if line.strip() and not line.startswith("#")]


def clean_text(el):
    for br in el.find_all("br"):
        br.replace_with("\n")
    text = el.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def extract_bg_url(style):
    if not style:
        return None
    m = re.search(r"url\((['\"]?)(.*?)\1\)", style)
    return m.group(2) if m else None


def parse_messages(html, n=LAST_N):
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.tgme_widget_message")
    if not blocks:
        return []

    blocks = blocks[-n:]
    parsed = []

    for block in blocks:
        data_post = block.get("data-post", "")
        msg_id = data_post.split("/")[-1] if "/" in data_post else data_post

        time_el = block.select_one(".tgme_widget_message_date time")
        date_str = time_el.get("datetime", "") if time_el else ""

        text_el = block.select_one(".tgme_widget_message_text")
        text = clean_text(text_el) if text_el else ""

        media = []

        photo_el = block.select_one(".tgme_widget_message_photo_wrap")
        if photo_el:
            url = extract_bg_url(photo_el.get("style"))
            if url:
                media.append(("photo", url))

        video_el = block.select_one("video.tgme_widget_message_video")
        if video_el and video_el.get("src"):
            media.append(("video", video_el.get("src")))

        doc_el = block.select_one("a.tgme_widget_message_document_wrap")
        if doc_el and doc_el.get("href"):
            media.append(("document", doc_el.get("href")))

        parsed.append({
            "id": msg_id,
            "date": date_str,
            "text": text,
            "media": media,
        })

    return parsed


def fetch_channel_html(channel):
    url = f"https://t.me/s/{channel}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def download_media(channel, messages):
    channel_dir = os.path.join(MEDIA_DIR, channel)
    os.makedirs(channel_dir, exist_ok=True)

    kept_ids = set()

    for msg in messages:
        if not msg["media"]:
            continue
        for idx, (kind, url) in enumerate(msg["media"]):
            file_id = f"{msg['id']}_{idx}"
            kept_ids.add(file_id)

            # اگه فایلی با همین آیدی از قبل هست، دوباره دانلود نکن
            existing = [f for f in os.listdir(channel_dir) if f.startswith(file_id + ".")]
            if existing:
                continue

            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                r.raise_for_status()
                ext = mimetypes.guess_extension(r.headers.get("Content-Type", "").split(";")[0].strip()) or ".bin"
                if ext == ".jpe":
                    ext = ".jpg"
                path = os.path.join(channel_dir, f"{file_id}{ext}")
                with open(path, "wb") as f:
                    f.write(r.content)
            except requests.RequestException as e:
                print(f"  [!] خطا در دانلود مدیای پیام {msg['id']} از @{channel}: {e}")

    # پاکسازی فایل‌های قدیمی که دیگه جزو ۲۰ پیام آخر نیستن
    for fname in os.listdir(channel_dir):
        file_id = fname.rsplit(".", 1)[0]
        if file_id not in kept_ids:
            os.remove(os.path.join(channel_dir, fname))


def write_text_file(channel, messages):
    lines = [f"آخرین آپدیت: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
             f"کانال: @{channel}", "=" * 40, ""]

    if not messages:
        lines.append("[پیامی یافت نشد یا کانال خصوصی/نامعتبر است]")
    else:
        for msg in messages:
            lines.append(f"[{msg['date']}] (id:{msg['id']})")
            lines.append(msg["text"] if msg["text"] else "(بدون متن / فقط رسانه)")
            if msg["media"]:
                kinds = ", ".join(k for k, _ in msg["media"])
                lines.append(f"[پیوست: {kinds}]")
            lines.append("-" * 40)

    with open(f"{channel}.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    channels = load_channels(CHANNELS_FILE)
    os.makedirs(MEDIA_DIR, exist_ok=True)

    for channel in channels:
        print(f"در حال پردازش @{channel} ...")
        try:
            html = fetch_channel_html(channel)
            messages = parse_messages(html)
        except requests.RequestException as e:
            print(f"  [!] خطا در دریافت @{channel}: {e}")
            messages = []

        write_text_file(channel, messages)
        if messages:
            download_media(channel, messages)

    print("تمام شد.")


if __name__ == "__main__":
    main()
