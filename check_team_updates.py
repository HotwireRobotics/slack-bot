import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# 2026 Season Materials page (contains Game Manual + Team Update links)
FRC_SEASON_MATERIALS_URL = "https://www.firstinspires.org/resources/library/frc/season-materials"
STATE_FILE = "state.json"

TEAM_UPDATE_RE = re.compile(r"TeamUpdate(?:-Combined|s-combined)?|Team Update", re.IGNORECASE)

def fetch_links(url: str) -> list[tuple[str, str]]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    for a in soup.select("a[href]"):
        href = a.get("href")
        text = (a.get_text() or "").strip()
        if not href:
            continue
        # Only care about PDFs hosted on FIRST's blob storage or FIRST pages that point there
        if "blob.core.windows.net" in href and href.lower().endswith(".pdf"):
            links.append((text, href))
    return links

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen": []}

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)

def post_to_slack(webhook_url: str, message: str) -> None:
    payload = {"text": message}
    r = requests.post(webhook_url, json=payload, timeout=30)
    r.raise_for_status()

def main():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("Missing SLACK_WEBHOOK_URL env var", file=sys.stderr)
        sys.exit(2)

    all_pdf_links = fetch_links(FRC_SEASON_MATERIALS_URL)

    # Filter to likely “manual/team update” PDFs.
    # The season materials page includes "REBUILT Game Manual" and "Team Update 00" links. :contentReference[oaicite:3]{index=3}
    interesting = []
    for text, href in all_pdf_links:
        if TEAM_UPDATE_RE.search(text) or "Manual" in text or "Game Manual" in text:
            interesting.append((text, href))

    state = load_state()
    seen = set(state.get("seen", []))

    new_items = [(t, u) for (t, u) in interesting if u not in seen]

    if new_items:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"*FRC manual/team update change detected* ({now})"]
        for t, u in new_items:
            label = t if t else "New PDF"
            lines.append(f"• {label}: {u}")
            seen.add(u)

        post_to_slack(webhook_url, "\n".join(lines))
        state["seen"] = sorted(seen)
        save_state(state)
        print(f"Posted {len(new_items)} new item(s).")
    else:
        print("No changes.")

if __name__ == "__main__":
    main()
