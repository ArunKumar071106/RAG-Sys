"""Builds docs/AAACET_Assistant_Deployment_Guide.pdf. Run: pip install reportlab && python docs/make_deployment_guide.py"""

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = str(__import__("pathlib").Path(__file__).with_name("AAACET_Assistant_Deployment_Guide.pdf"))
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", FONT_DIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", FONT_DIR + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", FONT_DIR + "DejaVuSansMono.ttf"))
pdfmetrics.registerFont(TTFont("Mono-Bold", FONT_DIR + "DejaVuSansMono-Bold.ttf"))
addMapping("Sans", 0, 0, "Sans"); addMapping("Sans", 1, 0, "Sans-Bold")
addMapping("Sans", 0, 1, "Sans"); addMapping("Sans", 1, 1, "Sans-Bold")

RED = colors.HexColor("#db2c1d")
NAVY = colors.HexColor("#323496")
GOLD = colors.HexColor("#e0ac2a")
INK = colors.HexColor("#1f2430")
MUTED = colors.HexColor("#5b6472")
CODE_BG = colors.HexColor("#f3f4f7")
TIP_BG = colors.HexColor("#eef4ff")
WARN_BG = colors.HexColor("#fff4e5")
LINE = colors.HexColor("#d8dee8")

S = {
    "title": ParagraphStyle("title", fontName="Sans-Bold", fontSize=26, leading=32, textColor=NAVY, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName="Sans", fontSize=13, leading=18, textColor=MUTED, spaceAfter=18),
    "h1": ParagraphStyle("h1", fontName="Sans-Bold", fontSize=17, leading=22, textColor=NAVY, spaceBefore=4, spaceAfter=8, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12.5, leading=17, textColor=RED, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Sans", fontSize=9.6, leading=14, textColor=INK, spaceAfter=5),
    "small": ParagraphStyle("small", fontName="Sans", fontSize=8.3, leading=11.5, textColor=MUTED, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=8.4, leading=11.2, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Sans-Bold", fontSize=8.4, leading=11.2, textColor=colors.white),
    "bullet": ParagraphStyle("bullet", fontName="Sans", fontSize=9.6, leading=14, textColor=INK, leftIndent=14,
                             bulletIndent=3, spaceAfter=2.5),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=7.9, leading=10.6, textColor=INK),
    "center": ParagraphStyle("center", fontName="Sans", fontSize=9.6, leading=14, alignment=TA_CENTER, textColor=MUTED),
}

story = []


def h1(text):
    story.append(Paragraph(text, S["h1"]))


def h2(text):
    story.append(Paragraph(text, S["h2"]))


def p(text, style="body"):
    story.append(Paragraph(text, S[style]))


def bullets(items, style="bullet", sym="•"):
    for item in items:
        story.append(Paragraph(item, S[style], bulletText=sym))


def steps(items):
    for n, item in enumerate(items, start=1):
        story.append(Paragraph(item, S["bullet"], bulletText=f"{n}."))


def code(text):
    pre = Preformatted(text.strip("\n"), S["code"])
    t = Table([[pre]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CODE_BG), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(t)
    story.append(Spacer(1, 5))


def box(title, lines, bg=TIP_BG, edge=NAVY):
    content = [Paragraph(f"<b>{title}</b>", S["body"])] + [Paragraph(x, S["body"]) for x in lines]
    t = Table([[content]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(KeepTogether([t, Spacer(1, 7)]))


def table(header, rows, widths, head_bg=NAVY):
    data = [[Paragraph(h, S["cellb"]) for h in header]] + [[Paragraph(c, S["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), head_bg), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CODE_BG]),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(t)
    story.append(Spacer(1, 8))


def checklist(items):
    rows = [[Paragraph("☐", S["cell"]), Paragraph(i, S["cell"])] for i in items]
    t = Table(rows, colWidths=[7 * mm, 163 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(t)
    story.append(Spacer(1, 8))


def architecture():
    d = Drawing(170 * mm, 62 * mm)
    W, H = 170 * mm, 62 * mm

    def node(x, y, w, h, title, sub, fill):
        d.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=fill, strokeColor=fill))
        d.add(String(x + w / 2, y + h - 14, title, fontName="Sans-Bold", fontSize=8.6, fillColor=colors.white, textAnchor="middle"))
        for k, line in enumerate(sub):
            d.add(String(x + w / 2, y + h - 26 - k * 10, line, fontName="Sans", fontSize=7, fillColor=colors.white, textAnchor="middle"))

    def arrow(x1, y1, x2, y2, label=""):
        d.add(Line(x1, y1, x2, y2, strokeColor=MUTED, strokeWidth=1.2))
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        tip = [x2, y2, x2 - 7 * math.cos(a - 0.4), y2 - 7 * math.sin(a - 0.4), x2 - 7 * math.cos(a + 0.4), y2 - 7 * math.sin(a + 0.4)]
        d.add(Polygon(tip, fillColor=MUTED, strokeColor=MUTED))
        if label:
            d.add(String((x1 + x2) / 2, (y1 + y2) / 2 + 4, label, fontName="Sans", fontSize=6.5, fillColor=MUTED, textAnchor="middle"))

    bw, bh, y = 88, 46, 110
    xs = [4, 120, 236, 352]
    node(xs[0], y, bw, bh, "Visitors", ["phone / laptop", "or college website"], MUTED)
    node(xs[1], y, bw, bh, "Caddy", ["HTTPS + free", "certificate"], NAVY)
    node(xs[2], y, bw, bh, "Frontend", ["nginx: chat page,", "proxies /api"], NAVY)
    node(xs[3], y, bw + 30, bh, "Backend (FastAPI)", ["search + answers,", "rate limits, admin"], RED)
    for a, b in zip(xs[:3], xs[1:]):
        arrow(a + bw, y + bh / 2, b, y + bh / 2, "https" if a == xs[0] else "")
    bx = xs[3] + (bw + 30) / 2
    node(xs[3] - 60, 18, 100, 44, "Qdrant", ["vector database", "(Docker volume)"], GOLD)
    node(xs[3] + 60, 18, 100, 44, "Claude API", ["writes answers", "(Anthropic, paid)"], colors.HexColor("#6b4fbb"))
    arrow(bx - 20, y, xs[3] - 10, 62)
    arrow(bx + 20, y, xs[3] + 110, 62)
    node(xs[0], 18, 210, 44, "Knowledge base", ["data/processed: website text + image info", "-> embeddings (FastEmbed, free, on server)"], colors.HexColor("#2f7d5b"))
    arrow(xs[0] + 210, 40, xs[3] - 60, 40, "indexed into")
    d.add(String(W / 2, H - 6, "Everything except the Claude API runs on your server in Docker", fontName="Sans", fontSize=7.5,
                 fillColor=MUTED, textAnchor="middle"))
    story.append(d)
    story.append(Spacer(1, 6))


def on_page(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setStrokeColor(RED); canvas.setLineWidth(1.5)
        canvas.line(20 * mm, A4[1] - 14 * mm, A4[0] - 20 * mm, A4[1] - 14 * mm)
        canvas.setFont("Sans", 7.5); canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, A4[1] - 12 * mm, "AAACET Virtual Assistant - Deployment Guide")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.drawString(20 * mm, 10 * mm, "Prices and provider screens change - check current details before buying.")
    canvas.restoreState()


# ============================================================== cover
story.append(Spacer(1, 30 * mm))
p("AAACET Virtual Assistant", "title")
p("Step-by-step guide: deploy, host, buy and connect the AI API, manage the vector database, and run it "
  "for AAA College of Engineering and Technology", "subtitle")
table(["What you will have at the end", ""], [
    ["Public address", "https://assistant.&lt;your-college-domain&gt; (for example assistant.aaaenggcoll.ac.in), with HTTPS"],
    ["Answers", "From the official website only, with links to every source; AI-written with a Claude API key"],
    ["Search", "Hybrid search (meaning + keywords) over 3,400 text and 4,800 image chunks in a Qdrant vector database"],
    ["Extras", "Suggestions while typing, questions in any language (with the key), embeddable on the college website"],
    ["Running cost", "A small cloud server (about US$12-25 / month) + Claude API usage (from under US$10 / month)"],
], [42, 128])
box("How to use this guide", [
    "Part A is a one-page quick path. Parts B-L explain every step. Part M lists things that are easy to forget, "
    "Part N fixes common problems, and Part O is the launch checklist to tick off.",
    "Commands in grey boxes are typed on the <b>server</b> (Linux) unless marked otherwise. Replace values in "
    "&lt;angle brackets&gt; with your own.",
])
p("Prepared for the RAG-Sys project (branch claude/admiring-johnson-xhrq59). Tested on the same Docker setup: "
  "image build, data loading, indexing into Qdrant, chat, suggestions, per-visitor rate limiting, admin access and "
  "HTTPS through Caddy (local certificate).", "small")
story.append(PageBreak())

# ============================================================== A. quick path
h1("A. The quick path (one page)")
steps([
    "<b>Get approval</b> from the principal / IT in-charge: the address, who maintains it, the monthly budget (Part B).",
    "<b>Rent a Linux server</b>: Ubuntu 24.04, 2 vCPU, 4 GB RAM (8 GB is faster for the first indexing), 40 GB disk, "
    "in an Indian region (Part C).",
    "<b>Point a subdomain</b> such as assistant.aaaenggcoll.ac.in to the server's IP address (Part D).",
    "<b>Install Docker</b>, copy the project to the server, fill in <font face='Mono'>.env</font> (Part E).",
    "<b>Start it</b>: build, load the knowledge base, switch on HTTPS (Part F).",
    "<b>Buy Claude API credits</b>, create a key, put it in <font face='Mono'>.env</font>, restart (Part G).",
    "<b>Test</b> with the checklist (Part F.6), then <b>add it to the college website</b> (Part J).",
    "<b>Schedule a weekly refresh</b> from the live website and <b>back up</b> (Parts I and K).",
])
code("""# On the server, after Parts C-E (Ubuntu 24.04 with Docker installed):
cd /opt/aaacet/app
cp .env.example .env && nano .env                  # API key, admin token, domain (Part E.3)
docker compose up -d --build                        # build and start (5-15 min the first time)
docker compose run --rm --no-deps --user root -v "$PWD/data/processed:/seed:ro" backend \\
  sh -c "mkdir -p /data/processed && cp -r /seed/. /data/processed/ \\
         && chown -R app:app /data/processed"
docker compose restart backend                      # indexes the data; chat works meanwhile
docker compose --profile https up -d                # HTTPS on your domain (free certificate)""")
box("What is already done for you", [
    "The website has been crawled (2,115 pages, 4,785 images) and cleaned into <font face='Mono'>data/processed</font>, "
    "which ships with the project. You do <b>not</b> need to crawl before launch; the server only has to index it "
    "into the vector database, which happens automatically on start.",
])
story.append(PageBreak())

# ============================================================== B. before you start
h1("B. Before you start: decisions and approvals")
p("A college-facing service needs a few non-technical decisions first. Getting them settled avoids rework later.")
table(["Decision", "Recommendation", "Who decides"], [
    ["Public address", "A subdomain of the college domain, e.g. <b>assistant.aaaenggcoll.ac.in</b>. Free; needs one DNS "
     "record from whoever manages the college domain.", "Principal / IT / website vendor"],
    ["Where it runs", "A small cloud server in India (simplest), or a college server if IT can open ports 80/443 to the "
     "internet (Part C).", "IT in-charge"],
    ["AI answers", "Buy Claude API credits with a college account and card; start with a small amount and a spend limit "
     "(Part G). Without a key it still works, quoting the website.", "Accounts / management"],
    ["Owner", "Name one staff member responsible for the server, the API account, updates and wrong-answer reports.",
     "HOD / principal"],
    ["Content", "The assistant only knows what is on the official website. Wrong or old information must be fixed "
     "<b>on the website</b>, then refreshed (Part I).", "Website / office staff"],
    ["Privacy notice", "Tell users not to type personal details, that questions are processed by an AI service, and "
     "to confirm important details (fees, dates) with the office.", "Management"],
], [32, 98, 40])
box("Branch and code", [
    "The finished work is on the GitHub branch <font face='Mono'>claude/admiring-johnson-xhrq59</font> of "
    "<font face='Mono'>ArunKumar071106/RAG-Sys</font>. Merging it into <font face='Mono'>main</font> through a pull "
    "request before deploying keeps one clear version to deploy and update.",
])

# ============================================================== C. hosting
h1("C. Choose where to host")
p("The app is four Docker containers (web page, backend, vector database, HTTPS). It needs a machine that runs "
  "continuously with Docker. Shared web hosting (cPanel / PHP hosting) <b>cannot</b> run it, and static hosts such as "
  "GitHub Pages or Netlify can only serve the page, not the backend.")
table(["Option", "Good for", "Approx. cost", "Notes"], [
    ["<b>Cloud VM in India (recommended)</b>: DigitalOcean (Bengaluru), AWS Lightsail/EC2 (Mumbai, Hyderabad), "
     "Azure (Pune, Chennai), Google Cloud (Mumbai, Delhi)", "Reliable public service with little IT effort",
     "US$12-25 / month for 2 vCPU, 4 GB", "Pick Ubuntu 24.04 LTS, x86-64. Easiest to get HTTPS working."],
    ["Oracle Cloud free tier (Mumbai, Hyderabad)", "Zero hosting cost", "Free (Arm VMs)",
     "Arm processors: the images should build, but this setup was not tested on Arm. Free capacity is not always available."],
    ["College's own server", "No monthly bill; data stays on campus", "Hardware you have",
     "Needs a public IP or port forwarding of 80/443 from the college router/firewall, and someone to keep it running."],
    ["Your laptop / PC", "Demos only", "-", "Turns off with the PC; not for students."],
], [52, 38, 32, 48])
h2("Server size")
table(["Resource", "Minimum", "Recommended", "Why"], [
    ["CPU", "2 vCPU", "2-4 vCPU", "Indexing the knowledge base and answering run on the CPU"],
    ["Memory", "4 GB", "8 GB", "Backend + embedding model + Qdrant; 8 GB makes the first indexing faster"],
    ["Disk", "30 GB", "40-60 GB SSD", "Docker images (~1.5 GB), data, model, logs, room for a full re-crawl with images"],
    ["OS", "Ubuntu 22.04", "Ubuntu 24.04 LTS", "Commands in this guide are for Ubuntu"],
], [25, 28, 32, 85])
p("A 2 vCPU / 4 GB server comfortably serves a college (dozens of people chatting at the same time). The slow part, "
  "the first build of the vector index, happens once and the chat works while it runs.", "small")

# ============================================================== D. domain
h1("D. Domain name and DNS")
steps([
    "Create the server first (Part E.1) and note its <b>public IPv4 address</b>, e.g. 203.0.113.25.",
    "Ask the person who manages <b>aaaenggcoll.ac.in</b> (IT team, website vendor or domain registrar account) to add:",
])
table(["Type", "Name / Host", "Value", "TTL"], [["A", "assistant", "&lt;server public IP&gt;", "300 (5 min) or default"]], [25, 45, 70, 30])
steps([
    "Wait 5-30 minutes, then check from your PC: <font face='Mono'>nslookup assistant.aaaenggcoll.ac.in</font> must show "
    "the server's IP. HTTPS (Part F.5) only works after this.",
])
box("No college domain access yet?", [
    "You can start with the server's IP address over plain HTTP (http://&lt;server-ip&gt;:8080) for internal testing. "
    "Do not announce it to students without HTTPS. A separate domain (e.g. a .in name, roughly Rs.500-1,000 a year) "
    "also works, but a subdomain of the official domain is more trustworthy for students.",
], bg=WARN_BG, edge=GOLD)
story.append(PageBreak())

# ============================================================== E. server setup
h1("E. Set up the server")
h2("E.1 Create the server")
steps([
    "Sign up with the cloud provider (college account). Create a VM / Droplet / instance: <b>Ubuntu 24.04 LTS</b>, "
    "2 vCPU / 4-8 GB, 40 GB SSD, region <b>India</b>.",
    "Authentication: choose <b>SSH key</b> (safer than a password). On Windows, PowerShell can create one: "
    "<font face='Mono'>ssh-keygen -t ed25519</font>, then paste the contents of <font face='Mono'>~/.ssh/id_ed25519.pub</font>.",
    "In the provider's firewall / security group allow inbound <b>22</b> (SSH), <b>80</b> and <b>443</b> (web). Nothing else.",
    "Connect from your PC: <font face='Mono'>ssh ubuntu@&lt;server-ip&gt;</font> (the user may be root, ubuntu or "
    "azureuser depending on the provider).",
])
h2("E.2 Install Docker and basic protection")
code("""sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh          # official Docker install script
sudo usermod -aG docker $USER                        # docker without sudo (after re-login)
sudo apt install -y git unattended-upgrades          # git + automatic security updates
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable""")
p("Log out (<font face='Mono'>exit</font>) and connect again, then check: <font face='Mono'>docker --version</font> and "
  "<font face='Mono'>docker compose version</font>.", "small")
h2("E.3 Copy the project to the server")
p("<b>Option 1 - git (best for updates).</b> The repository is private, so GitHub asks for your username and a "
  "<b>personal access token</b> (GitHub, Settings - Developer settings - Fine-grained tokens, read-only access to this "
  "repository) instead of a password.")
code("""sudo mkdir -p /opt/aaacet && sudo chown $USER /opt/aaacet && cd /opt/aaacet
git clone -b claude/admiring-johnson-xhrq59 https://github.com/ArunKumar071106/RAG-Sys.git app
cd app""")
p("<b>Option 2 - ZIP.</b> Download the branch ZIP on your PC, then upload and unpack it (from PowerShell on your PC):", "body")
code("""scp RAG-Sys.zip ubuntu@<server-ip>:/opt/aaacet/        # on your PC
ssh ubuntu@<server-ip>
cd /opt/aaacet && sudo apt install -y unzip && unzip RAG-Sys.zip && mv RAG-Sys-* app && cd app""")
h2("E.4 Fill in the settings file (.env)")
code("""cp .env.example .env
openssl rand -base64 32          # copy the output: this is your ADMIN_TOKEN
nano .env                        # edit, then Ctrl+O, Enter, Ctrl+X to save and exit""")
table(["Setting in .env", "Set it to", "Why"], [
    ["ANTHROPIC_API_KEY", "Your key from Part G (sk-ant-...); can be added later", "AI-written answers, any language"],
    ["ADMIN_TOKEN", "The random string from openssl", "Protects re-indexing (Part I). Never share it."],
    ["LLM_MODEL", "claude-sonnet-5-5 (balanced) or claude-haiku-5-5 (cheapest)", "Cost / quality choice (Part G.4)"],
    ["DOMAIN", "assistant.aaaenggcoll.ac.in (remove the # in front)", "Caddy gets the HTTPS certificate for it"],
    ["FRONTEND_PUBLISH", "127.0.0.1:8080 (remove the #)", "Plain-HTTP port only reachable on the server itself"],
    ["COMPOSE_PROFILES", "https (add this new line)", "So every 'docker compose up' also starts Caddy"],
    ["RATE_LIMIT_PER_MINUTE", "20 (default 30)", "Questions per visitor per minute; protects your API budget"],
], [40, 70, 60])
box("Keep .env secret", ["It holds the API key and admin token. Never put it in GitHub, WhatsApp or e-mail. "
                         "Keep a copy in a password manager or with the principal's office (Part K)."], bg=WARN_BG, edge=GOLD)
story.append(PageBreak())

# ============================================================== F. start
h1("F. Start the app")
h2("F.1 Build and start the containers")
code("""cd /opt/aaacet/app
docker compose up -d --build       # first build: 5-15 minutes (downloads Python packages)
docker compose ps                  # qdrant, backend, frontend (and caddy) should be "running" """)
h2("F.2 Load the knowledge base into the server")
p("The cleaned website content ships in <font face='Mono'>data/processed</font>. Copy it into the backend's data "
  "volume (this exact command was tested), then restart the backend:")
code("""docker compose run --rm --no-deps --user root -v "$PWD/data/processed:/seed:ro" backend \\
  sh -c "mkdir -p /data/processed && cp -r /seed/. /data/processed/ \\
         && chown -R app:app /data/processed"
docker compose restart backend""")
h2("F.3 Watch it build the vector index")
code("""docker compose logs -f backend     # Ctrl+C stops watching (the app keeps running)""")
p("You will see, in order: <font face='Mono'>Answering with keyword search while the semantic index is built</font> "
  "(chat works from here), progress lines <font face='Mono'>Indexing aaacet_text: 1152/3426 (34%)</font> and "
  "<font face='Mono'>aaacet_images</font>, then <font face='Mono'>Semantic index ready; answering with hybrid search</font>. "
  "On a 2-4 vCPU server expect roughly 10-40 minutes, once. The first start also downloads the 67 MB embedding model.")
h2("F.4 Check health")
code("""curl -s http://127.0.0.1:8080/api/health
# {"status":"ok", ..., "components":{"llm":"anthropic:claude-sonnet-5-5", ...},
#  "search":"hybrid"}""")
h2("F.5 Switch on HTTPS")
p("With DNS pointing at the server (Part D) and DOMAIN set:")
code("""docker compose --profile https up -d      # not needed if COMPOSE_PROFILES=https is in .env
docker compose logs caddy | grep -i certificate""")
p("Caddy obtains a free Let's Encrypt certificate and renews it automatically. Open "
  "<b>https://assistant.aaaenggcoll.ac.in</b>; plain http:// redirects to https://.")
h2("F.6 Test before announcing")
checklist([
    "The page loads on a phone and a laptop over https:// with the padlock.",
    "Typing 'ai&amp;ds fac' shows a suggestion; picking it lists the AI &amp; DS faculty table.",
    "Try: intake for B.E. and B.Tech, hostel facilities, bus transport, contact phone and e-mail, photos of the library.",
    "Each answer has source links that open the official website.",
    "With the API key: answers are written in plain words; a question in Tamil is answered in Tamil.",
    "An unrelated question (e.g. 'weather on the moon') says it is not covered instead of guessing.",
    "Ask the same question 25 times quickly: after the rate limit you see 'sending messages too quickly'.",
])
story.append(PageBreak())

# ============================================================== G. API
h1("G. Buy the Claude API and connect it")
p("The app calls Anthropic's <b>Claude API</b> (official <font face='Mono'>anthropic</font> Python library) to write "
  "answers and to translate non-English questions. Search, embeddings and OCR run free on your server.")
h2("G.1 Create the account and buy credits")
steps([
    "Go to <b>console.anthropic.com</b> and sign up with an official college e-mail (so the account belongs to the "
    "college, not a person). Create an organization named after the college.",
    "Open <b>Settings - Billing</b>. Add a payment method: a card enabled for <b>international online payments</b> "
    "(many Indian debit cards need this switched on in the bank app), or the college's corporate card.",
    "Buy a small amount of <b>prepaid credits</b> to start (for example US$10-20). Usage is deducted as students ask questions.",
    "Open <b>Settings - Limits</b> (or the billing page) and set a <b>monthly spend limit</b> and e-mail alerts, so a "
    "busy week cannot overspend.",
    "Open <b>API Keys</b> - <b>Create Key</b>, name it <font face='Mono'>aaacet-assistant-production</font>, copy it "
    "immediately (it is shown once). It starts with <font face='Mono'>sk-ant-</font>.",
])
p("Screens and names in the Console change from time to time; if a menu differs, look for Billing, Limits and API Keys.", "small")
h2("G.2 Connect the key to the app")
code("""cd /opt/aaacet/app
nano .env              # set ANTHROPIC_API_KEY=sk-ant-...  and  LLM_MODEL=claude-sonnet-5-5
docker compose up -d --force-recreate backend
curl -s http://127.0.0.1:8080/api/health
# "llm":"anthropic:claude-sonnet-5-5" in the output means the key is connected""")
p("If it still says <font face='Mono'>extractive</font>, check for spaces or quotes around the key, then "
  "<font face='Mono'>docker compose logs backend | grep -i anthropic</font>.", "small")
h2("G.3 What the API does in this app")
table(["Job", "Setting", "Notes"], [
    ["Write answers from the retrieved website text, with citations", "LLM_MODEL, LLM_EFFORT=low",
     "Only official content is sent; links not from the website are removed"],
    ["Translate a non-English question into an English search", "same model", "Answer comes back in the user's language"],
    ["Describe images (optional)", "VISION_ENABLED=true, VISION_MODEL", "Off by default; only needed for a re-crawl"],
    ["Back-up model if Claude declines a request", "LLM_SERVER_FALLBACKS=true", "Opus and Sonnet only; Haiku has no fallback"],
], [62, 50, 58])
h2("G.4 Which model, and what it costs")
table(["Model", "LLM_MODEL", "Price per million tokens (in / out)", "Per question*", "9,000 questions / month*"], [
    ["Claude Haiku 5.5", "claude-haiku-5-5", "US$0.10 / US$0.50", "&lt; US$0.001", "about US$8"],
    ["Claude Sonnet 5.5 (recommended start)", "claude-sonnet-5-5", "US$2 / US$10", "about US$0.02", "about US$160"],
    ["Claude Opus 5.5 (code default)", "claude-opus-5-5", "US$4 / US$20", "about US$0.04", "about US$320"],
], [36, 33, 40, 28, 33])
p("* Estimates: about 6,000 tokens of website text in and 600 out per answer (300 questions a day). Real use varies; "
  "watch the Console's usage page during the first weeks. Prices are Anthropic's list prices at the time of writing.", "small")
box("How to choose", [
    "Ask 15 typical questions (faculty, intake, hostel, transport, one in Tamil) with <b>claude-haiku-5-5</b>, then the same "
    "with <b>claude-sonnet-5-5</b>. If Haiku's answers are just as clear and correct, keep Haiku: it is about 20 times "
    "cheaper. Change the model any time in .env and recreate the backend (G.2).",
])
story.append(PageBreak())

# ============================================================== H. vector db
h1("H. The vector database: what it is, which is best, how your data gets in")
h2("H.1 How your website becomes searchable")
architecture()
table(["Stage", "What happens", "Where / tool"], [
    ["1. Crawl", "Downloads the official website pages, PDFs and image addresses (polite: obeys robots.txt, 1 s delay)", "Scrapy"],
    ["2. Extract", "Cleans menus and footers, keeps headings, tables (labelled rows) and image context", "BeautifulSoup"],
    ["3. Images", "Downloads images, removes duplicates, reads text in images (OCR)", "RapidOCR (free, local)"],
    ["4. Chunk", "Splits pages into pieces of up to ~800 tokens along headings; tables keep their header", "data/processed/*.jsonl"],
    ["5. Embed + index", "Turns every chunk into a vector (meaning) and a keyword index", "FastEmbed BGE-small -&gt; <b>Qdrant</b>; BM25"],
    ["6. Answer", "Hybrid search finds the best chunks; Claude writes the answer with citations", "Backend + Claude API"],
], [24, 100, 46])
p("Stages 1-4 are already done and shipped. Stage 5 runs automatically when the backend starts (Part F.2-F.3).")
h2("H.2 Which vector database is best for this?")
table(["Database", "Type", "Cost", "Fit for this app"], [
    ["<b>Qdrant (used, recommended)</b>", "Open source, runs in Docker on your server", "Free",
     "Already integrated and tested; fast; ~8,000 vectors is tiny for it; no extra account"],
    ["Qdrant Cloud", "Managed Qdrant", "Free 1 GB cluster, then paid",
     "Only if you do not want the database on your server: set QDRANT_URL and QDRANT_API_KEY in .env"],
    ["pgvector (PostgreSQL)", "Extension for Postgres", "Free",
     "Good if the college already runs Postgres; would need code changes here"],
    ["Pinecone", "Managed service", "Paid beyond a small free tier", "Works, but adds a vendor and cost for no gain at this size"],
    ["Chroma, Weaviate, Milvus", "Open source", "Free", "Fine products; no advantage over Qdrant here and would need code changes"],
], [38, 40, 32, 60])
p("<b>Recommendation: keep Qdrant in Docker</b> (the default). The whole college knowledge base takes only tens of "
  "megabytes, so the database is not a cost or speed concern.")
h2("H.3 Which embedding model?")
table(["EMBEDDING_PROVIDER / model", "Speed on a CPU", "Quality", "When to use"], [
    ["fastembed + BAAI/bge-small-en-v1.5 (default)", "Fast (minutes)", "Good", "Recommended start; 67 MB download"],
    ["fastembed + BAAI/bge-base-en-v1.5", "~3x slower to index", "A little better", "If you have 4+ vCPU and want slightly better search"],
    ["bge-m3 (needs WITH_ML: \"true\" in docker-compose.yml)", "Much slower, +2 GB image", "Best, multilingual",
     "Many non-English questions <b>without</b> a Claude key (with a key, questions are translated anyway)"],
], [60, 30, 25, 55])
p("Changing the model rebuilds the vector index automatically on the next start (the old vectors do not fit the new model).", "small")
h2("H.4 Add or change content")
bullets([
    "<b>Fix or add information on the official website</b> (including PDFs linked from it), then refresh (Part I). "
    "This keeps one source of truth: the assistant never contradicts the website.",
    "<b>Specific new pages</b> only: list their URLs in a text file and run "
    "<font face='Mono'>docker compose run --rm backend python -m rag.cli crawl --urls /data/new_urls.txt</font>, then "
    "refresh without re-crawling everything.",
    "Pages outside <font face='Mono'>aaaenggcoll.ac.in</font> are ignored on purpose (CRAWL_ALLOWED_DOMAINS).",
])
story.append(PageBreak())

# ============================================================== I. refresh
h1("I. Keep the knowledge base up to date")
p("The website changes (new notices, faculty, events). Refresh the assistant <b>weekly</b>; it re-reads the site, "
  "re-embeds only changed pages and swaps in the new index without downtime.")
h2("I.1 Refresh now")
code("""curl -s -X POST http://127.0.0.1:8080/api/admin/reindex \\
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" \\
  -d '{"recrawl": true}'
# -> {"id":"5f2c...","state":"queued",...}
# check progress with the id from the answer:
curl -s http://127.0.0.1:8080/api/admin/jobs/<id> -H "Authorization: Bearer <ADMIN_TOKEN>"
""")
p("A full re-crawl of 2,000+ pages and 4,800 images takes several hours because the crawler is deliberately polite. "
  "The assistant keeps answering with the current index meanwhile.", "small")
h2("I.2 Refresh automatically every Sunday at 2 a.m.")
p("First save the refresh command as a small script (paste your real token in place of &lt;ADMIN_TOKEN&gt;):")
code("""cat > $HOME/aaacet-refresh.sh <<'SH'
#!/bin/sh
curl -s -X POST http://127.0.0.1:8080/api/admin/reindex \\
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" \\
  -d '{"recrawl": true}'
echo " $(date)"
SH
chmod 700 $HOME/aaacet-refresh.sh                   # only you can read it (it holds the token)
$HOME/aaacet-refresh.sh                             # try it once by hand""")
p("Then schedule it:")
code("""crontab -e                                          # choose nano, add this one line, save:
0 2 * * 0 $HOME/aaacet-refresh.sh >> $HOME/aaacet-refresh.log 2>&1""")
box("After urgent website changes", ["Run I.1 by hand (e.g. after admission notices are published) instead of waiting for Sunday."])

# ============================================================== J. website
h1("J. Put it on the college website")
p("Ask the website team to add a link in the menu (e.g. 'Ask AAACET') and/or embed the chat on a page:")
code("""<iframe src="https://assistant.aaaenggcoll.ac.in/?embed=1" title="AAACET Virtual Assistant"
        style="width:100%;height:640px;border:0" loading="lazy"></iframe>""")
bullets([
    "<font face='Mono'>?embed=1</font> shows only the chat panel, without the header and footer.",
    "Embedding is allowed from https://aaaenggcoll.ac.in and https://www.aaaenggcoll.ac.in. For another site, add it to "
    "the <font face='Mono'>frame-ancestors</font> line in <font face='Mono'>frontend/nginx.conf</font> and rebuild "
    "(<font face='Mono'>docker compose up -d --build frontend</font>).",
    "WordPress: add a Custom HTML block with the iframe code on a page such as 'Virtual Assistant'.",
])

# ============================================================== K. updates, backups
h1("K. Updates and backups")
h2("K.1 Install a new version of the app")
code("""cd /opt/aaacet/app
git pull                                  # or upload and unpack the new ZIP over the folder
docker compose up -d --build              # rebuilds only what changed; the data volume is kept""")
p("If an update ships a newer <font face='Mono'>data/processed</font> and you do <b>not</b> run your own refreshes, "
  "repeat F.2 to load it; the backend re-indexes only the changed pages.", "small")
h2("K.2 What to back up")
table(["Item", "How", "Why"], [
    [".env", "Copy into a password manager / sealed office file", "Contains the API key and admin token"],
    ["Data volume (rag_data)", "Weekly, command below; keep a copy off the server", "Crawled content and index (can be rebuilt, but takes hours)"],
    ["Qdrant volume", "Optional", "Rebuilt automatically from rag_data on start"],
    ["Certificates (caddy_data)", "Optional", "Caddy re-issues certificates automatically"],
], [40, 70, 60])
code("""docker volume ls | grep rag_data                       # e.g. app_rag_data
docker run --rm -v app_rag_data:/data -v $HOME:/backup alpine \\
  tar czf /backup/rag_data-$(date +%F).tgz -C /data .""")
p("Most cloud providers also offer automatic weekly <b>server snapshots</b> for a small fee; switching them on is the simplest full backup.", "small")
story.append(PageBreak())

# ============================================================== L. security & monitoring
h1("L. Security and monitoring")
h2("L.1 Security checklist")
checklist([
    "SSH with keys only; disable password login (PasswordAuthentication no in /etc/ssh/sshd_config).",
    "Firewall allows only 22, 80, 443. FRONTEND_PUBLISH=127.0.0.1:8080 keeps the plain-HTTP port private. "
    "Note: ports published by Docker bypass ufw, so keep this setting.",
    "Strong random ADMIN_TOKEN; never in screenshots or chats. The backend and Qdrant are never published to the internet.",
    "API spend limit and alerts set in the Anthropic Console; rate limit per visitor set in .env (20-30 per minute).",
    "Automatic security updates on (unattended-upgrades) and a monthly 'sudo apt upgrade -y &amp;&amp; sudo reboot'.",
    "Rotate the API key if it may have leaked (create a new key, update .env, recreate backend, delete the old key).",
    "Privacy notice on the page: no personal details, AI-processed, confirm important information with the office. "
    "Review Anthropic's commercial terms and data policy with the college (India's DPDP Act 2023 applies to personal data).",
])
h2("L.2 Daily and weekly checks")
table(["Check", "Command / tool", "Healthy result"], [
    ["Containers running", "docker compose ps", "All 'running'; restart: unless-stopped brings them back after a reboot"],
    ["Health", "curl -s https://assistant.../api/health", "\"status\":\"ok\", \"search\":\"hybrid\""],
    ["Errors", "docker compose logs --since 24h backend | grep -i error", "Nothing new"],
    ["Uptime alerts", "UptimeRobot / Better Stack (free plans): monitor /api/health every 5 min", "E-mail if it goes down"],
    ["Disk space", "df -h /", "Below 80% used"],
    ["API cost", "console.anthropic.com usage page", "Within the monthly budget"],
], [32, 78, 60])

# ============================================================== M. easy to miss
h1("M. Things that are easy to miss")
bullets([
    "<b>Accuracy disclaimer</b>: the page footer already says answers come from the website; keep fees and dates "
    "confirmed by the office, especially during admissions.",
    "<b>Wrong answers</b>: give students a way to report them (an e-mail or Google Form link). Most fixes are website "
    "fixes followed by a refresh.",
    "<b>Admission season load</b>: before counselling, check the API spend limit and consider a 4 vCPU server for that month.",
    "<b>Ownership</b>: the API account, server account and domain should be in the college's name, with two people having access.",
    "<b>Handover notes</b>: keep this guide, the server IP, account names (not passwords) and the refresh schedule in the IT file.",
    "<b>Accessibility</b>: the chat works with the keyboard and screen readers; keep it that way when the website team embeds it.",
    "<b>Robots and permission</b>: the crawler only reads the college's own public website; get written approval from "
    "the website owner/vendor if they host it.",
    "<b>Logs and privacy</b>: logs record requests, not answers; do not add analytics that store students' questions "
    "without a privacy notice.",
    "<b>Costs in rupees</b>: card payments in US$ may add bank currency-conversion charges and taxes; plan the budget with a margin.",
    "<b>Branch</b>: after merging the branch into main, deploy from main so updates are simple (git pull).",
])

# ============================================================== N. troubleshooting
h1("N. Troubleshooting")
table(["You see", "Fix"], [
    ["Browser cannot open https://assistant...", "DNS not pointing to the server yet (nslookup), ports 80/443 closed in the provider "
     "firewall, or Caddy not started: docker compose --profile https up -d; docker compose logs caddy"],
    ["Chat: 'still starting up'", "The backend is loading; wait a minute. docker compose logs backend shows progress."],
    ["Chat: 'Something went wrong'", "docker compose ps; docker compose logs backend | tail -50"],
    ["Answers quote the website instead of AI text", "ANTHROPIC_API_KEY missing/invalid or no credits: check .env, "
     "recreate backend (G.2), check Console billing"],
    ["'sending messages too quickly' for everyone", "Visitors must reach the app through Caddy/nginx (not the backend "
     "directly); raise RATE_LIMIT_PER_MINUTE if many students share one campus IP address"],
    ["PermissionError on /data/processed", "Load the data with the exact F.2 command (copy as root, then chown to app)"],
    ["'Collection has N-d vectors but the embedder produces M-d'", "You changed the embedding model with an index "
     "from another model; it rebuilds on start, or run docker compose run --rm backend python -m rag.cli index --full"],
    ["Out of disk space", "docker system prune -f (removes old images); enlarge the disk"],
    ["Port 80/443 already in use", "Another web server (Apache/nginx) is installed on the host: stop and disable it"],
], [55, 115])
story.append(PageBreak())

# ============================================================== O. launch checklist
h1("O. Launch checklist")
h2("Before launch")
checklist([
    "Approval from management; owner named; privacy notice wording agreed.",
    "Server created (Ubuntu 24.04, 2 vCPU, 4-8 GB, India region), SSH key login, firewall 22/80/443.",
    "Docker installed; project copied to /opt/aaacet/app.",
    ".env filled: ANTHROPIC_API_KEY, ADMIN_TOKEN, LLM_MODEL, DOMAIN, FRONTEND_PUBLISH, COMPOSE_PROFILES=https.",
    "DNS A record for the subdomain points to the server (nslookup shows the IP).",
    "docker compose up -d --build; knowledge base loaded (F.2); logs show 'Semantic index ready'.",
    "https:// works with a padlock; http:// redirects.",
    "Claude credits bought, spend limit and alerts set, /api/health shows the anthropic model.",
    "Test checklist F.6 passed on phone and laptop.",
])
h2("After launch")
checklist([
    "Link / embed added to the college website (Part J).",
    "Weekly refresh scheduled with cron (Part I.2); first refresh run checked.",
    "Backups: .env stored safely; weekly data-volume backup or provider snapshots on (Part K).",
    "Uptime monitor on /api/health with e-mail alerts.",
    "First month: review API usage weekly; adjust LLM_MODEL and limits.",
    "Wrong-answer reports reviewed monthly; website corrected and refreshed.",
])
box("Need to start over?", [
    "Everything lives in /opt/aaacet/app and three Docker volumes. 'docker compose down' stops the app and keeps the "
    "data; the knowledge base can always be reloaded from data/processed (F.2).",
])

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=17 * mm,
                        title="AAACET Virtual Assistant - Deployment Guide", author="RAG-Sys project",
                        subject="Deploy, host, Claude API, vector database")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("written", OUT)
