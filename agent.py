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
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "state.json"
UA = "JARVIS-Pessoal/2.0 (monitor privado via Telegram)"
LABELS = {topic["category"]: topic["label"] for topic in CONFIG["topics"]}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def normalize(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def trusted(url, source=""):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    source = source.lower()
    return any(host == domain or host.endswith("." + domain) or domain in source
               for domain in CONFIG["trusted_domains"])


def relevant(text, keywords):
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def publication_date(value):
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo(CONFIG["timezone"]))
    except (TypeError, ValueError, OverflowError):
        return None


def fresh(value):
    published = publication_date(value)
    if not published:
        return False
    cutoff = datetime.now(ZoneInfo(CONFIG["timezone"])) - timedelta(
        days=CONFIG["freshness_days"]
    )
    return published >= cutoff


def item_id(item):
    value = (item["title"].lower() + "|" + item["link"]).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:20]


EVENT_RULES = [
    ("retificacao", "Retificação", ("retificação", "edital retificado", "retifica o edital")),
    ("nomeacao", "Nomeação", ("nomeação", "nomeados", "nomeado")),
    ("convocacao", "Convocação", ("convocação", "convocados", "convocado")),
    ("resultado", "Resultado", ("resultado final", "resultado preliminar", "resultado")),
    ("prova", "Prova", ("local de prova", "cartão de confirmação", "data da prova", "provas")),
    ("inscricoes", "Inscrições", ("inscrições abertas", "prazo de inscrição", "inscrição")),
    ("edital", "Edital publicado", ("edital publicado", "edital de abertura", "edital")),
    ("banca", "Banca definida", ("banca organizadora", "banca definida", "escolha da banca")),
    ("autorizacao", "Autorização", ("concurso autorizado", "autorização", "autorizado")),
]


def identify_competition(item):
    text = normalize(item["title"] + " " + item.get("summary", "")).lower()
    for competition in CONFIG.get("tracked_competitions", []):
        if any(alias.lower() in text for alias in competition["aliases"]):
            return competition["id"], competition["name"]
    return "", ""


def detect_event(item):
    text = normalize(item["title"] + " " + item.get("summary", "")).lower()
    for event_id, label, keywords in EVENT_RULES:
        if any(keyword in text for keyword in keywords):
            return event_id, label
    return "novidade", "Nova informação"


def detect_cycle(item):
    text = item["title"] + " " + item.get("summary", "")
    years = re.findall(r"\b20(?:2[4-9]|3\d)\b", text)
    return years[-1] if years else str(datetime.now(ZoneInfo(CONFIG["timezone"])).year)


def fact_signature(item):
    """Agrupa manchetes diferentes que comunicam essencialmente o mesmo fato."""
    text = normalize(item["title"]).lower()
    text = re.sub(r"\b(19|20)\d{2}\b", " ANO ", text)
    text = re.sub(r"\b\d[\d.,]*\b", " NUM ", text)
    text = re.sub(r"[^a-záàâãéêíóôõúç0-9 ]+", " ", text)
    words = [word for word in text.split() if len(word) > 2]
    value = " ".join(sorted(set(words))).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def enrich_item(item):
    competition_id, competition_name = identify_competition(item)
    event_id, event_label = detect_event(item)
    item["competition_id"] = competition_id
    item["competition_name"] = competition_name
    item["event_id"] = event_id
    item["event_label"] = event_label
    item["cycle"] = detect_cycle(item)
    item["fact_signature"] = fact_signature(item)
    return item


def item_quality(item):
    host = (urllib.parse.urlparse(item.get("link", "")).hostname or "").lower()
    official = any(
        host == domain or host.endswith("." + domain)
        for domain in CONFIG["trusted_domains"]
        if domain.endswith(".gov.br") or domain in {
            "gov.br", "in.gov.br", "ibge.gov.br", "eb.mil.br",
            "esa.eb.mil.br", "fgv.br", "fcc.org.br", "cesgranrio.org.br",
            "institutoaocp.org.br", "ibfc.org.br", "idecan.org.br",
            "cebraspe.org.br", "vunesp.com.br"
        }
    )
    return (2 if official else 0) + (1 if publication_date(item.get("published", "")) else 0)


def collapse_similar(items):
    """Mantém uma única fonte para cada concurso/etapa/fato."""
    chosen = {}
    for item in items:
        if item.get("competition_id"):
            key = (
                item["competition_id"],
                item.get("event_id", "novidade"),
                item.get("cycle", ""),
            )
        else:
            key = (
                item.get("category"),
                item.get("event_id", "novidade"),
                item.get("fact_signature", item_id(item)),
            )
        previous = chosen.get(key)
        if previous is None or item_quality(item) > item_quality(previous):
            chosen[key] = item
    return list(chosen.values())


def google_news_items(query, topic):
    params = urllib.parse.urlencode({
        "q": f"{query} when:{CONFIG['freshness_days']}d",
        "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"
    })
    root = ET.fromstring(fetch("https://news.google.com/rss/search?" + params))
    items = []
    for node in root.findall("./channel/item"):
        title = normalize(node.findtext("title"))
        description = normalize(node.findtext("description"))
        source_node = node.find("source")
        source = normalize(source_node.text if source_node is not None else "")
        source_url = source_node.attrib.get("url", "") if source_node is not None else ""
        published = normalize(node.findtext("pubDate"))
        if (
            fresh(published)
            and relevant(title + " " + description, topic["keywords"])
            and trusted(source_url, source)
        ):
            items.append({
                "category": topic["category"],
                "title": title,
                "link": normalize(node.findtext("link")),
                "source": source,
                "published": published,
                "summary": description
            })
    return items


def direct_page_items(page):
    url = page["url"]
    body = fetch(url).decode("utf-8", errors="ignore")
    topic = next((t for t in CONFIG["topics"] if t["category"] == page["category"]), None)
    if not topic:
        return []
    items = []
    pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    for href, label in re.findall(pattern, body, flags=re.I | re.S):
        title = normalize(label)
        link = urllib.parse.urljoin(url, html.unescape(href))
        if len(title) >= 18 and relevant(title, topic["keywords"]) and trusted(link):
            items.append({
                "category": page["category"], "title": title, "link": link,
                "source": urllib.parse.urlparse(link).hostname,
                "published": "", "summary": "Publicado em página oficial monitorada."
            })
    return items


def economy_snapshot():
    """Compara as duas últimas cotações PTAX de venda publicadas pelo Banco Central."""
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/2?formato=json"
    try:
        rows = json.loads(fetch(url))
        if len(rows) < 2:
            return ""
        previous, current = float(rows[-2]["valor"]), float(rows[-1]["valor"])
        change = ((current / previous) - 1) * 100 if previous else 0
        arrow = "subiu" if change > 0 else "caiu" if change < 0 else "ficou estável"
        return (f"Dólar PTAX: R$ {current:.4f} — {arrow} {abs(change):.2f}% "
                f"ante a cotação anterior. Fonte: Banco Central do Brasil.")
    except Exception as exc:
        print(f"AVISO cotação BCB: {exc}", file=sys.stderr)
        return ""


def telegram_send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError("O Telegram recusou a mensagem.")


def format_item(item):
    published = publication_date(item.get("published", ""))
    date = published.strftime("%d/%m/%Y") if published else "data não confirmada"
    title = html.escape(item["title"])
    link = html.escape(item["link"], quote=True)
    source = html.escape(item["source"] or "fonte oficial")
    text = (item["title"] + " " + item.get("summary", "")).lower()
    competition = html.escape(item.get("competition_name", ""))
    event = html.escape(item.get("event_label", "Nova informação"))

    if item.get("category") == "bancas":
        link_label = "Abrir página oficial da banca"
    elif "edital" in text:
        link_label = "Abrir edital ou página oficial"
    elif "inscri" in text:
        link_label = "Ver inscrições e prazo"
    elif "resultado" in text:
        link_label = "Consultar resultado oficial"
    elif "convoca" in text or "nomea" in text:
        link_label = "Consultar convocação oficial"
    else:
        link_label = "Ler informação na fonte"

    return (
        f"• <b>{title}</b>\n"
        + (f"Concurso: {competition}\n" if competition else "")
        + f"Situação: {event}\n"
        f"Fonte: {source} | Publicado: {date}\n"
        f"🔗 <a href=\"{link}\">{link_label}</a>"
    )


def load_state():
    if not STATE_FILE.exists():
        return {
            "version": 5, "seen": [], "daily_queue": [],
            "last_summary": "", "last_reports": {}, "competition_profiles": {}
        }
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state.setdefault("seen", [])
    state.setdefault("daily_queue", [])
    state.setdefault("last_summary", "")
    state.setdefault("last_reports", {})
    state.setdefault("competition_profiles", {})
    return state


def save_state(state):
    state["seen"] = state["seen"][-5000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def urgent(item):
    text = (item["title"] + " " + item.get("summary", "")).lower()
    return item["category"] in {"meus_concursos", "concursos_ba", "concursos_brasil", "bancas"} and any(
        keyword in text for keyword in CONFIG["urgent_keywords"]
    )


def register_competition_change(state, item):
    competition_id = item.get("competition_id")
    if not competition_id:
        return urgent(item)

    profiles = state.setdefault("competition_profiles", {})
    profile = profiles.setdefault(competition_id, {
        "name": item.get("competition_name", competition_id),
        "events": {},
        "last_update": "",
    })
    event_id = item.get("event_id", "novidade")
    event_key = f"{event_id}:{item.get('cycle', '')}"
    signature = item.get("fact_signature", item_id(item))
    previous = profile["events"].get(event_key)
    changed = not previous or (
        event_id == "retificacao" and previous.get("signature") != signature
    )

    if changed:
        profile["events"][event_key] = {
            "label": item.get("event_label", "Nova informação"),
            "cycle": item.get("cycle", ""),
            "signature": signature,
            "title": item["title"],
            "source": item.get("source", ""),
            "link": item["link"],
            "published": item.get("published", ""),
        }
        profile["last_update"] = datetime.now(
            ZoneInfo(CONFIG["timezone"])
        ).isoformat(timespec="seconds")
    return changed and (event_id != "novidade" or urgent(item))


def send_scheduled_report(report, queue, snapshot=""):
    categories = report["categories"]
    selected = collapse_similar([
        item for item in queue if item.get("category", "concursos_ba") in categories
    ])
    date = datetime.now(ZoneInfo(CONFIG["timezone"])).strftime("%d/%m/%Y")
    intro = f"JARVIS — {report['title']}\n{date}"
    if snapshot:
        telegram_send(intro + "\n\nRESUMO DO DÓLAR\n" + snapshot)
    elif not selected:
        telegram_send(intro + "\n\nNenhuma novidade relevante desde o relatório anterior.")

    for category in categories:
        items = [item for item in selected if item.get("category", "concursos_ba") == category]
        if not items:
            continue
        items = items[:CONFIG["max_report_items_per_category"]]
        for index in range(0, len(items), 3):
            part = items[index:index + 3]
            heading = f"JARVIS — {LABELS[category]}"
            telegram_send(heading + "\n\n" + "\n\n".join(format_item(item) for item in part))


def main():
    now = datetime.now(ZoneInfo(CONFIG["timezone"]))
    force_reports = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    state = load_state()
    bootstrap = state.get("version") != 5
    if bootstrap:
        state["daily_queue"] = []
    seen = set(state["seen"])
    candidates, errors = [], []

    for topic in CONFIG["topics"]:
        topic_items = []
        for query in topic["searches"]:
            try:
                topic_items.extend(google_news_items(query, topic))
            except Exception as exc:
                errors.append(f"{topic['label']}: {exc}")
        candidates.extend(topic_items[:CONFIG["max_items_per_topic"]])

    for page in CONFIG["official_pages"]:
        try:
            candidates.extend(direct_page_items(page))
        except Exception as exc:
            errors.append(f"{page['url']}: {exc}")

    unique = {item_id(item): enrich_item(item) for item in candidates}
    if bootstrap:
        for item in unique.values():
            register_competition_change(state, item)
    new_items = [(key, item) for key, item in unique.items() if key not in seen]

    for key, item in new_items:
        seen.add(key)
        if not bootstrap:
            state["daily_queue"].append(item)
        important_change = register_competition_change(state, item)
        if important_change and not bootstrap:
            telegram_send(
                f"JARVIS — ALERTA IMPORTANTE\n\n{format_item(item)}\n\n"
                "Confira prazos e requisitos no edital ou documento oficial."
            )

    today = now.date().isoformat()
    for report_key, report in CONFIG["report_schedule"].items():
        if not force_reports and (
            now.hour < report["hour"] or state["last_reports"].get(report_key) == today
        ):
            continue
        snapshot = economy_snapshot() if report_key == "economia" else ""
        send_scheduled_report(report, state["daily_queue"], snapshot)
        categories = set(report["categories"])
        state["daily_queue"] = [
            item for item in state["daily_queue"]
            if item.get("category", "concursos_ba") not in categories
        ]
        state["last_reports"][report_key] = today

    state["version"] = 5
    state["seen"] = list(seen)
    save_state(state)
    print(f"JARVIS: encontrados={len(unique)} novos={len(new_items)} erros={len(errors)}")
    for error in errors:
        print("AVISO", error, file=sys.stderr)


if __name__ == "__main__":
    main()
