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
        "You are a professional newspaper editor and science communicator. "
        "You write clean, structured news summaries for a beginner audience. "
        "Rules you must follow without exception:\n"
        "1. Output ONLY the final formatted text. No preamble, no meta-talk.\n"
        "2. Never start with 'Sure!', 'Here is', 'Let me', 'Certainly', 'I will'.\n"
        "3. Never use placeholder text in brackets. Write real content always.\n"
        "4. Write like a journalist — clear, confident, factual, beginner-friendly.\n"
        "5. Every technical term must be explained in plain English in parentheses immediately after."
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
                        "i need to", "we need to", "i should ", "now i "
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

# ── RSS ───────────────────────────────────────────────────────────────────────

def fetch_rss(url, count=5):
    items = []
    try:
        resp = requests.get(
            url, timeout=15,
            headers={"User-Agent": "HermesBot/1.0"}
        )
        content = resp.text
        entries = content.split("<item>")[1:]
        for entry in entries[:count]:
            title = desc = link = ""
            if "<title>" in entry:
                raw = entry.split("<title>")[1].split("</title>")[0].strip()
                title = raw.replace("<![CDATA[", "").replace("]]>", "").strip()
            if "<description>" in entry:
                raw = entry.split("<description>")[1].split("</description>")[0].strip()
                desc = raw.replace("<![CDATA[", "").replace("]]>", "").strip()[:300]
            if "<link>" in entry:
                link = entry.split("<link>")[1].split("</link>")[0].strip()
            if title:
                items.append(f"TITLE: {title}\nSUMMARY: {desc}\nLINK: {link}")
    except Exception as e:
        print(f"RSS error {url}: {e}")
    return "\n\n".join(items)

# ── Learning topic + difficulty ───────────────────────────────────────────────

def get_learning_topic():
    try:
        with open("learning_log.txt", "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        if not lines:
            return None, "Medium"
        last = lines[-1]
        if ": " in last:
            last = last.split(": ", 1)[1].strip()
        difficulty = "Medium"
        if " | " in last:
            parts = last.rsplit(" | ", 1)
            topic = parts[0].strip()
            diff_raw = parts[1].strip().capitalize()
            if diff_raw in ["Easy", "Medium", "Hard"]:
                difficulty = diff_raw
        else:
            topic = last.strip()
        print(f"Topic: {topic} | Difficulty: {difficulty}")
        return topic, difficulty
    except Exception as e:
        print(f"Could not read learning_log.txt: {e}")
    return None, "Medium"

# ── News prompt builder ───────────────────────────────────────────────────────

def build_news_prompt(section_name, raw_articles, story_count=5):
    return (
        f"You are the editor of a morning newspaper writing the {section_name} section. "
        "Your reader is a smart beginner who just started learning about AI and tech. "
        "Write in newspaper front-page style — headline first, then detail, then impact. "
        "No meta-commentary, no preamble. Output only the final formatted text.\n\n"
        f"From the articles below, select the {story_count} most important stories. "
        "For each story write EXACTLY this structure:\n\n"
        "HEADLINE: [rewrite the headline in plain, punchy English — max 12 words]\n\n"
        "THE STORY\n"
        "Write 3 sentences. Sentence 1: what happened — the core fact, who did what. "
        "Sentence 2: the context — why this happened and what led to it. "
        "Sentence 3: the scale — how big is this, what numbers or names are involved.\n\n"
        "IN PLAIN ENGLISH\n"
        "Write 2 sentences explaining this story to someone who has never followed "
        "tech news. No jargon. If you must use a technical term, explain it in "
        "parentheses immediately after.\n\n"
        "REAL-WORLD ANALOGY\n"
        "Write 1-2 sentences. Give a vivid analogy comparing this news to something "
        "from daily life — shopping, cooking, sports, school, or traffic. "
        "The analogy must explain the significance of the story, not just its topic.\n\n"
        "WHY IT MATTERS\n"
        "Write 2 sentences. Sentence 1: who is directly affected — name specific "
        "groups of people, companies, or countries. Sentence 2: what changes in the "
        "world because of this story — be concrete and specific.\n\n"
        "────────────────────────────\n\n"
        f"ARTICLES:\n{raw_articles[:4000]}"
    )

# ── Coding challenge prompt ───────────────────────────────────────────────────

def build_challenge_prompt(topic, difficulty):
    diff_guide = {
        "Easy": (
            "The student is a complete beginner. "
            "Easy: 5-10 lines, basic syntax only. "
            "Medium: 15 lines, one concept at a time. "
            "Hard: 20 lines, one real-world mini-problem."
        ),
        "Medium": (
            "The student knows the basics. "
            "Easy: quick warmup directly testing the topic. "
            "Medium: combines topic with one other concept. "
            "Hard: a real-world mini-project using the topic."
        ),
        "Hard": (
            "The student is comfortable with the topic. "
            "Easy: something solvable in under 5 minutes. "
            "Medium: requires thinking about edge cases. "
            "Hard: production-level problem, optimization required."
        ),
    }.get(difficulty, "")

    return (
        f"Generate exactly 3 coding challenges on this topic: {topic}\n"
        f"Difficulty level: {difficulty}\n\n"
        f"{diff_guide}\n\n"
        "Output only the challenges. No preamble. Use EXACTLY this structure:\n\n"
        f"TOPIC: {topic}\n"
        f"DIFFICULTY: {difficulty}\n\n"
        "EASY\n"
        f"Task: [specific beginner challenge directly testing {topic}]\n"
        "Concept: [the specific method or syntax they must use]\n"
        "Expected output:\n"
        "[show exact output]\n\n"
        "MEDIUM\n"
        f"Task: [intermediate challenge combining {topic} with something practical]\n"
        "Concept: [specific tools or concepts involved]\n"
        "Expected output:\n"
        "[show exact output]\n\n"
        "HARD\n"
        f"Task: [advanced real-world application of {topic}]\n"
        "Hint: [one-line hint without giving away the solution]\n"
        "Expected output:\n"
        "[show exact output]\n\n"
        "BONUS QUESTION\n"
        f"Question: [one conceptual question testing deep understanding of {topic}]\n"
        "Answer: [clear, concise answer in plain English]"
    )

# ── HTML helpers ──────────────────────────────────────────────────────────────

def news_to_html(text, accent_color):
    if not text:
        return "<p style='color:#999;font-family:Arial,sans-serif;'>Content unavailable.</p>"

    lines = text.split("\n")
    parts = []
    in_story_card = False

    for line in lines:
        s = line.strip()

        if not s:
            parts.append("<div style='height:5px;'></div>")
            continue

        # Story divider — close previous card, open new one
        if s == "────────────────────────────":
            if in_story_card:
                parts.append("</div></div>")
                in_story_card = False
            parts.append(
                "<div style='border-top:1px dashed #e0dbd0;margin:20px 0;'></div>"
            )
            continue

        # HEADLINE
        if s.startswith("HEADLINE:"):
            if in_story_card:
                parts.append("</div></div>")
            headline = s.replace("HEADLINE:", "").strip()
            parts.append(
                "<div style='margin:20px 0 0;'>"
                "<div style='padding:18px 22px;background:#fafaf8;"
                "border-left:4px solid " + accent_color + ";'>"
                "<h3 style='color:#1a1a2e;font-size:16px;margin:0 0 4px;"
                "font-family:Georgia,serif;line-height:1.4;font-weight:bold;'>"
                + headline + "</h3>"
                "</div>"
                "<div style='padding:14px 22px 18px;background:#fff;"
                "border:1px solid #e8e4d9;border-top:none;'>"
            )
            in_story_card = True
            continue

        # Section headers inside story
        if s in ["THE STORY", "IN PLAIN ENGLISH", "REAL-WORLD ANALOGY", "WHY IT MATTERS"]:
            icon_map = {
                "THE STORY":        ("📰", "#1a1a2e"),
                "IN PLAIN ENGLISH": ("💡", "#2d6a4f"),
                "REAL-WORLD ANALOGY": ("🔁", "#1a4a6e"),
                "WHY IT MATTERS":   ("⚡", "#7d3c00"),
            }
            icon, color = icon_map.get(s, ("▸", "#333"))
            parts.append(
                "<p style='font-family:Arial,sans-serif;font-size:9px;"
                "font-weight:bold;color:" + color + ";letter-spacing:2px;"
                "margin:14px 0 5px;text-transform:uppercase;'>"
                + icon + " " + s + "</p>"
            )
            continue

        # Default paragraph
        parts.append(
            "<p style='margin:4px 0;line-height:1.8;color:#333;"
            "font-size:13px;font-family:Georgia,serif;'>" + s + "</p>"
        )

    if in_story_card:
        parts.append("</div></div>")

    return "\n".join(parts)

def build_news_section_email(label, color, icon, content_html):
    return (
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='margin-top:32px;'><tr><td>"
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='margin-bottom:18px;'><tr>"
        "<td style='border-bottom:3px solid " + color + ";padding-bottom:10px;'>"
        "<span style='background:" + color + ";color:#fff;"
        "font-family:Arial,sans-serif;font-size:9px;letter-spacing:3px;"
        "padding:6px 16px;text-transform:uppercase;font-weight:bold;'>"
        + icon + " " + label + "</span>"
        "</td></tr></table>"
        "<div>" + content_html + "</div>"
        "</td></tr></table>"
    )

def build_divider():
    return (
        "<table role='presentation' width='100%' cellpadding='0'"
        " cellspacing='0' style='margin:16px 0;'><tr>"
        "<td style='border-top:1px solid #e8e4d9;'></td>"
        "</tr></table>"
    )

def build_full_email(date, weekday, sections_html):
    return (
        "<!DOCTYPE html><html lang='en'>"
        "<head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>The Hermes Daily</title></head>"
        "<body style='margin:0;padding:0;background:#f0ede6;font-family:Georgia,serif;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        " style='background:#f0ede6;'>"
        "<tr><td align='center' style='padding:28px 12px;'>"
        "<table role='presentation' style='max-width:660px;width:100%;"
        "background:#fff;border:1px solid #d4c9b0;"
        "box-shadow:0 4px 16px rgba(0,0,0,0.1);'>"
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
        "font-family:Arial,sans-serif;letter-spacing:4px;'>MORNING EDITION</p>"
        "<div style='border-top:1px solid #2d2d4e;margin:16px 0 0;padding-top:14px;'>"
        "<p style='color:#888;font-size:10px;margin:0;"
        "font-family:Arial,sans-serif;letter-spacing:1.5px;'>"
        + date + " &nbsp;&bull;&nbsp; " + weekday + " Morning Edition"
        " &nbsp;&bull;&nbsp; HERMES AI</p>"
        "</div></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#2d2d4e;height:1px;'></td></tr>"
        "<tr><td style='padding:20px 48px 48px;background:#fff;'>"
        + sections_html +
        "</td></tr>"
        "<tr><td style='background:#e8e4d9;height:1px;'></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "<tr><td style='background:#1a1a2e;padding:24px 48px;text-align:center;'>"
        "<p style='color:#c9a227;font-size:11px;margin:0;"
        "font-family:Arial,sans-serif;letter-spacing:4px;font-weight:bold;'>"
        "THE HERMES DAILY</p>"
        "<p style='color:#666;font-size:10px;margin:8px 0 0;"
        "font-family:Arial,sans-serif;'>"
        "TechCrunch &bull; VentureBeat &bull; MIT &bull; HackerNews &bull; InfoQ"
        "</p>"
        "<p style='color:#444;font-size:10px;margin:6px 0 0;"
        "font-family:Arial,sans-serif;'>"
        "Automated by GitHub Actions &bull; AI by OpenRouter"
        "</p></td></tr>"
        "<tr><td style='background:#c9a227;height:3px;'></td></tr>"
        "</table></td></tr></table>"
        "</body></html>"
    )

def send_email(subject, html_body):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Hermes Daily <{GMAIL_USER}>"
        msg["To"]      = GMAIL_USER
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("  Email sent!")
    except Exception as e:
        print(f"  Email error: {e}")

# ── Telegram section formatter ────────────────────────────────────────────────

def format_section_telegram(label, emoji, stories_text):
    border = "═" * 32
    return (
        f"╔{border}╗\n"
        f"   {emoji}  {label}\n"
        f"╚{border}╝\n\n"
        + stories_text
    )

# =============================================================================
# MAIN
# =============================================================================

today   = datetime.now().strftime("%d %B %Y")
weekday = datetime.now().strftime("%A")

send(
    f"☀️ Good Morning — {today} ({weekday})\n\n"
    f"Your Hermes 8 AM Brief is incoming.\n\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"  1.  AI & ML News\n"
    f"  2.  Hacker News\n"
    f"  3.  Java in AI/ML\n"
    f"  4.  Coding Challenges\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    f"Full newsletter also coming to your email."
)

email_sections = []

# ── 1. AI/ML NEWS ─────────────────────────────────────────────────────────────

print("Fetching AI/ML news...")
aiml_sources = {
    "TechCrunch AI":     "https://techcrunch.com/category/artificial-intelligence/feed/",
    "VentureBeat AI":    "https://venturebeat.com/category/ai/feed/",
    "MIT Tech Review":   "https://www.technologyreview.com/feed/",
    "The Verge AI":      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "Ars Technica":      "https://feeds.arstechnica.com/arstechnica/index",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
}

aiml_raw = ""
for name, url in aiml_sources.items():
    chunk = fetch_rss(url, count=4)
    if chunk:
        aiml_raw += f"\n[{name}]\n{chunk}\n"
    time.sleep(0.5)

aiml_summary = ask_ai(build_news_prompt("AI & ML News", aiml_raw, story_count=5))

if aiml_summary:
    telegram_msg = format_section_telegram("AI & ML NEWS", "🤖", aiml_summary)
    send(telegram_msg)
    email_sections.append(
        build_news_section_email("AI & ML News", "#1a1a2e", "🤖",
                                  news_to_html(aiml_summary, "#1a1a2e"))
    )
    email_sections.append(build_divider())

time.sleep(2)

# ── 2. HACKER NEWS ────────────────────────────────────────────────────────────

print("Fetching Hacker News...")
hn_raw = ""
try:
    hn_resp = requests.get(
        "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=15",
        timeout=15,
        headers={"User-Agent": "HermesBot/1.0"}
    )
    hn_data = hn_resp.json()
    hn_stories = []
    for hit in hn_data.get("hits", [])[:15]:
        title    = hit.get("title", "")
        points   = hit.get("points", 0)
        comments = hit.get("num_comments", 0)
        obj_id   = hit.get("objectID", "")
        hn_link  = f"https://news.ycombinator.com/item?id={obj_id}"
        if title:
            hn_stories.append(
                f"TITLE: {title}\n"
                f"SUMMARY: {points} points, {comments} comments on Hacker News\n"
                f"LINK: {hn_link}"
            )
    hn_raw = "\n\n".join(hn_stories)
    print(f"  HN: {len(hn_stories)} stories fetched")
except Exception as e:
    print(f"  HN error: {e}")

if hn_raw:
    hn_summary = ask_ai(build_news_prompt("Hacker News", hn_raw, story_count=5))
    if hn_summary:
        telegram_msg = format_section_telegram("HACKER NEWS", "🔶", hn_summary)
        send(telegram_msg)
        email_sections.append(
            build_news_section_email("Hacker News", "#ff6600", "🔶",
                                      news_to_html(hn_summary, "#ff6600"))
        )
        email_sections.append(build_divider())

time.sleep(2)

# ── 3. JAVA IN AI/ML ──────────────────────────────────────────────────────────

print("Fetching Java news...")
java_sources = {
    "InfoQ Java":  "https://feed.infoq.com/java",
    "InfoQ AI/ML": "https://feed.infoq.com/ai-ml-data-eng",
    "Baeldung":    "https://www.baeldung.com/feed/",
    "Inside Java": "https://inside.java/feed.xml",
    "DZone Java":  "https://feeds.dzone.com/java",
}

java_raw = ""
for name, url in java_sources.items():
    chunk = fetch_rss(url, count=4)
    if chunk:
        java_raw += f"\n[{name}]\n{chunk}\n"
    time.sleep(0.5)

java_summary = ask_ai(build_news_prompt("Java in AI/ML", java_raw, story_count=4))

if java_summary:
    telegram_msg = format_section_telegram("JAVA IN AI & ML", "☕", java_summary)
    send(telegram_msg)
    email_sections.append(
        build_news_section_email("Java in AI & ML", "#e76f00", "☕",
                                  news_to_html(java_summary, "#e76f00"))
    )

time.sleep(2)

# ── 4. CODING CHALLENGES (Telegram only) ──────────────────────────────────────

print("Generating coding challenges...")
learning_topic, difficulty = get_learning_topic()

if learning_topic:
    challenge = ask_ai(build_challenge_prompt(learning_topic, difficulty))
    topic_label = f"{learning_topic} ({difficulty})"
else:
    challenge = ask_ai(
        "Generate 3 Python coding challenges on fundamentals for a complete beginner.\n\n"
        "Note at top: Update learning_log.txt in your GitHub repo to get "
        "personalised challenges! Format: 2026-05-17: your topic | Easy\n\n"
        "EASY\nTask: [challenge]\nExpected output:\n[output]\n\n"
        "MEDIUM\nTask: [challenge]\nExpected output:\n[output]\n\n"
        "HARD\nTask: [challenge]\nHint: [hint]\nExpected output:\n[output]"
    )
    topic_label = "Python Fundamentals (default)"

if challenge:
    border = "═" * 32
    send(
        f"╔{border}╗\n"
        f"   💻  DAILY CODING CHALLENGES\n"
        f"╚{border}╝\n\n"
        f"📚 Topic: {topic_label}\n\n"
        f"{'─'*35}\n\n"
        f"{challenge}\n\n"
        f"{'─'*35}\n"
        f"✏️ Update your topic:\n"
        f"Edit learning_log.txt in your repo\n"
        f"Format: 2026-05-17: your topic | Easy"
    )

# ── Build and send email ───────────────────────────────────────────────────────

if email_sections:
    print("Building email...")
    html = build_full_email(today, weekday, "".join(email_sections))
    send_email(f"The Hermes Daily — {today} Morning Brief", html)

send(
    f"✅ 8 AM brief complete.\n\n"
    f"Research papers from 6:30 AM are also in your inbox.\n"
    f"Have a productive day!"
)

print("Morning brief complete!")
