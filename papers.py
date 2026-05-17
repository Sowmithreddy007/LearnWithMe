import requests, os, time, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

TOKEN      = os.environ["TELEGRAM_TOKEN"]
CHAT_ID    = os.environ["CHAT_ID"]
OR_KEY     = os.environ["OPENROUTER_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]

MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]

SENT_FILE = "sent_papers.txt"

# ── Sent papers tracker ───────────────────────────────────────────────────────

def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_sent(ids):
    existing = load_sent()
    all_ids = existing | ids
    trimmed = list(all_ids)[-200:]
    with open(SENT_FILE, "w") as f:
        f.write("\n".join(trimmed))

# ── Telegram ──────────────────────────────────────────────────────────────────

def send(text):
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": chunk},
                timeout=15
            )
        except Exception as e:
            print(f"Telegram error: {e}")
        time.sleep(1)

# ── AI ────────────────────────────────────────────────────────────────────────

def ask_ai(prompt):
    system = (
        "You are a professional science communicator writing a research digest for a complete beginner. "
        "Rules you must follow without exception:\n"
        "1. Output ONLY the final formatted summary. No preamble, no meta-talk, no reasoning.\n"
        "2. Never start with phrases like 'Sure!', 'Here is', 'Let me', 'I will', 'Certainly'.\n"
        "3. Never use placeholder text. Write real content for every single section.\n"
        "4. Every technical term must be followed immediately by a plain English explanation in parentheses.\n"
        "5. If a number or benchmark is not mentioned in the abstract, write: 'Specific figures not disclosed in the abstract.'\n"
        "6. Write like a journalist at a science magazine — clear, confident, professional, beginner-friendly."
    )
    for model in MODELS:
        for attempt in range(2):
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OR_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 2000
                    },
                    timeout=90
                )
                data = r.json()
                if "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"].strip()
                    leak_signals = [
                        "let me ", "i will ", "i'll ", "here is ",
                        "sure!", "certainly!", "okay,", "the instruction",
                        "i need to", "we need to", "the user wants",
                        "i should ", "now i ", "first,"
                    ]
                    if any(s in content.lower()[:200] for s in leak_signals):
                        print(f"  {model} leaked reasoning — skipping")
                        break
                    print(f"  Model used: {model}")
                    return content
                else:
                    print(f"  {model} error: {data.get('error', {}).get('message', 'unknown')}")
                    break
            except Exception as e:
                print(f"  Attempt {attempt+1} failed: {e}")
                time.sleep(3)
    return None

# ── arXiv fetcher ─────────────────────────────────────────────────────────────

def fetch_arxiv(category, count=8):
    papers = []
    try:
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query=cat:{category}"
            "&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={count}"
        )
        resp = requests.get(url, timeout=30, headers={"User-Agent": "HermesBot/1.0"})
        content = resp.text
        for entry in content.split("<entry>")[1:]:
            title = abstract = link = published = ""
            author_list = []
            if "<title>" in entry:
                title = entry.split("<title>")[1].split("</title>")[0].strip().replace("\n", " ")
            if "<summary>" in entry:
                abstract = entry.split("<summary>")[1].split("</summary>")[0].strip().replace("\n", " ")
            if "<id>" in entry:
                link = entry.split("<id>")[1].split("</id>")[0].strip()
            if "<published>" in entry:
                published = entry.split("<published>")[1].split("</published>")[0].strip()[:10]
            for chunk in entry.split("<author>")[1:]:
                if "<name>" in chunk:
                    author_list.append(chunk.split("<name>")[1].split("</name>")[0].strip())
            authors = ", ".join(author_list[:3])
            if len(author_list) > 3:
                authors += " et al."
            if title and link:
                papers.append({
                    "title":     title,
                    "abstract":  abstract[:800],
                    "link":      link,
                    "authors":   authors,
                    "published": published
                })
    except Exception as e:
        print(f"arXiv error for {category}: {e}")
    return papers

# ── Prompts ───────────────────────────────────────────────────────────────────

def build_summary_prompt(num, total, paper, label="TODAY"):
    return (
        "You are a professional science communicator writing for a smart beginner "
        "who just started learning AI. Write a detailed, structured summary of this "
        "research paper. Every section must be fully written. "
        "No placeholders, no skipped sections, no meta-commentary. "
        "Output only the final summary, nothing else.\n\n"
        "PAPER DETAILS:\n"
        f"Title: {paper['title']}\n"
        f"Authors: {paper['authors']}\n"
        f"Date: {paper['published']}\n"
        f"Category: {paper['category']}\n"
        f"Abstract: {paper['abstract']}\n\n"
        "Write the summary using EXACTLY this structure and EXACTLY these markers. "
        "Do not change any symbol, emoji, or divider line:\n\n"
        f"PAPER {num} of {total} — {label}\n"
        f"{paper['title']}\n"
        f"Authors: {paper['authors']}\n"
        f"Category: {paper['category']} | Date: {paper['published']}\n\n"
        "IN PLAIN ENGLISH\n"
        "Write exactly 5 sentences in plain English for a curious 16-year-old with "
        "zero AI background. "
        "Sentence 1: what the researchers built or discovered. "
        "Sentence 2: what specific problem it solves. "
        "Sentence 3: how it works at the most basic level. "
        "Sentence 4: what makes it better than what existed before. "
        "Sentence 5: why an ordinary person should care.\n\n"
        "REAL-WORLD ANALOGY\n"
        "Write 2-3 sentences. Give one specific vivid analogy comparing the core "
        "mechanism of this research to something from daily life — food, sports, "
        "school, traffic, or medicine. The analogy must explain how it works, "
        "not just what topic it covers. Make it concrete and memorable.\n\n"
        "THE PROBLEM\n"
        "Write exactly 3 sentences. "
        "Sentence 1: what specific limitation existed in AI before this paper. "
        "Sentence 2: what goes wrong in real applications because of this gap — "
        "give a concrete example of failure. "
        "Sentence 3: why this problem was hard to solve before.\n\n"
        "THEIR APPROACH\n"
        "Write exactly 4 sentences. Every technical term must be immediately followed "
        "by a plain English explanation in parentheses — example: "
        "'transformer (an AI that reads text in overlapping chunks)'. "
        "Sentence 1: the core idea of their method. "
        "Sentence 2: how they built or trained it. "
        "Sentence 3: what makes their approach different from previous work. "
        "Sentence 4: one specific clever design choice that makes it work.\n\n"
        "RESULTS AND NUMBERS\n"
        "Write exactly 3 sentences. "
        "Sentence 1: the main achievement. "
        "Sentence 2: include specific numbers from the abstract if any exist and "
        "explain what they mean in plain terms — example: '94 percent accuracy means "
        "correct 94 times out of 100'. If no numbers exist write the qualitative "
        "improvement they describe. "
        "Sentence 3: how this compares to the previous best approach.\n\n"
        "WHO BENEFITS\n"
        "Name exactly 3 specific groups of real people. For each write one sentence "
        "on exactly how their work or life improves. Be concrete — write 'radiologists' "
        "not 'healthcare', 'high school students' not 'education', "
        "'warehouse engineers' not 'industry'.\n\n"
        "WHAT TO LEARN NEXT\n"
        "Give exactly 3 topics. Each on its own line:\n"
        "1. Topic Name — one sentence on why this topic helps understand this paper\n"
        "2. Topic Name — one sentence on why this topic helps understand this paper\n"
        "3. Topic Name — one sentence on why this topic helps understand this paper\n\n"
        f"Full paper: {paper['link']}"
    )
def build_weekly_overview_prompt(num_papers, weekly_text):
    return (
        "Write a weekly AI research digest for a complete beginner who just started "
        "learning AI. Be detailed, specific, and professional. "
        "No placeholders, no meta-commentary, output only the final text.\n\n"
        "Use exactly this structure:\n\n"
        "THIS WEEK IN AI RESEARCH\n\n"
        "BIGGEST THEMES\n"
        "Write 4-5 sentences describing the dominant research directions this week. "
        "Name specific topics — for example 'improving how language models reason "
        "through multi-step problems' or 'making object detection work in low-light "
        "conditions' — not vague phrases like 'AI improvements'. For each theme, "
        "briefly explain in plain English why researchers care about it.\n\n"
        "PAPER OF THE WEEK\n"
        "Name the single most impressive or important paper this week. Write 4 sentences: "
        "what it built or discovered, what problem it solves, what result it achieved, "
        "and why it stands above everything else published this week. "
        "Write as if recommending it to a curious friend over coffee.\n\n"
        "TREND TO WATCH\n"
        "Identify one specific technique or research direction appearing across multiple "
        "papers this week. Write 3 sentences: what it is in plain English, why multiple "
        "research groups are working on it simultaneously, and why a beginner learning "
        "AI right now should pay close attention to it.\n\n"
        "BY CATEGORY\n"
        "Write exactly one detailed sentence per category — not a vague summary but "
        "a specific description of what actually happened:\n"
        "AI: [specific development in general AI research this week]\n"
        "ML: [specific development in machine learning this week]\n"
        "NLP: [specific development in language AI this week]\n"
        "Computer Vision: [specific development in image and video AI this week]\n"
        "Robotics: [specific development in robotics research this week]\n\n"
        f"PAPERS THIS WEEK:\n{weekly_text[:5000]}"
    )

# ── HTML helpers ──────────────────────────────────────────────────────────────

def plain_to_html(text):
    if not text:
        return "<p style='color:#999;font-family:Arial,sans-serif;'>Content unavailable.</p>"

    # Section config: marker text -> (background color, text color, emoji)
    SECTION_STYLES = {
        "IN PLAIN ENGLISH":    ("#1a1a2e", "#f0c040", "💡"),
        "REAL-WORLD ANALOGY":  ("#1a4a2e", "#80ffb0", "🔁"),
        "WHAT TO LEARN NEXT":  ("#2e1a4a", "#c9b0ff", "📚"),
    }
    SUBSECTION_MARKERS = {
        "THE PROBLEM":         "#e74c3c",
        "THEIR APPROACH":      "#2980b9",
        "RESULTS AND NUMBERS": "#27ae60",
        "WHO BENEFITS":        "#e67e22",
    }

    lines = text.split("\n")
    parts = []

    for line in lines:
        s = line.strip()
        if not s:
            parts.append("<div style='height:6px;'></div>")
            continue

        # Full paper link
        if s.startswith("Full paper:"):
            link = s.replace("Full paper:", "").strip()
            parts.append(
                "<div style='margin:22px 0 0;padding-top:16px;"
                "border-top:1px solid #e8e4d9;'>"
                "<a href='" + link + "' "
                "style='display:inline-block;background:#1a1a2e;color:#c9a227;"
                "font-family:Arial,sans-serif;font-size:9px;font-weight:bold;"
                "letter-spacing:2px;padding:10px 22px;text-decoration:none;"
                "text-transform:uppercase;'>READ FULL PAPER &rarr;</a>"
                "</div>"
            )
            continue

        # Paper badge line
        if s.startswith("PAPER ") and " of " in s and "—" in s:
            parts.append(
                "<div style='margin-bottom:16px;'>"
                "<span style='display:inline-block;background:#c9a227;color:#1a1a2e;"
                "font-family:Arial,sans-serif;font-size:8px;font-weight:bold;"
                "letter-spacing:3px;padding:6px 14px;text-transform:uppercase;'>"
                + s + "</span></div>"
            )
            continue

        # Paper title (line after badge — long line, not metadata)
        if (not s.startswith("Authors:") and not s.startswith("Category:")
                and not s.startswith("Full paper:")
                and len(s) > 30 and s == s and not s.isupper()
                and not any(s.startswith(k) for k in SECTION_STYLES)
                and not any(s.startswith(k) for k in SUBSECTION_MARKERS)
                and not s[0].isdigit()):
            # Could be title — check if previous part had badge
            last = "".join(parts[-2:]) if len(parts) >= 2 else ""
            if "c9a227" in last and "PAPER" in last:
                parts.append(
                    "<h2 style='color:#1a1a2e;font-size:18px;margin:0 0 6px;"
                    "font-family:Georgia,serif;line-height:1.4;font-weight:bold;'>"
                    + s + "</h2>"
                )
                continue

        # Authors / Category metadata
        if s.startswith("Authors:") or s.startswith("Category:"):
            parts.append(
                "<p style='color:#999;font-size:11px;margin:2px 0 0;"
                "font-family:Arial,sans-serif;border-bottom:1px solid #f0ede6;"
                "padding-bottom:10px;margin-bottom:4px;'>" + s + "</p>"
            )
            continue

        # Major section headers (colored banner)
        matched_section = None
        for key, (bg, fg, emoji) in SECTION_STYLES.items():
            if s.upper() == key:
                matched_section = (bg, fg, emoji, key)
                break

        if matched_section:
            bg, fg, emoji, key = matched_section
            parts.append(
                "<div style='margin:24px 0 12px;'>"
                "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>"
                "<tr>"
                "<td style='background:" + bg + ";padding:9px 16px;'>"
                "<span style='color:" + fg + ";font-family:Arial,sans-serif;"
                "font-size:10px;font-weight:bold;letter-spacing:2px;"
                "text-transform:uppercase;'>"
                + emoji + " " + key +
                "</span>"
                "</td>"
                "<td style='background:" + bg + ";opacity:0.3;width:100%;'></td>"
                "</tr></table>"
                "</div>"
            )
            continue

        # Sub-section markers (colored left border)
        matched_sub = None
        for key, color in SUBSECTION_MARKERS.items():
            if s.upper() == key:
                matched_sub = (key, color)
                break

        if matched_sub:
            key, color = matched_sub
            parts.append(
                "<div style='margin:18px 0 8px;border-left:4px solid " + color + ";"
                "padding:6px 12px;background:#fafaf8;'>"
                "<span style='font-family:Arial,sans-serif;font-size:9px;"
                "font-weight:bold;color:" + color + ";letter-spacing:2px;"
                "text-transform:uppercase;'>&#9670; " + key + "</span>"
                "</div>"
            )
            continue

        # Numbered learning items
        if len(s) > 2 and s[0].isdigit() and s[1] == ".":
            emoji_map = {"1": "1️⃣", "2": "2️⃣", "3": "3️⃣"}
            num_emoji = emoji_map.get(s[0], s[0])
            parts.append(
                "<div style='display:flex;align-items:flex-start;margin:10px 0;"
                "padding:10px 14px;background:#f8f5ef;border-left:3px solid #c9a227;'>"
                "<span style='font-size:16px;margin-right:10px;flex-shrink:0;'>"
                + s[0] + "</span>"
                "<span style='color:#333;font-size:13px;line-height:1.7;"
                "font-family:Georgia,serif;'>" + s[3:] + "</span>"
                "</div>"
            )
            continue

        # Bullet points
        if s.startswith("- ") or s.startswith("* "):
            parts.append(
                "<div style='display:flex;align-items:flex-start;margin:6px 0;'>"
                "<span style='color:#c9a227;margin-right:10px;font-size:16px;"
                "line-height:1.4;flex-shrink:0;'>&#8226;</span>"
                "<span style='color:#333;font-size:13px;line-height:1.75;"
                "font-family:Georgia,serif;'>" + s[2:] + "</span>"
                "</div>"
            )
            continue

        # Default paragraph
        parts.append(
            "<p style='margin:5px 0;line-height:1.85;color:#333;"
            "font-size:13px;font-family:Georgia,serif;'>" + s + "</p>"
        )

    return "\n".join(parts)


def build_paper_card(num, total, paper, summary, is_weekly=False):
    badge = f"PAPER {num} OF {total}" + (" — WEEKLY BEST" if is_weekly else " — TODAY")
    content = (
        plain_to_html(summary) if summary else
        "<p style='font-family:Georgia,serif;font-size:13px;color:#333;line-height:1.7;'>"
        + paper["abstract"] + "</p>"
    )
    return (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        " style='margin:28px 0;border:1px solid #e0dbd0;background:#fafaf8;'>"
        "<tr>"
        "<td style='background:#c9a227;width:5px;'></td>"
        "<td style='padding:26px 30px;'>"
        "<div style='margin-bottom:14px;'>"
        "<span style='background:#1a1a2e;color:#c9a227;font-family:Arial,sans-serif;"
        "font-size:8px;font-weight:bold;letter-spacing:2.5px;padding:5px 12px;"
        "text-transform:uppercase;'>" + badge + "</span>"
        "</div>"
        "<h2 style='color:#1a1a2e;font-size:17px;margin:0 0 8px;"
        "font-family:Georgia,serif;line-height:1.4;font-weight:bold;'>"
        + paper["title"] + "</h2>"
        "<p style='color:#999;font-size:11px;margin:0 0 18px;font-family:Arial,sans-serif;"
        "border-bottom:1px solid #e8e4d9;padding-bottom:14px;'>"
        + paper["authors"] + " &nbsp;&bull;&nbsp; "
        + paper["category"] + " &nbsp;&bull;&nbsp; "
        + paper["published"] + "</p>"
        "<div>" + content + "</div>"
        "</td></tr></table>"
    )

def build_section_header(label, color="#1a1a2e"):
    return (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        " style='margin:30px 0 0;'><tr>"
        "<td style='border-bottom:3px solid " + color + ";padding-bottom:10px;'>"
        "<span style='background:" + color + ";color:#fff;font-family:Arial,sans-serif;"
        "font-size:9px;letter-spacing:3px;padding:6px 16px;"
        "text-transform:uppercase;font-weight:bold;'>"
        + label + "</span>"
        "</td></tr></table>"
    )

def build_full_email(date, weekday, edition_label, intro_text, body_html):
    return (
        "<!DOCTYPE html><html lang='en'>"
        "<head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>The Hermes Daily</title></head>"
        "<body style='margin:0;padding:0;background:#f0ede6;font-family:Georgia,serif;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        " style='background:#f0ede6;'>"
        "<tr><td align='center' style='padding:28px 12px;'>"
        "<table role='presentation' style='max-width:680px;width:100%;background:#fff;"
        "border:1px solid #d4c9b0;box-shadow:0 4px 16px rgba(0,0,0,0.1);'>"
        "<tr><td style='background:#1a1a2e;height:6px;'></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#1a1a2e;padding:36px 48px;text-align:center;'>"
        "<p style='color:#c9a227;font-size:9px;letter-spacing:6px;margin:0 0 12px;"
        "font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;'>"
        "Your Personal Intelligence Brief</p>"
        "<h1 style='color:#fff;font-size:48px;margin:0;letter-spacing:5px;"
        "font-family:Georgia,serif;font-weight:normal;line-height:1;'>"
        "THE HERMES DAILY</h1>"
        "<p style='color:#c9a227;font-size:11px;margin:10px 0 0;"
        "font-family:Arial,sans-serif;letter-spacing:4px;'>RESEARCH EDITION</p>"
        "<div style='border-top:1px solid #2d2d4e;margin:16px 0 0;padding-top:14px;'>"
        "<p style='color:#888;font-size:10px;margin:0;font-family:Arial,sans-serif;"
        "letter-spacing:1.5px;'>"
        + date + " &nbsp;&bull;&nbsp; " + edition_label + " &nbsp;&bull;&nbsp; HERMES AI"
        "</p></div></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#2d2d4e;height:1px;'></td></tr>"
        "<tr><td style='padding:22px 48px 0;background:#fff;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        " style='background:#f8f5ef;border-left:4px solid #c9a227;'>"
        "<tr><td style='padding:14px 20px;'>"
        "<p style='color:#555;font-size:13px;margin:0;font-family:Georgia,serif;"
        "line-height:1.7;font-style:italic;'>" + intro_text + "</p>"
        "</td></tr></table></td></tr>"
        "<tr><td style='padding:0 48px 48px;background:#fff;'>" + body_html + "</td></tr>"
        "<tr><td style='background:#e8e4d9;height:1px;'></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#1a1a2e;padding:24px 48px;text-align:center;'>"
        "<p style='color:#c9a227;font-size:11px;margin:0;font-family:Arial,sans-serif;"
        "letter-spacing:4px;font-weight:bold;'>THE HERMES DAILY</p>"
        "<p style='color:#666;font-size:10px;margin:8px 0 0;font-family:Arial,sans-serif;'>"
        "arXiv &bull; cs.AI &bull; cs.LG &bull; cs.CL &bull; cs.CV &bull; cs.RO"
        "</p>"
        "<p style='color:#444;font-size:10px;margin:6px 0 0;font-family:Arial,sans-serif;'>"
        "Automated by GitHub Actions &bull; Summaries by OpenRouter AI"
        "</p></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "</table></td></tr></table></body></html>"
    )

def send_email(subject, html_body):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Hermes Research <{GMAIL_USER}>"
        msg["To"]      = GMAIL_USER
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("Email sent!")
    except Exception as e:
        print(f"Email error: {e}")

# ── Categories ────────────────────────────────────────────────────────────────

categories = {
    "AI (cs.AI)":               "cs.AI",
    "Machine Learning (cs.LG)": "cs.LG",
    "NLP (cs.CL)":              "cs.CL",
    "Computer Vision (cs.CV)":  "cs.CV",
    "Robotics (cs.RO)":         "cs.RO",
}

today   = datetime.now().strftime("%d %B %Y")
weekday = datetime.now().strftime("%A")

# =============================================================================
# WEEKEND PATH
# =============================================================================

if weekday in ["Saturday", "Sunday"]:

    send(
        f"6:30 AM Weekend Research Digest — {today}\n\n"
        "arXiv is closed on weekends.\n"
        "Your full WEEK IN AI RESEARCH digest is incoming.\n\n"
        "Each paper has a plain English summary, real-world analogy, "
        "and what to study next.\n\n"
        "Full newsletter also coming to your email."
    )

    weekly_papers = []
    for cat_name, cat_code in categories.items():
        fetched = fetch_arxiv(cat_code, count=15)
        for p in fetched:
            p["category"] = cat_name
        weekly_papers.extend(fetched)
        time.sleep(2)

    print(f"Weekly papers: {len(weekly_papers)}")

    if len(weekly_papers) == 0:
        send("Could not fetch weekly papers. arXiv may be down.")
        exit()

    weekly_text = ""
    for i, p in enumerate(weekly_papers):
        weekly_text += (
            f"[{i+1}] {p['category']} | {p['published']}\n"
            f"Title: {p['title']}\n"
            f"Abstract: {p['abstract'][:300]}\n---\n"
        )

    overview = ask_ai(build_weekly_overview_prompt(len(weekly_papers), weekly_text))
    if overview:
        send("THIS WEEK IN AI RESEARCH\n" + "="*35 + "\n\n" + overview)
    time.sleep(3)

    selection_prompt = (
        "From these arXiv papers, select the 5 most impactful of the week.\n\n"
        "Return only a numbered list of exact titles. No other text.\n\n"
        f"PAPERS:\n{weekly_text[:5000]}"
    )
    top_5_raw = ask_ai(selection_prompt) or ""

    papers_to_summarize = []
    if top_5_raw:
        for paper in weekly_papers:
            if len(papers_to_summarize) >= 5:
                break
            if paper["title"][:45].lower() in top_5_raw.lower():
                papers_to_summarize.append(paper)

    if len(papers_to_summarize) == 0:
        papers_to_summarize = weekly_papers[:5]

    send("TOP 5 PAPERS OF THE WEEK\n" + "="*35 + "\n\nDetailed summaries incoming...")

    email_body = build_section_header("THIS WEEK IN AI RESEARCH", "#1a1a2e")
    if overview:
        email_body += (
            "<div style='margin:18px 0;padding:18px 22px;"
            "background:#f8f5ef;border-left:4px solid #1a1a2e;'>"
            + plain_to_html(overview) + "</div>"
        )
    email_body += build_section_header("TOP 5 PAPERS OF THE WEEK", "#c9a227")

    total = len(papers_to_summarize)
    for idx, paper in enumerate(papers_to_summarize):
        num = idx + 1
        summary = ask_ai(build_summary_prompt(num, total, paper, "WEEKLY BEST"))
        if summary:
            send(summary)
        else:
            send(
                f"PAPER {num} of {total}\n\n"
                f"{paper['title']}\n\n"
                f"{paper['abstract']}\n\n"
                f"Full paper: {paper['link']}"
            )
        email_body += build_paper_card(num, total, paper, summary, is_weekly=True)
        print(f"Sent paper {num}/{total}")
        time.sleep(3)

    html = build_full_email(
        today, weekday,
        f"{weekday} Weekend Research Digest",
        (
            f"arXiv publishes no new papers on weekends. This is your complete week in "
            f"AI research — {len(weekly_papers)} papers across AI, ML, NLP, Computer Vision, "
            "and Robotics. Every summary is written in plain English with real-world analogies "
            "and personalised learning recommendations."
        ),
        email_body
    )
    send_email(f"The Hermes Daily — Week in AI Research ({today})", html)

    send(
        "Weekend digest complete.\n\n"
        "Full newsletter sent to your email.\n"
        "Enjoy your weekend. New papers resume Monday at 6:30 AM."
    )
    exit()

# =============================================================================
# WEEKDAY PATH
# =============================================================================

all_papers = []
for cat_name, cat_code in categories.items():
    fetched = fetch_arxiv(cat_code, count=8)
    for p in fetched:
        p["category"] = cat_name
    all_papers.extend(fetched)
    print(f"{cat_name}: {len(fetched)} papers")
    time.sleep(2)

print(f"Total fetched: {len(all_papers)}")

sent_ids   = load_sent()
new_papers = [p for p in all_papers if p["link"] not in sent_ids]
print(f"New papers: {len(new_papers)}")

if len(new_papers) == 0:
    send(
        f"6:30 AM Research Brief — {today}\n\n"
        "No new papers today. All recent arXiv papers were already sent.\n"
        "Check back tomorrow."
    )
    exit()

send(
    f"6:30 AM Research Brief — {today} ({weekday})\n\n"
    f"Fetched {len(new_papers)} new papers from arXiv.\n"
    "Each summary includes:\n"
    "  Plain English explanation\n"
    "  Real-world analogy\n"
    "  Technical breakdown\n"
    "  What to study next\n\n"
    "Full newsletter also coming to your email."
)

papers_list_text = ""
for i, p in enumerate(new_papers):
    papers_list_text += (
        f"[{i+1}] {p['category']}\n"
        f"Title: {p['title']}\n"
        f"Abstract: {p['abstract'][:250]}\n---\n"
    )

selection_prompt = (
    "From these arXiv papers, select the 5 most impactful and interesting "
    "for someone learning AI/ML.\n\n"
    "Return only a numbered list of exact titles. No other text.\n\n"
    f"PAPERS:\n{papers_list_text[:5000]}"
)

print("Selecting top 5...")
top_5_raw = ask_ai(selection_prompt) or ""

papers_to_summarize = []
if top_5_raw:
    for paper in new_papers:
        if len(papers_to_summarize) >= 5:
            break
        if paper["title"][:45].lower() in top_5_raw.lower():
            papers_to_summarize.append(paper)

if len(papers_to_summarize) == 0:
    print("Selection matched nothing — using top 5 newest")
    papers_to_summarize = new_papers[:5]

email_body = build_section_header("TODAY'S TOP 5 RESEARCH PAPERS", "#1a1a2e")
sent_today = set()
total = len(papers_to_summarize)

for idx, paper in enumerate(papers_to_summarize):
    num = idx + 1
    summary = ask_ai(build_summary_prompt(num, total, paper, "TODAY"))
    if summary:
        send(summary)
    else:
        send(
            f"PAPER {num} of {total}\n\n"
            f"{paper['title']}\n"
            f"Authors: {paper['authors']}\n"
            f"Category: {paper['category']} | {paper['published']}\n\n"
            f"{paper['abstract']}\n\n"
            f"Full paper: {paper['link']}"
        )
    email_body += build_paper_card(num, total, paper, summary)
    sent_today.add(paper["link"])
    print(f"Sent paper {num}/{total}")
    time.sleep(3)

save_sent(sent_today)

html = build_full_email(
    today, weekday,
    f"{weekday} Research Edition",
    (
        f"Today Hermes fetched {len(new_papers)} new papers from arXiv. "
        f"The top {total} most impactful are summarized below — each written in plain English "
        "with a real-world analogy, full technical breakdown, and specific topics to study next."
    ),
    email_body
)
send_email(f"The Hermes Daily — Research Brief ({today})", html)

send(
    f"Research brief complete. ({total} papers)\n\n"
    "Full newsletter sent to your email.\n"
    "See you at 8 AM for news and coding challenges."
)

print("Done!")
