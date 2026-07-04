#!/usr/bin/env python3
"""Build the daily MIR Digest site from a structured digest JSON.

Usage:
    python scripts/build_daily.py digests/2026-07-05.json [--check-only]

Responsibilities (deterministic; no network, no heuristics):
  1. Validate the digest JSON produced by the Cowork scheduled agent.
  2. Render reports/<date>.html using the canonical style extracted from
     reports/2026-05-27.html.
  3. Run the PRODUCT_STANDARD.md section 9 QA gate. Fail -> exit 1, no writes.
  4. Append rows to data/papers.csv (idempotent per date+slot).
  5. Rebuild index.html (archive + calendar).

The agent owns: searching, selection, dedup, and all summary text.
This script owns: HTML structure, QA, and the archive.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html as html_lib
import json
import re
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
DATA_CSV = REPO_ROOT / "data" / "papers.csv"
CANONICAL_REPORT = REPORTS_DIR / "2026-05-27.html"
PRODUCT_STANDARD = REPO_ROOT / "PRODUCT_STANDARD.md"

PRODUCT_STANDARD_REQUIRED_MARKERS = [
    "## 1. Product Promise",
    "## 3. Information Architecture",
    "## 4. Paper Card Contract",
    "## 5. Long Summary Contract",
    "## 6. Interaction And Accessibility",
    "## 8. Legal And Source Hygiene",
    "## 9. Automation QA Gate",
]

TRACKS = {"mean_audio": "MeanAudio", "karaoke_jp": "karaoke-jp", "general_mir": "MIR"}
TRACK_HINTS = {"mean_audio": "貼近主線", "karaoke_jp": "可轉譯", "general_mir": "MIR 觀點"}

PAPER_REQUIRED_FIELDS = [
    "slot", "track", "title", "authors", "updated", "source_url", "tags",
    "quality", "tldr", "insight", "try_next", "problem", "method", "data",
    "findings", "limitations", "editor_note",
]

CSV_HEADER = [
    "date_sent", "slot", "item_type", "track", "title", "source_url",
    "arxiv_or_doi", "topic_tags", "quality_label",
]


def esc(s: object) -> str:
    return html_lib.escape(str(s or ""), quote=True)


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- validation

def load_standard() -> tuple[str, str]:
    if not PRODUCT_STANDARD.exists():
        die(f"product standard missing: {PRODUCT_STANDARD}")
    text = PRODUCT_STANDARD.read_text(encoding="utf-8-sig")
    missing = [m for m in PRODUCT_STANDARD_REQUIRED_MARKERS if m not in text]
    if missing:
        die("product standard incomplete; missing: " + ", ".join(missing))
    m = re.search(r"^Version:\s*(.+)$", text, flags=re.M)
    version = m.group(1).strip() if m else "unknown"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return version, digest


def load_digest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    date_s = str(data.get("date", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_s):
        die(f"digest date invalid: {date_s!r}")
    papers = data.get("papers")
    if not isinstance(papers, list) or len(papers) != 2:
        die("digest must contain exactly 2 papers")
    for i, p in enumerate(papers, 1):
        for field in PAPER_REQUIRED_FIELDS:
            if field not in p or p[field] in ("", None, []):
                die(f"paper {i} missing field: {field}")
        if p["track"] not in TRACKS:
            die(f"paper {i} invalid track: {p['track']}")
        tldr = str(p["tldr"])
        if not (20 <= len(tldr) <= 200):
            die(f"paper {i} tldr length {len(tldr)} outside 20-200 chars")
    msgs = data.get("discord_messages")
    if not isinstance(msgs, list) or not (1 <= len(msgs) <= 5):
        die("discord_messages must be a list of 1-5 strings")
    for i, m in enumerate(msgs, 1):
        if not isinstance(m, str) or not m.strip():
            die(f"discord message {i} empty")
        if len(m) > 1990:
            die(f"discord message {i} exceeds 1990 chars ({len(m)})")
        if "discord.com/api/webhooks" in m.lower():
            die(f"discord message {i} contains a webhook URL")
    repo = data.get("repo")
    if repo is not None:
        for field in ("full_name", "url", "description_zh", "why"):
            if not str(repo.get(field, "")).strip():
                die(f"repo missing field: {field}")
    return data


# ---------------------------------------------------------------- report css

EXTRA_REPORT_CSS = """
    .source-link,
    .details-toggle {
      display: inline-flex; align-items: center; justify-content: center; gap: 8px;
      font-family: var(--font-sans);
      font-size: 13px; font-weight: 500;
      padding: 9px 18px;
      border-radius: 9999px;
      border: 1px solid var(--border);
      background: var(--bg-surface);
      color: var(--text-primary);
      cursor: pointer;
      transition: background .18s, border-color .18s, color .18s, transform .08s;
      text-decoration: none;
    }
    .source-link {
      background: var(--teal-wash);
      border-color: var(--teal);
      color: var(--teal);
    }
    .source-link:hover { background: var(--teal-soft); text-decoration: none; }
    .details-toggle:hover { background: var(--bg-hover); }
    .details-toggle:active,
    .source-link:active { transform: translateY(1px); }
    body { overflow-x: hidden; }
    .canvas, .topbar-inner, footer, .digest-layout > *, .paper-card,
    .paper-card-body, .quick-read > *, .detail-section { min-width: 0; }
    .paper-card { overflow: hidden; }
    .paper-card h2, .one-line, .quick-read p, .detail-section p,
    .meta-list dd { overflow-wrap: anywhere; }
    .repo-pick {
      margin-top: 18px;
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow-card);
      padding: 18px;
      overflow: hidden;
    }
    .repo-pick .repo-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--text-tertiary);
      margin-bottom: 6px;
    }
    .repo-pick h2 {
      margin: 0 0 8px;
      font-family: var(--font-zh), var(--font-serif);
      font-size: 21px;
      font-weight: 500;
      line-height: 1.25;
    }
    .repo-pick h2 a { color: var(--text-primary); text-decoration: none; overflow-wrap: anywhere; }
    .repo-pick h2 a:hover { color: var(--accent); }
    .repo-pick p { margin: 0 0 8px; color: var(--text-secondary); font-family: var(--font-sans); font-size: 14px; overflow-wrap: anywhere; }
    .repo-pick .repo-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    @media (max-width: 640px) {
      .nav { width: 100%; margin-left: 0; overflow-x: auto; justify-content: flex-start; }
      .nav a, .nav-pill { flex-shrink: 0; }
      .hero, .digest-layout { max-width: 342px; margin-left: 0; margin-right: auto; }
      .paper-card { width: 100%; }
      .card-actions { align-items: flex-start; }
      .star-rating { width: 100%; margin-left: 0; justify-content: flex-end; }
      .star-rating button { width: 26px; height: 28px; }
    }
"""


def canonical_css() -> str:
    if not CANONICAL_REPORT.exists():
        die(f"canonical style source missing: {CANONICAL_REPORT}")
    html = CANONICAL_REPORT.read_text(encoding="utf-8")
    m = re.search(r"<style>\s*(.*?)\s*</style>", html, flags=re.S | re.I)
    if not m:
        die(f"canonical style block not found in {CANONICAL_REPORT}")
    return m.group(1).rstrip() + EXTRA_REPORT_CSS


# ---------------------------------------------------------------- report html

def source_label(url: str) -> str:
    parsed = urllib.parse.urlparse(url or "")
    return (parsed.netloc + parsed.path).strip("/") or url


def compact(s: str, limit: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "").strip())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "..."


def novelty_days(updated: str, date_s: str) -> int:
    try:
        return max(0, (dt.date.fromisoformat(date_s) - dt.date.fromisoformat(str(updated))).days)
    except ValueError:
        return 0


def paper_nav_item(slot: int, p: dict) -> str:
    return (
        f'          <li><a href="#paper-{slot}">\n'
        f'            <span class="nav-num">{slot:02d}</span>\n'
        f'            <span>{esc(compact(p["title"], 42))}'
        f'<span class="nav-track">{esc(TRACKS[p["track"]])}</span></span>\n'
        f"          </a></li>"
    )


def paper_card_html(date_s: str, p: dict) -> str:
    slot = int(p["slot"])
    authors_list = [str(a) for a in p["authors"]]
    authors = ", ".join(authors_list[:5]) or "arXiv 未列出"
    if len(authors_list) > 5:
        authors += f" 等 {len(authors_list)} 位"
    nd = novelty_days(p["updated"], date_s)
    tags = [str(t) for t in p["tags"]][:3]
    extra = max(0, len(p["tags"]) - len(tags))
    if extra:
        tags.append(f"+{extra}")
    tag_html = "\n            ".join(f'<span class="tag">{esc(t)}</span>' for t in tags)
    rel = p.get("relevance", {}) or {}
    rel_mean = int(rel.get("mean_audio", 0))
    rel_kara = int(rel.get("karaoke_jp", 0))
    score_text = f"MeanAudio {rel_mean} / karaoke {rel_kara}"
    panel_id = f"paper-{slot}-panel"
    return f"""
        <article class="paper-card" data-track="{esc(p['track'])}" id="paper-{slot}">
          <div class="paper-head">
            <div class="paper-number">{slot:02d}</div>
            <div class="paper-meta">
              <span class="track">{esc(TRACKS[p['track']])}</span>
              <span class="quality">{esc(p['quality'])}</span>
              <span class="freshness">{esc(str(p['updated']))} · {nd}d</span>
            </div>
          </div>
          <div class="paper-card-body">
          <h2><a href="{esc(p['source_url'])}" target="_blank" rel="noopener">{esc(p['title'])}</a></h2>
          <p class="one-line">{esc(p['tldr'])}</p>
          <div class="tag-row">
            <span class="track-hint">{esc(TRACK_HINTS[p['track']])}</span>
            {tag_html}
          </div>
          <div class="quick-read">
            <div>
              <span class="label">Insight</span>
              <p>{esc(p['insight'])}</p>
            </div>
            <div>
              <span class="label">Try next</span>
              <p>{esc(p['try_next'])}</p>
            </div>
          </div>
          </div>
          <div class="card-actions">
            <a class="source-link" href="{esc(p['source_url'])}" target="_blank" rel="noopener">Open Paper &#8599;</a>
            <button class="details-toggle" type="button" aria-expanded="false" aria-controls="{panel_id}">展開摘要與實驗建議</button>
            <div class="star-rating" data-paper-id="{esc(date_s)}-{slot}" aria-label="Rate this paper">
              <span class="star-label">重要度</span>
              <button type="button" data-value="1" aria-label="1 star">&#9733;</button>
              <button type="button" data-value="2" aria-label="2 stars">&#9733;</button>
              <button type="button" data-value="3" aria-label="3 stars">&#9733;</button>
              <button type="button" data-value="4" aria-label="4 stars">&#9733;</button>
              <button type="button" data-value="5" aria-label="5 stars">&#9733;</button>
            </div>
          </div>
          <div class="details-panel" id="{panel_id}">
            <div class="detail-grid">
              <section class="detail-section" data-standard-section="problem">
                <h3>Problem</h3>
                <p>{esc(p['problem'])}</p>
              </section>
              <section class="detail-section" data-standard-section="method">
                <h3>Method</h3>
                <p>{esc(p['method'])}</p>
              </section>
              <section class="detail-section" data-standard-section="data">
                <h3>Data</h3>
                <p>{esc(p['data'])}</p>
              </section>
              <section class="detail-section" data-standard-section="findings">
                <h3>Findings</h3>
                <p>{esc(p['findings'])}</p>
              </section>
              <section class="detail-section" data-standard-section="limitations">
                <h3>Limitations</h3>
                <p>{esc(p['limitations'])}</p>
              </section>
              <section class="detail-section" data-standard-section="editor-note">
                <h3>Editor Note</h3>
                <p>{esc(p['editor_note'])}</p>
              </section>
              <section class="detail-section" data-standard-section="metadata">
                <h3>Metadata</h3>
                <dl class="meta-list">
                  <div><dt>Authors</dt><dd>{esc(authors)}</dd></div>
                  <div><dt>Source</dt><dd><a href="{esc(p['source_url'])}">{esc(source_label(p['source_url']))}</a></dd></div>
                  <div><dt>Relevance</dt><dd>{esc(score_text)} · max {max(rel_mean, rel_kara)}</dd></div>
                </dl>
              </section>
            </div>
          </div>
        </article>
    """


def repo_section_html(repo: dict | None) -> str:
    if not repo:
        return ""
    stars = repo.get("stars")
    star_html = f'<span class="tag">★ {esc(stars)}</span>' if stars is not None else ""
    updated = repo.get("updated", "")
    updated_html = f'<span class="tag">更新 {esc(updated)}</span>' if updated else ""
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in (repo.get("tags") or [])[:3])
    return f"""
    <section class="repo-pick" aria-label="GitHub pick">
      <div class="repo-eyebrow">GitHub pick of the day</div>
      <h2><a href="{esc(repo['url'])}" target="_blank" rel="noopener">{esc(repo['full_name'])}</a></h2>
      <div class="repo-meta">{star_html}{updated_html}{tags}</div>
      <p>{esc(repo['description_zh'])}</p>
      <p><strong>為什麼相關:</strong>{esc(repo['why'])}</p>
      <div class="card-actions">
        <a class="source-link" href="{esc(repo['url'])}" target="_blank" rel="noopener">Open Repo &#8599;</a>
      </div>
    </section>
    """


REPORT_JS = """
    const cards = Array.from(document.querySelectorAll('.paper-card'));
    const RATINGS_KEY = 'mir-ratings';
    function loadRatings() {
      try { return JSON.parse(localStorage.getItem(RATINGS_KEY)) || {}; } catch { return {}; }
    }
    function saveRating(paperId, value) {
      const ratings = loadRatings();
      if (value === 0) delete ratings[paperId];
      else ratings[paperId] = value;
      localStorage.setItem(RATINGS_KEY, JSON.stringify(ratings));
    }
    function applyStars(widget, filled) {
      widget.querySelectorAll('button[data-value]').forEach(btn => {
        const value = parseInt(btn.dataset.value);
        btn.classList.toggle('filled', value <= filled);
        btn.classList.remove('preview');
      });
      const card = widget.closest('.paper-card');
      card.classList.toggle('is-rated', filled > 0);
      card.classList.toggle('is-important', filled >= 3);
    }
    function initStarWidget(widget) {
      const paperId = widget.dataset.paperId;
      applyStars(widget, loadRatings()[paperId] || 0);
      const buttons = widget.querySelectorAll('button[data-value]');
      buttons.forEach(btn => {
        btn.addEventListener('mouseenter', () => {
          const value = parseInt(btn.dataset.value);
          buttons.forEach(b => {
            const other = parseInt(b.dataset.value);
            b.classList.remove('filled');
            b.classList.toggle('preview', other <= value);
          });
        });
        btn.addEventListener('click', () => {
          const value = parseInt(btn.dataset.value);
          const previous = loadRatings()[paperId] || 0;
          const next = previous === value ? 0 : value;
          saveRating(paperId, next);
          applyStars(widget, next);
        });
      });
      widget.addEventListener('mouseleave', () => {
        applyStars(widget, loadRatings()[paperId] || 0);
      });
    }
    document.querySelectorAll('.star-rating').forEach(initStarWidget);
    function toggleCard(card) {
      const isOpen = card.classList.toggle('is-open');
      const btn = card.querySelector('.details-toggle');
      btn.setAttribute('aria-expanded', String(isOpen));
      btn.textContent = isOpen ? '收合' : '展開摘要與實驗建議';
    }
    document.querySelectorAll('.details-toggle').forEach(btn => {
      btn.addEventListener('click', () => toggleCard(btn.closest('.paper-card')));
    });
    document.querySelectorAll('.paper-card-body').forEach(body => {
      body.addEventListener('click', event => {
        if (event.target.closest('a, button, input, .card-actions, .star-rating')) return;
        toggleCard(body.closest('.paper-card'));
      });
    });
    document.querySelectorAll('.paper-nav-list a').forEach(link => {
      link.addEventListener('click', event => {
        event.preventDefault();
        const target = document.querySelector(link.getAttribute('href'));
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          target.style.borderColor = 'var(--accent)';
          target.style.boxShadow = '0 0 0 4px var(--accent-tint)';
          setTimeout(() => {
            target.style.borderColor = '';
            target.style.boxShadow = '';
          }, 1500);
        }
      });
    });
"""


def render_report(digest: dict, std_version: str, std_digest: str) -> str:
    date_s = digest["date"]
    papers = sorted(digest["papers"], key=lambda p: int(p["slot"]))
    style_css = canonical_css()
    cards_html = "\n".join(paper_card_html(date_s, p) for p in papers)
    nav_html = "\n".join(paper_nav_item(int(p["slot"]), p) for p in papers)
    repo_html = repo_section_html(digest.get("repo"))
    generated_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime(
        "%Y-%m-%d %H:%M:%S Asia/Taipei"
    )
    return f"""<!doctype html>
<html lang="zh-Hant" data-standard-version="{esc(std_version)}" data-standard-digest="{esc(std_digest)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="mir-digest-product-standard" content="{esc(std_version)}:{esc(std_digest)}">
  <title>MIR Paper Digest - {esc(date_s)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,500;0,600;1,400&family=Inter+Tight:wght@400;500;600&family=Noto+Serif+TC:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
{style_css}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <a class="brand" href="../index.html" aria-label="MIR Paper Digest home">
        <span class="brand-dot"></span>
        MIR Paper Digest
        <span class="sub">Daily Brief</span>
      </a>
      <nav class="nav" aria-label="Site navigation">
        <a class="nav-pill active" href="#">{esc(date_s)}</a>
        <a class="nav-pill" href="../index.html">All Issues</a>
        <span class="issue-badge">2 papers</span>
      </nav>
    </div>
  </div>
  <main class="canvas">
    <section class="hero">
      <div>
        <p class="eyebrow">Daily research brief · {esc(date_s)}</p>
        <h1>每日 MIR 論文<em>精選</em></h1>
        <p class="subtitle">近期主線往 Music Flamingo、歌詞辨識、JPOP 與卡拉 OK 靠攏;今天先看最能轉成下一個小實驗的兩篇。</p>
      </div>
    </section>
    <section class="digest-layout">
      <aside class="paper-nav" aria-label="Paper navigation">
        <div class="paper-nav-title">Papers</div>
        <ol class="paper-nav-list">
{nav_html}
        </ol>
      </aside>
      <div class="cards" aria-label="論文卡片">
{cards_html}
      </div>
    </section>
{repo_html}
    <details class="footnote">
      <summary>閱讀順序與篩選原則</summary>
      <div class="footnote-body">
        <span><strong>1.</strong> 近期主線:Music Flamingo、歌詞辨識、JPOP、卡拉 OK 與 karaoke-jp。</span>
        <span><strong>2.</strong> 生成主線仍保留:text-to-audio/music、flow、caption、codec、評估與 reward alignment。</span>
        <span><strong>3.</strong> 只收高品質:新穎度、重要性、baseline、資料與可落地性一起看。</span>
      </div>
    </details>
  </main>
  <footer>Generated by the MIR digest automation · Product standard {esc(std_version)} · {esc(std_digest)} · {esc(generated_at)}</footer>
  <script>
{REPORT_JS}
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------- QA gate

def qa_gate(html_text: str) -> None:
    failures: list[str] = []
    if ("discord.com/api/" + "webhooks") in html_text.lower():
        failures.append("HTML contains a Discord webhook URL")
    if re.search(r"\b[A-Za-z]:\\\\?", html_text):
        failures.append("HTML contains a local Windows path")
    if re.search(r"gh[pousr]_[A-Za-z0-9]{20,}", html_text):
        failures.append("HTML contains something that looks like a GitHub token")
    if html_text.count('class="paper-card"') != 2:
        failures.append("HTML must contain exactly two paper cards")
    required = [
        "閱讀順序",
        'class="tag-row"',
        'class="quality"',
        'class="freshness"',
        'class="one-line"',
        'class="source-link"',
        'class="details-toggle"',
        'aria-expanded="false"',
        "aria-controls=",
        "@media print",
        "@media (max-width: 640px)",
        "mir-digest-product-standard",
        'class="paper-nav"',
        'class="paper-card-body"',
        "Insight",
        "Try next",
    ]
    failures += [f"missing marker: {m}" for m in required if m not in html_text]
    for section in ["problem", "method", "data", "findings", "limitations", "editor-note"]:
        n = html_text.count(f'data-standard-section="{section}"')
        if n != 2:
            failures.append(f"section '{section}' must appear once per card; found {n}")
    for label in ("Insight", "Try next"):
        pattern = rf'<span class="label">{label}</span>\s*<p>(.*?)</p>'
        values = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", v)).strip()
                  for v in re.findall(pattern, html_text, flags=re.S)]
        if len(values) != 2:
            failures.append(f"quick-read '{label}' must appear once per card; found {len(values)}")
        elif len(set(values)) != 2:
            failures.append(f"quick-read '{label}' must be paper-specific; duplicates found")
    if failures:
        die("QA gate failed:\n- " + "\n- ".join(failures))


# ---------------------------------------------------------------- papers.csv

def append_papers_csv(digest: dict) -> None:
    DATA_CSV.parent.mkdir(parents=True, exist_ok=True)
    existing: set[tuple[str, str, str]] = set()
    rows: list[dict[str, str]] = []
    if DATA_CSV.exists():
        with DATA_CSV.open("r", newline="", encoding="utf-8-sig") as f:
            rows = [dict(r) for r in csv.DictReader(f)]
            existing = {(r.get("date_sent", ""), r.get("slot", ""), r.get("item_type", "paper")) for r in rows}
    date_s = digest["date"]
    new_rows: list[dict[str, str]] = []
    for p in digest["papers"]:
        key = (date_s, str(p["slot"]), "paper")
        if key in existing:
            continue
        new_rows.append({
            "date_sent": date_s,
            "slot": str(p["slot"]),
            "item_type": "paper",
            "track": p["track"],
            "title": str(p["title"]),
            "source_url": str(p["source_url"]),
            "arxiv_or_doi": str(p.get("doi") or p.get("arxiv_id") or ""),
            "topic_tags": "|".join(str(t) for t in p["tags"]),
            "quality_label": str(p["quality"]),
        })
    repo = digest.get("repo")
    if repo and (date_s, "0", "repo") not in existing:
        new_rows.append({
            "date_sent": date_s,
            "slot": "0",
            "item_type": "repo",
            "track": "github",
            "title": str(repo["full_name"]),
            "source_url": str(repo["url"]),
            "arxiv_or_doi": "",
            "topic_tags": "|".join(str(t) for t in (repo.get("tags") or [])),
            "quality_label": "",
        })
    if not new_rows:
        return
    write_header = not DATA_CSV.exists()
    with DATA_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER, quoting=csv.QUOTE_MINIMAL)
        if write_header:
            w.writeheader()
        for r in new_rows:
            w.writerow(r)


# ---------------------------------------------------------------- index page

def read_paper_rows(limit: int = 200) -> list[dict[str, str]]:
    if not DATA_CSV.exists():
        return []
    with DATA_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        raw = [dict(r) for r in csv.DictReader(f)]
    out: list[dict[str, str]] = []
    for r in raw:
        if r.get("item_type", "paper") != "paper":
            continue
        date_s = (r.get("date_sent") or "").strip()
        title = (r.get("title") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_s) or not title:
            continue
        try:
            slot_i = int(r.get("slot") or "9")
        except ValueError:
            slot_i = 9
        out.append({
            "date": date_s,
            "slot": f"{slot_i:02d}",
            "slot_sort": str(slot_i),
            "track": (r.get("track") or "mir").strip(),
            "title": title,
            "source_url": (r.get("source_url") or "").strip(),
            "tags": (r.get("topic_tags") or "").strip(),
            "href": f"reports/{date_s}.html",
        })
    out.sort(key=lambda x: (x["date"], -int(x["slot_sort"])), reverse=True)
    return out[:limit]


def report_links() -> list[tuple[str, str]]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    links = []
    for name in sorted((p.name for p in REPORTS_DIR.glob("*.html")), reverse=True):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", name):
            links.append((name[:-5], f"reports/{name}"))
    return links


def track_label(track: str) -> str:
    return {"mean_audio": "MeanAudio", "karaoke_jp": "karaoke-jp",
            "general_mir": "MIR", "github": "GitHub"}.get(track, track or "MIR")


def paper_rows_html(papers: list[dict[str, str]]) -> str:
    if not papers:
        return '<p class="empty" id="paper-empty">還沒有可列出的文章。下一次成功發布後會自動出現在這裡。</p>'
    items = []
    for p in papers:
        paper_id = f"{p['date']}-{int(p['slot_sort'])}"
        tags = [t for t in p["tags"].split("|") if t][:3]
        tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags)
        source_html = (
            f'<a class="secondary-link" href="{esc(p["source_url"])}" target="_blank" rel="noopener">Source</a>'
            if p["source_url"] else ""
        )
        items.append(f"""
          <article class="paper-row" data-paper-id="{esc(paper_id)}" data-date="{esc(p['date'])}">
            <div class="paper-row-meta">
              <span>{esc(p['date'])} / {esc(p['slot'])}</span>
              <span>{esc(track_label(p['track']))}</span>
              <span class="rating-chip" data-rating-for="{esc(paper_id)}">未評分</span>
            </div>
            <h2><a href="{esc(p['href'])}">{esc(p['title'])}</a></h2>
            <div class="paper-row-tags">{tag_html}</div>
            <div class="paper-row-actions">
              <a class="primary-link" href="{esc(p['href'])}">Open issue</a>
              {source_html}
            </div>
          </article>
        """)
    items.append('<p class="empty is-hidden" id="paper-empty">目前沒有 ★3 以上的重要文章。讀完報告後在文章卡片打星,這裡就會留下來。</p>')
    return "\n".join(items)


def issue_links_html(links: list[tuple[str, str]]) -> str:
    if not links:
        return '<p class="empty">尚無 issue。</p>'
    groups: dict[str, list[tuple[str, str]]] = {}
    for date_s, href in links:
        groups.setdefault(date_s[:7], []).append((date_s, href))
    blocks = []
    for month in sorted(groups, reverse=True):
        rows = "\n".join(
            f'<a class="issue-link" href="{esc(href)}"><span>{esc(date_s)}</span><strong>2 papers</strong></a>'
            for date_s, href in groups[month]
        )
        blocks.append(f"""
          <section class="month-block">
            <h3>{esc(month)}</h3>
            <div class="issue-list">{rows}</div>
          </section>
        """)
    return "\n".join(blocks)


def build_index(std_version: str, std_digest: str) -> None:
    links = report_links()
    latest_date = links[0][0] if links else ""
    latest_link = links[0][1] if links else ""
    latest_cta = (
        f'<a class="primary-cta" href="{esc(latest_link)}">閱讀最新 issue</a>'
        if latest_link else '<span class="primary-cta disabled">尚無 issue</span>'
    )
    papers = read_paper_rows()
    date_to_ids: dict[str, list[str]] = {}
    for p in papers:
        date_to_ids.setdefault(p["date"], []).append(f"{p['date']}-{int(p['slot_sort'])}")
    reports_data = [
        {"date": d, "href": h, "paperIds": date_to_ids.get(d, [])} for d, h in links
    ]
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    try:
        latest_dt = dt.date.fromisoformat(latest_date) if latest_date else now.date()
    except ValueError:
        latest_dt = now.date()
    index_tpl = (REPO_ROOT / "templates" / "index_template.html").read_text(encoding="utf-8")
    body = (
        index_tpl
        .replace("__STANDARD_VERSION__", esc(std_version))
        .replace("__STANDARD_DIGEST__", esc(std_digest))
        .replace("__LATEST_DATE__", esc(latest_date or "no issue"))
        .replace("__LATEST_CTA__", latest_cta)
        .replace("__PAPER_ROWS__", paper_rows_html(papers))
        .replace("__ISSUE_LINKS__", issue_links_html(links))
        .replace("__REPORTS_JSON__", json.dumps(reports_data, ensure_ascii=False).replace("</", "<\\/"))
        .replace("__TODAY__", esc(now.date().isoformat()))
        .replace("__CALENDAR_YEAR__", str(latest_dt.year))
        .replace("__CALENDAR_MONTH__", str(latest_dt.month - 1))
    )
    (REPO_ROOT / "index.html").write_text(body, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("digest_json", help="path to digests/YYYY-MM-DD.json")
    parser.add_argument("--check-only", action="store_true",
                        help="validate + render + QA in memory; write nothing")
    args = parser.parse_args(argv)

    std_version, std_digest = load_standard()
    digest = load_digest(Path(args.digest_json))
    html_text = render_report(digest, std_version, std_digest)
    qa_gate(html_text)

    if args.check_only:
        print(f"CHECK OK: {digest['date']} (standard {std_version} · {std_digest})")
        return 0

    date_s = digest["date"]
    out_path = REPORTS_DIR / f"{date_s}.html"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8", newline="\n")
    append_papers_csv(digest)
    build_index(std_version, std_digest)
    print(f"OK: wrote {out_path.relative_to(REPO_ROOT)}, updated data/papers.csv and index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
