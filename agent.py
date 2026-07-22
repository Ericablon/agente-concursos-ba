#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "state.json"
UA = "AgenteConcursosBA/1.0 (monitor pessoal; contato via repositorio)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def normalize(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def relevant(text):
    lower = text.lower()
    return any(word.lower() in lower for word in CONFIG["keywords"])


def trusted(url, source=""):
    host = urllib.parse.urlparse(url).hostname or ""
    source = source.lower()
    return any(host == d or host.endswith("." + d) or d in source
               for d in CONFIG["trusted_domains"])


def item_id(item):
    base = (item["title"].lower() + "|" + item["link"]).encode("utf-8")
    return hashlib.sha256(base).hexdigest()[:20]


def google_news_items(query):
    params = urllib.parse.urlencode({"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})
    root = ET.fromstring(fetch("https://news.google.com/rss/search?" + params))
    found = []
    for node in root.findall("./channel/item"):
        title = normalize(node.findtext("title"))
        description = normalize(node.findtext("description"))
        source_node = node.find("source")
        source = normalize(source_node.text if source_node is not None else "")
        source_url = source_node.attrib.get("url", "") if source_node is not None else ""
        link = normalize(node.findtext("link"))
        text = title + " " + description
        # A busca descobre a notícia; o domínio informado pelo feed determina a confiança.
        if relevant(text) and trusted(source_url, source):
            found.append({"title": title, "link": link, "source": source,
                          "published": normalize(node.findtext("pubDate")), "summary": description})
    return found


def direct_page_items(url):
    body = fetch(url).decode("utf-8", errors="ignore")
    found = []
    for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body,
                                  flags=re.I | re.S):
        title = normalize(label)
        link = urllib.parse.urljoin(url, html.unescape(href))
        if len(title) >= 18 and relevant(title) and trusted(link):
            found.append({"title": title, "link": link, "source": urllib.parse.urlparse(link).hostname,
                          "published": "", "summary": "Encontrado em página oficial monitorada."})
    return found


def telegram_send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text,
                                  "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError("O Telegram recusou a mensagem.")


def format_item(item):
    return f"• {item['title']}\nFonte: {item['source']}\n{item['link']}"


def load_state():
    if not STATE_FILE.exists():
        return {"seen": [], "daily_queue": [], "last_summary": ""}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    state["seen"] = state["seen"][-3000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    now = datetime.now(ZoneInfo(CONFIG["timezone"]))
    state = load_state()
    seen = set(state.get("seen", []))
    candidates = []
    errors = []
    for query in CONFIG["searches"]:
        try:
            candidates.extend(google_news_items(query))
        except Exception as exc:
            errors.append(f"Busca: {exc}")
    for url in CONFIG["official_pages"]:
        try:
            candidates.extend(direct_page_items(url))
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    unique = {}
    for item in candidates:
        unique[item_id(item)] = item
    new_items = [(key, value) for key, value in unique.items() if key not in seen]
    new_items = new_items[:CONFIG["max_items_per_run"]]

    # Na primeira execução, cria a base sem bombardear o usuário com notícias antigas.
    first_run = not STATE_FILE.exists()
    for key, item in new_items:
        seen.add(key)
        state.setdefault("daily_queue", []).append(item)
        urgent = any(word in (item["title"] + " " + item["summary"]).lower()
                     for word in CONFIG["urgent_keywords"])
        if urgent and not first_run:
            telegram_send("🚨 CONCURSOS BA — NOVA INFORMAÇÃO\n\n" + format_item(item) +
                          "\n\nConfirme os detalhes no documento oficial antes de agir.")

    today = now.date().isoformat()
    if now.hour >= CONFIG["daily_summary_hour"] and state.get("last_summary") != today:
        queue = state.get("daily_queue", [])
        if queue:
            chunks = [queue[i:i + 8] for i in range(0, len(queue), 8)]
            for index, chunk in enumerate(chunks, 1):
                heading = f"📋 RESUMO DIÁRIO — CONCURSOS DA BAHIA ({index}/{len(chunks)})"
                telegram_send(heading + "\n\n" + "\n\n".join(format_item(x) for x in chunk))
        else:
            telegram_send("📋 RESUMO DIÁRIO — CONCURSOS DA BAHIA\n\nNenhuma nova publicação relevante encontrada hoje.")
        state["daily_queue"] = []
        state["last_summary"] = today

    state["seen"] = list(seen)
    save_state(state)
    print(f"Encontrados={len(unique)} novos={len(new_items)} erros={len(errors)}")
    for error in errors:
        print("AVISO", error, file=sys.stderr)


if __name__ == "__main__":
    main()
