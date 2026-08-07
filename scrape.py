#!/usr/bin/env python3
"""
اسکرپ آخرین پیام‌های چند کانال پابلیک تلگرام از صفحه‌ی پیش‌نمایش
https://t.me/s/<channel_username>
بدون نیاز به بات یا اکانت شخصی.

خروجی:
  - media/<channel>.txt : فقط ۲۰ پیام متنی عادی آخر (هر بار کامل بازنویسی می‌شه)
  - config/Sub1.txt, Sub2.txt, ... : خط‌هایی که با پیشوندهای کانفیگ VPN شروع بشن
    (هیچ‌وقت پاک نمی‌شن، فقط اضافه می‌شن، تکراری حذف می‌شه، هر فایل حداکثر ۶۰۰ خط)
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup

CHANNELS_FILE = "channels.txt"
MEDIA_DIR = "media"
CONFIG_DIR = "config"
LAST_N = 20
MAX_PER_CONFIG_FILE = 600

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

CONFIG_PREFIXES = (
    "vmess://", "vless://", "trojan://", "ss://", "shadowsocks://",
    "wg://", "wireguard://", "warp://", "reality://",
)


def load_channels(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip().lstrip("@") for line in f if line.strip() and not line.startswith("#")]


def clean_text(el):
    for br in el.find_all("br"):
        br.replace_with("\n")
    text = el.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


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

        parsed.append({"id": msg_id, "date": date_str, "text": text})

    return parsed


def fetch_channel_html(channel):
    url = f"https://t.me/s/{channel}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def split_message(msg):
    """پیام رو به دو دسته تقسیم می‌کنه: خط‌های کانفیگ و بقیه‌ی متن.
    اگه پیام حداقل یک خط کانفیگ داشته باشه، کل پیام «کانفیگ» حساب می‌شه
    و از فایل متنی عادی حذف می‌شه."""
    lines = msg["text"].splitlines()
    config_lines = [ln.strip() for ln in lines if ln.strip().lower().startswith(CONFIG_PREFIXES)]
    return config_lines


def write_media_text(channel, normal_messages):
    lines = [f"آخرین آپدیت: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
             f"کانال: @{channel}", "=" * 40, ""]

    if not normal_messages:
        lines.append("[پیامی یافت نشد یا کانال خصوصی/نامعتبر است]")
    else:
        for msg in normal_messages:
            lines.append(f"[{msg['date']}] (id:{msg['id']})")
            lines.append(msg["text"] if msg["text"] else "(بدون متن)")
            lines.append("-" * 40)

    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_DIR, f"{channel}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def load_existing_configs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(CONFIG_DIR) if re.match(r"^Sub\d+\.txt$", f)],
        key=lambda x: int(re.search(r"\d+", x).group())
    )
    existing = set()
    for fname in files:
        with open(os.path.join(CONFIG_DIR, fname), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    existing.add(line)
    return existing, files


def append_new_configs(new_configs, existing_set, files):
    to_add = []
    for cfg in new_configs:
        if cfg not in existing_set:
            existing_set.add(cfg)
            to_add.append(cfg)
    if not to_add:
        return 0

    if files:
        last_num = int(re.search(r"\d+", files[-1]).group())
        path = os.path.join(CONFIG_DIR, files[-1])
        with open(path, "r", encoding="utf-8") as fh:
            current_count = sum(1 for line in fh if line.strip())
    else:
        last_num = 1
        path = os.path.join(CONFIG_DIR, f"Sub{last_num}.txt")
        current_count = 0

    for cfg in to_add:
        if current_count >= MAX_PER_CONFIG_FILE:
            last_num += 1
            path = os.path.join(CONFIG_DIR, f"Sub{last_num}.txt")
            current_count = 0
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(cfg + "\n")
        current_count += 1

    return len(to_add)


def main():
    channels = load_channels(CHANNELS_FILE)
    existing_configs, config_files = load_existing_configs()

    all_new_configs = []

    for channel in channels:
        print(f"در حال پردازش @{channel} ...")
        try:
            html = fetch_channel_html(channel)
            messages = parse_messages(html)
        except requests.RequestException as e:
            print(f"  [!] خطا در دریافت @{channel}: {e}")
            messages = []

        normal_messages = []
        for msg in messages:
            config_lines = split_message(msg)
            if config_lines:
                all_new_configs.extend(config_lines)
            else:
                normal_messages.append(msg)

        write_media_text(channel, normal_messages)

    added = append_new_configs(all_new_configs, existing_configs, config_files)
    print(f"{added} کانفیگ جدید اضافه شد.")
    print("تمام شد.")


if __name__ == "__main__":
    main()
