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

def ask_ai(prompt):
    system = (
        "You are a professional science communicator writing for a beginner audience. "
        "You write clean, structured summaries with no internal commentary, no meta-talk, "
        "no reasoning visible to the reader. Output only the final formatted text. "
        "Never explain what you are about to do. Never use placeholder brackets. "
        "Write the actual content directly."
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
                    bad_signals = [
                        "let me ", "i need to ", "i'll ", "we need to ",
                        "the instruction", "let's ", "i should ", "okay so",
                        "now i ", "first i ", "the user wants"
                    ]
                    lower = content.lower()
                    if any(sig in lower[:300] for sig in bad_signals):
                        print(f"Model {model} leaked reasoning — trying next model")
                        break
                    print(f"Model used: {model}")
                    return content
                else:
                    print(f"Model {model} failed: {data.get('error',{}).get('message','')}")
                    break
            except Exception as e:
                print(f"Attempt {attempt+1} error: {e}")
                time.sleep(3)
    return None

def fetch_arxiv(category, count=8):
    papers = []
    try:
        url = (
            f"https://export.arxiv.org/api/query?"
            f"search_query=cat:{category}"
            f"&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={count}"
        )
        resp = requests.get(url, timeout=30, headers={"User-Agent": "HermesBot/1.0"})
        content = resp.text
        raw_entries = content.split("<entry>")[1:]
        for entry in raw_entries[:count]:
            title = ""
            if "<title>" in entry:
                title = entry.split("<title>")[1].split("</title>")[0].strip().replace("\n", " ")
            abstract = ""
            if "<summary>" in entry:
                abstract = entry.split("<summary>")[1].split("</summary>")[0].strip().replace("\n", " ")
            link = ""
            if "<id>" in entry:
                link = entry.split("<id>")[1].split("</id>")[0].strip()
            author_list = []
            for chunk in entry.split("<author>")[1:]:
                if "<name>" in chunk:
                    author_list.append(chunk.split("<name>")[1].split("</name>")[0].strip())
            authors = ", ".join(author_list[:3])
            if len(author_list) > 3:
                authors += " et al."
            published = ""
            if "<published>" in entry:
                published = entry.split("<published>")[1].split("</published>")[0].strip()[:10]
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

def build_summary_prompt(num, total, paper, label="TODAY"):
    return f"""Summarize this research paper for a complete beginner who just started learning about AI.

Paper details:
Title: {paper['title']}
Authors: {paper['authors']}
Date: {paper['published']}
Category: {paper['category']}
Abstract: {paper['abstract']}

Write the summary using this exact format. Write actual content for each section — no placeholders, no brackets, no meta-commentary:

PAPER {num} of {total} — {label}
{paper['title']}
Authors: {paper['authors']}
Category: {paper['category']} | Date: {paper['published']}

━━━ SIMPLE VERSION ━━━
Explain this paper in 4-5 plain sentences that a curious 15-year-old can understand. Imagine explaining it to a smart friend who has never studied AI. Avoid all technical terms. Focus on what the researchers did and why it matters for ordinary people.

━━━ REAL-WORLD ANALOGY ━━━
Write a single vivid analogy that compares this research to something from everyday life — cooking, sports, school, driving, shopping, or anything relatable. Make it specific and memorable.

━━━ WHAT THEY ACTUALLY DID ━━━

THE PROBLEM
In 2-3 sentences, explain what specific gap or challenge this research addresses. Why did this problem need solving? What was missing before this paper?

THEIR APPROACH
In 3-4 sentences, describe the technique or method they developed. If you must use a technical term, immediately explain it in plain English in parentheses. Focus on the core idea, not implementation details.

RESULTS AND NUMBERS
In 2-3 sentences, describe what they achieved. If there are accuracy numbers or benchmark scores, include them and explain what they mean in plain terms. For example: "96% accuracy means the system was correct 96 times out of 100."

WHO BENEFITS FROM THIS
Name 2-3 specific groups of real people — doctors, students, farmers, engineers, companies — who will benefit from this research and briefly say how their lives or work improves.

WHAT TO LEARN NEXT
List exactly 3 topics the student should study to understand this paper better:
1. [Topic name] — one sentence explaining why this topic is directly relevant to this paper
2. [Topic name] — one sentence explaining relevance
3. [Topic name] — one sentence explaining relevance

Full paper: {paper['link']}"""

def build_weekly_overview_prompt(num_papers, weekly_text):
    return f"""Write a weekly digest of AI/ML research for a complete beginner.

You have {num_papers} arXiv papers from this week below. Write a clean, professional weekly overview.

Use this exact format:

THIS WEEK IN AI RESEARCH

BIGGEST THEMES
Write 3-4 sentences describing the major research directions researchers were focused on this week. Be specific — name actual topics, not vague terms like "various advances."

STANDOUT PAPER OF THE WEEK
Name one paper that was most impressive. In 3-4 sentences, explain in plain English what it did and why it stands out above everything else this week.

EMERGING TREND TO WATCH
In 2-3 sentences, describe one new pattern or technique appearing across multiple papers. Explain why a beginner should pay attention to it.

BY CATEGORY
AI: one plain sentence on what happened in general AI research
ML: one plain sentence on machine learning research
NLP: one plain sentence on natural language processing
Computer Vision: one plain sentence on image and video AI
Robotics: one plain sentence on robotics research

PAPERS:
{weekly_text[:5000]}"""

def plain_to_html(text):
    if not text:
        return "<p style='color:#999;font-family:Arial,sans-serif;'>Content unavailable.</p>"
    lines = text.split("\n")
    parts = []
    for line in lines:
        s = line.strip()
        if not s:
            parts.append("<div style='height:5px;'></div>")
        elif s.startswith("Full paper:"):
            link = s.replace("Full paper:", "").strip()
            parts.append(
                "<p style='margin:18px 0 0;'>"
                "<a href='" + link + "' style='display:inline-block;"
                "background:#1a1a2e;color:#c9a227;"
                "font-family:Arial,sans-serif;font-size:9px;"
                "font-weight:bold;letter-spacing:2px;padding:8px 18px;"
                "text-decoration:none;text-transform:uppercase;'>"
                "READ FULL PAPER &rarr;</a></p>"
            )
        elif s.startswith("\u2501\u2501\u2501") and s.endswith("\u2501\u2501\u2501"):
            label = s.replace("\u2501\u2501\u2501", "").strip()
            parts.append(
                "<p style='font-family:Arial,sans-serif;font-size:10px;"
                "font-weight:bold;color:#fff;background:#1a1a2e;"
                "letter-spacing:2px;margin:20px 0 8px;"
                "padding:6px 12px;text-transform:uppercase;'>"
                + label + "</p>"
            )
        elif s.isupper() and 2 < len(s) < 60:
            parts.append(
                "<p style='font-family:Arial,sans-serif;font-size:9px;"
                "font-weight:bold;color:#1a1a2e;letter-spacing:2px;"
                "margin:16px 0 5px;text-transform:uppercase;"
                "border-bottom:1px solid #e8e4d9;padding-bottom:4px;'>"
                + s + "</p>"
            )
        elif s.startswith("Authors:") or s.startswith("Category:"):
            parts.append(
                "<p style='color:#888;font-size:11px;margin:2px 0;"
                "font-family:Arial,sans-serif;'>" + s + "</p>"
            )
        elif s.startswith("PAPER ") and " of " in s:
            parts.append(
                "<p style='background:#c9a227;color:#1a1a2e;"
                "font-family:Arial,sans-serif;font-size:9px;"
                "font-weight:bold;letter-spacing:2px;padding:5px 12px;"
                "margin:0 0 10px;text-transform:uppercase;display:inline-block;'>"
                + s + "</p>"
            )
        elif s[:2] in ["1.", "2.", "3."]:
            parts.append(
                "<div style='display:flex;align-items:flex-start;margin:8px 0;'>"
                "<span style='background:#1a1a2e;color:#c9a227;"
                "font-family:Arial,sans-serif;font-size:11px;"
                "font-weight:bold;padding:2px 8px;margin-right:10px;"
                "margin-top:2px;flex-shrink:0;'>" + s[0] + "</span>"
                "<span style='color:#333;font-size:13px;line-height:1.7;"
                "font-family:Georgia,serif;'>" + s[3:] + "</span></div>"
            )
        else:
            parts.append(
                "<p style='margin:5px 0;line-height:1.8;color:#333;"
                "font-size:13px;font-family:Georgia,serif;'>" + s + "</p>"
            )
    return "\n".join(parts)

def build_paper_card(num, total, paper, summary, is_weekly=False):
    badge = f"PAPER {num} OF {total}" + (" — WEEKLY BEST" if is_weekly else " — TODAY")
    content = plain_to_html(summary) if summary else (
        "<p style='font-family:Georgia,serif;font-size:13px;"
        "color:#333;line-height:1.7;'>" + paper["abstract"] + "</p>"
    )
    return (
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='margin:28px 0;border:1px solid #e0dbd0;"
        "background:#fafaf8;border-radius:2px;'>"
        "<tr>"
        "<td style='background:#c9a227;width:5px;border-radius:2px 0 0 2px;'></td>"
        "<td style='padding:24px 28px;'>"
        "<div style='margin-bottom:14px;'>"
        "<span style='background:#1a1a2e;color:#c9a227;"
        "font-family:Arial,sans-serif;font-size:8px;"
        "font-weight:bold;letter-spacing:2.5px;padding:5px 12px;"
        "text-transform:uppercase;'>" + badge + "</span>"
        "</div>"
        "<h2 style='color:#1a1a2e;font-size:18px;margin:0 0 8px;"
        "font-family:Georgia,serif;line-height:1.4;font-weight:bold;'>"
        + paper["title"] + "</h2>"
        "<p style='color:#888;font-size:11px;margin:0 0 18px;"
        "font-family:Arial,sans-serif;letter-spacing:0.3px;"
        "border-bottom:1px solid #e8e4d9;padding-bottom:14px;'>"
        + paper["authors"] + " &nbsp;&bull;&nbsp; "
        + paper["category"] + " &nbsp;&bull;&nbsp; "
        + paper["published"] + "</p>"
        "<div>" + content + "</div>"
        "</td></tr></table>"
    )

def build_section_header(label, color="#1a1a2e"):
    return (
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='margin:30px 0 0;'><tr>"
        "<td style='border-bottom:3px solid " + color + ";padding-bottom:10px;'>"
        "<span style='background:" + color + ";color:#fff;"
        "font-family:Arial,sans-serif;font-size:9px;letter-spacing:3px;"
        "padding:6px 16px;text-transform:uppercase;font-weight:bold;'>"
        + label + "</span>"
        "</td></tr></table>"
    )

def build_full_email(date, weekday, edition_label, intro_text, body_html):
    return (
        "<!DOCTYPE html><html lang='en'>"
        "<head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>The Hermes Daily</title></head>"
        "<body style='margin:0;padding:0;background:#f0ede6;"
        "font-family:Georgia,serif;'>"
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='background:#f0ede6;'>"
        "<tr><td align='center' style='padding:28px 12px;'>"
        "<table role='presentation' style='max-width:680px;width:100%;"
        "background:#fff;border:1px solid #d4c9b0;"
        "box-shadow:0 4px 16px rgba(0,0,0,0.1);'>"
        "<tr><td style='background:#1a1a2e;height:6px;'></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#1a1a2e;padding:36px 48px;text-align:center;'>"
        "<p style='color:#c9a227;font-size:9px;letter-spacing:6px;"
        "margin:0 0 12px;font-family:Arial,sans-serif;"
        "text-transform:uppercase;font-weight:bold;'>"
        "Your Personal Intelligence Brief</p>"
        "<h1 style='color:#fff;font-size:48px;margin:0;letter-spacing:5px;"
        "font-family:Georgia,serif;font-weight:normal;line-height:1;'>"
        "THE HERMES DAILY</h1>"
        "<p style='color:#c9a227;font-size:11px;margin:10px 0 0;"
        "font-family:Arial,sans-serif;letter-spacing:4px;'>"
        "RESEARCH EDITION</p>"
        "<div style='border-top:1px solid #2d2d4e;margin:16px 0 0;padding-top:14px;'>"
        "<p style='color:#888;font-size:10px;margin:0;"
        "font-family:Arial,sans-serif;letter-spacing:1.5px;'>"
        + date + " &nbsp;&bull;&nbsp; " + edition_label +
        " &nbsp;&bull;&nbsp; HERMES AI"
        "</p></div></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#2d2d4e;height:1px;'></td></tr>"
        "<tr><td style='padding:20px 48px 0;background:#fff;'>"
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='background:#f8f5ef;"
        "border-left:4px solid #c9a227;'>"
        "<tr><td style='padding:14px 20px;'>"
        "<p style='color:#555;font-size:13px;margin:0;"
        "font-family:Georgia,serif;line-height:1.7;font-style:italic;'>"
        + intro_text + "</p>"
        "</td></tr></table></td></tr>"
        "<tr><td style='padding:0 48px 48px;background:#fff;'>"
        + body_html +
        "</td></tr>"
        "<tr><td style='background:#e8e4d9;height:1px;'></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#1a1a2e;padding:24px 48px;text-align:center;'>"
        "<p style='color:#c9a227;font-size:11px;margin:0;"
        "font-family:Arial,sans-serif;letter-spacing:4px;font-weight:bold;'>"
        "THE HERMES DAILY</p>"
        "<p style='color:#666;font-size:10px;margin:8px 0 0;"
        "font-family:Arial,sans-serif;letter-spacing:0.5px;'>"
        "Papers sourced from arXiv &bull; cs.AI &bull; cs.LG &bull; "
        "cs.CL &bull; cs.CV &bull; cs.RO"
        "</p>"
        "<p style='color:#444;font-size:10px;margin:6px 0 0;"
        "font-family:Arial,sans-serif;'>"
        "Automated by GitHub Actions &bull; Summaries by OpenRouter AI"
        "</p></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "</table></td></tr></table>"
        "</body></html>"
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

categories = {
    "AI (cs.AI)":               "cs.AI",
    "Machine Learning (cs.LG)": "cs.LG",
    "NLP (cs.CL)":              "cs.CL",
    "Computer Vision (cs.CV)":  "cs.CV",
    "Robotics (cs.RO)":         "cs.RO",
}

today   = datetime.now().strftime("%d %B %Y")
weekday = datetime.now().strftime("%A")

# ═════════════════════════════════════════════════════════════════
# WEEKEND PATH
# ═════════════════════════════════════════════════════════════════

if weekday in ["Saturday", "Sunday"]:

    send(
        f"6:30 AM Weekend Research Digest — {today}\n\n"
        f"arXiv is closed on weekends.\n"
        f"Your full WEEK IN AI RESEARCH digest is incoming.\n\n"
        f"Each paper includes a plain English summary, real-world analogy, "
        f"and what to study next.\n\n"
        f"Full newsletter also coming to your email."
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
        send("Could not fetch weekly papers. arXiv may be down. Try again later.")
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
        send(f"THIS WEEK IN AI RESEARCH\n{'='*35}\n\n{overview}")
    time.sleep(3)

    selection_prompt = (
        f"From these arXiv papers, select the 5 most impactful and "
        f"interesting papers of the week.\n\n"
        f"Return only a numbered list of exact titles. No commentary.\n\n"
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

    send(f"TOP 5 PAPERS OF THE WEEK\n{'='*35}\n\nDetailed summaries incoming...")

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
                f"{paper['title']}\n"
                f"{paper['abstract']}\n\n"
                f"Full paper: {paper['link']}"
            )
        email_body += build_paper_card(num, total, paper, summary, is_weekly=True)
        print(f"Sent paper {num}/{total}")
        time.sleep(3)

    html = build_full_email(
        today, weekday,
        f"{weekday} Weekend Research Digest",
        f"arXiv publishes no new papers on weekends. This is your complete week in "
        f"AI research — {len(weekly_papers)} papers across AI, ML, NLP, Computer "
        f"Vision, and Robotics. Each summary is written for beginners with plain "
        f"English explanations, real-world analogies, and learning recommendations.",
        email_body
    )
    send_email(f"The Hermes Daily — Week in AI Research ({today})", html)

    send(
        f"Weekend digest complete!\n\n"
        f"Full newsletter sent to your email.\n"
        f"Enjoy your weekend. New papers resume Monday at 6:30 AM."
    )
    exit()

# ═════════════════════════════════════════════════════════════════
# WEEKDAY PATH
# ═════════════════════════════════════════════════════════════════

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
        f"No new papers today. All recent arXiv papers were already sent.\n"
        f"Check back tomorrow."
    )
    exit()

send(
    f"6:30 AM Research Brief — {today} ({weekday})\n\n"
    f"Fetched {len(new_papers)} new papers from arXiv.\n"
    f"Each summary includes:\n"
    f"  Simple English explanation\n"
    f"  Real-world analogy\n"
    f"  Technical breakdown\n"
    f"  What to learn next\n\n"
    f"Full newsletter also coming to your email."
)

papers_list_text = ""
for i, p in enumerate(new_papers):
    papers_list_text += (
        f"[{i+1}] {p['category']}\n"
        f"Title: {p['title']}\n"
        f"Abstract: {p['abstract'][:250]}\n---\n"
    )

selection_prompt = (
    f"From these arXiv papers, select the 5 most impactful and interesting "
    f"for someone learning AI/ML.\n\n"
    f"Return only a numbered list of exact titles. No commentary.\n\n"
    f"PAPERS:\n{papers_list_text[:5000]}"
)

print("Asking AI to select top 5...")
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
    f"Today Hermes fetched {len(new_papers)} new papers from arXiv. "
    f"The top {total} most impactful are summarized below — each with a "
    f"plain English explanation, real-world analogy, technical breakdown, "
    f"and specific topics to study next.",
    email_body
)
send_email(f"The Hermes Daily — Research Brief ({today})", html)

send(
    f"Research brief complete. ({total} papers)\n\n"
    f"Full newsletter sent to your email.\n"
    f"See you at 8 AM for news and challenges."
)

print("Done!")
