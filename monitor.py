# -*- coding: utf-8 -*-
"""
위시켓 프로젝트 알리미 (GitHub Actions 버전)

- 환경변수에서 FILTER_URL, TELEGRAM_TOKEN, TELEGRAM_CHATID 읽음
  (GitHub Repository Secrets로 주입됨)
- seen.json 파일에 이미 알린 항목 ID 저장
  (워크플로우가 변경분을 자동 커밋해 다음 실행에서 중복 알림 방지)
"""
import os
import re
import sys
import json
import datetime

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, "seen.json")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def fetch_projects(url):
    """위시켓 필터 URL에서 프로젝트 목록을 추출."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    projects = []
    for card in soup.select("section.project-organic-info"):
        link = None
        for a in card.select('a[href*="/project/"]'):
            href = a.get("href", "")
            if re.search(r"/project/\d+/", href):
                if link is None or len(a.get_text(strip=True)) > len(link[1]):
                    link = (href, a.get_text(strip=True))
        if not link:
            continue
        pid = re.search(r"/project/(\d+)/", link[0]).group(1)
        text = card.get_text(" ", strip=True)
        status = "모집 중" if "모집 중" in text else "모집 마감"
        money = re.search(r"(예상 금액|월 금액)\s*([\d,]+\s*원)", text)
        projects.append({
            "id": pid,
            "title": link[1] or "(제목 없음)",
            "url": "https://www.wishket.com" + link[0],
            "status": status,
            "budget": (money.group(2) if money else "금액 미정"),
        })
    return projects


def telegram_send(token, chat_id, message):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message,
              "disable_web_page_preview": False},
        timeout=20,
    ).raise_for_status()


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2, sort_keys=True)


def main():
    print("=" * 58)
    print(" 위시켓 프로젝트 알리미 (GitHub Actions)")
    print(" 시각(UTC):", datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 58)

    filter_url = os.getenv("FILTER_URL", "").strip()
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHATID", "").strip()

    if not filter_url:
        print(" FILTER_URL 시크릿이 비어 있습니다."); sys.exit(1)
    live = bool(token and chat_id)

    try:
        projects = fetch_projects(filter_url)
    except Exception as e:
        print(f" 위시켓 페이지를 불러오지 못했습니다: {e}")
        sys.exit(0)  # 일시적 오류는 워크플로우 실패로 보지 않음
    print(f" 현재 목록 {len(projects)}건 확인")

    seen = load_seen()
    first_run = len(seen) == 0
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    new_open = []
    for p in projects:
        if p["id"] in seen:
            continue
        seen[p["id"]] = now
        if p["status"] == "모집 중" and not first_run:
            new_open.append(p)

    save_seen(seen)

    if first_run:
        print(f" 첫 실행 — {len(projects)}건 기준 등록(알림 없음).")
        if live:
            telegram_send(token, chat_id,
                          "✅ 위시켓 프로젝트 알리미가 GitHub Actions에서 동작합니다.\n"
                          "새 프로젝트가 뜨면 바로 알려드립니다.")
            print(" 설치 확인 메시지 전송 완료.")
        return

    if not new_open:
        print(" 새 모집 중 프로젝트 없음.")
        return

    print(f" 새 프로젝트 {len(new_open)}건 — 텔레그램 전송")
    for p in new_open:
        msg = (f"🔔 위시켓 새 프로젝트\n\n"
               f"{p['title']}\n"
               f"예상 금액: {p['budget']}\n"
               f"{p['url']}")
        if live:
            try:
                telegram_send(token, chat_id, msg)
            except Exception as e:
                print(f"   ! 전송 실패: {e}")
        print(f"   - {p['title']}")


if __name__ == "__main__":
    main()
