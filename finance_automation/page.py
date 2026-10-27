"""One self-contained page with the results of the last run: images inlined, no server, no API call.

    python -m finance_automation.page    # writes output/index.html

Published on GitHub Pages by .github/workflows/pages.yml; the same file also opens straight from disk.
"""

import base64
import html
import json
import posixpath
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "index.html"
REPO = "https://github.com/gcabralcavalcanti/personal-finance-automation"

CSS = """
:root{--bg:#fbfaf8;--fg:#1c1b19;--muted:#5f5b55;--line:#e6e2dc;--card:#fff;--accent:#1f4e79}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe8;--muted:#a19d96;--line:#2c2b29;--card:#1b1b1a;
--accent:#8db7e0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:40px 16px 64px}
h1{font-size:1.7rem;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:1.25rem;margin:40px 0 10px}
h3{font-size:1.05rem;margin:22px 0 8px}
h4,h5,h6{font-size:.95rem;margin:16px 0 6px}
a{color:var(--accent)}
.lead{color:var(--muted);margin:0 0 10px;max-width:75ch}
.links{display:flex;flex-wrap:wrap;gap:6px 18px;font-weight:600;margin:0}
.note{color:var(--muted);font-size:.9rem}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:1.4rem;font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:.85rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:14px 0}
.card h3{margin-top:0}
figure{margin:14px 0}
figure img{display:block;max-width:100%;max-height:440px;width:auto;height:auto;
border:1px solid var(--line);border-radius:8px;background:#fff}
figcaption{color:var(--muted);font-size:.85rem;margin-top:4px}
.tw{overflow-x:auto;margin:10px 0}
table{border-collapse:collapse;font-size:.85rem}
th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{font-weight:600}
.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
details{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0;background:var(--card)}
summary{cursor:pointer;font-weight:600}
code{font-size:.9em;background:var(--line);padding:0 4px;border-radius:4px}
pre{overflow-x:auto;background:var(--bg);border:1px solid var(--line);padding:10px;border-radius:8px}
pre code{background:none;padding:0}
blockquote{margin:10px 0;padding-left:12px;border-left:3px solid var(--line);color:var(--muted)}
hr{border:0;border-top:1px solid var(--line);margin:18px 0}
footer{margin-top:48px;color:var(--muted);font-size:.85rem}
"""


def esc(s):
    return html.escape(str(s), quote=True)


def link(url, base):
    """Relative links in the reports point to the file on GitHub, so the page works anywhere."""
    if re.match(r"[a-z]+:|#", url):
        return url
    path = posixpath.normpath(posixpath.join(base, url.split("#")[0]))
    return f"{REPO}/blob/main/{path}"


def inline(text, base=""):
    out = []
    for part in re.split(r"(`[^`]+`)", text):
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{esc(part[1:-1])}</code>")
            continue
        part = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", part)  # figures are placed by the page itself
        part = esc(part)
        part = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", part)
        part = re.sub(
            r"\[([^\]]+)\]\(([^)\s]+)\)",
            lambda m: f'<a href="{esc(link(html.unescape(m.group(2)), base))}">{m.group(1)}</a>',
            part,
        )
        out.append(part)
    return "".join(out)


def table(rows, base):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    align, head, body = [], None, cells
    if len(cells) > 1 and all(re.fullmatch(r":?-{3,}:?", c) for c in cells[1] if c):
        align = [c.endswith(":") for c in cells[1]]
        head, body = cells[0], cells[2:]

    def tr(row, tag):
        return (
            "<tr>"
            + "".join(
                f"<{tag}{' class=r' if k < len(align) and align[k] else ''}>{inline(c, base)}</{tag}>"
                for k, c in enumerate(row)
            )
            + "</tr>"
        )

    thead = f"<thead>{tr(head, 'th')}</thead>" if head and any(head) else ""
    return f'<div class="tw"><table>{thead}<tbody>{"".join(tr(r, "td") for r in body)}</tbody></table></div>'


BLOCK = re.compile(r"(#{1,6}\s|\||>|```|[-*]\s|\d+\.\s)")


def md(text, base="", shift=1):
    """Small Markdown reader for the reports this repository writes: headings, tables, lists, code, quotes."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
        elif s.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append(f"<pre><code>{esc(chr(10).join(lines[i + 1 : j]))}</code></pre>")
            i = j + 1
        elif m := re.match(r"(#{1,6})\s+(.*)", s):
            n = min(len(m.group(1)) + shift, 6)
            out.append(f"<h{n}>{inline(m.group(2), base)}</h{n}>")
            i += 1
        elif re.fullmatch(r"-{3,}", s):
            out.append("<hr>")
            i += 1
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(table(rows, base))
        elif s.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(quote), base)}</blockquote>")
        elif re.match(r"([-*]|\d+\.)\s", s):
            tag, items = ("ol" if s[0].isdigit() else "ul"), []
            while i < len(lines) and lines[i].strip():
                t = lines[i].strip()
                if m := re.match(r"(?:[-*]|\d+\.)\s+(.*)", t):
                    items.append(m.group(1))
                else:
                    items[-1] += " " + t
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x, base)}</li>" for x in items) + f"</{tag}>")
        else:
            para = [s]
            i += 1
            while i < len(lines) and lines[i].strip() and not BLOCK.match(lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para), base)}</p>")
    return "\n".join(out)


def figure(path, caption):
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    img = f'<img src="data:{mime};base64,{data}" alt="{esc(caption)}">'
    return f"<figure>{img}<figcaption>{esc(caption)}</figcaption></figure>"


def kpis(items):
    return (
        '<div class="grid">'
        + "".join(f'<div class="kpi"><b>{esc(v)}</b><span>{esc(t)}</span></div>' for v, t in items)
        + "</div>"
    )


def details(title, inner, open_=False):
    return f"<details{' open' if open_ else ''}><summary>{esc(title)}</summary>{inner}</details>"


def page(title, lead, links, body, command):
    nav = "".join(f'<a href="{esc(u)}">{esc(t)}</a>' for t, u in links)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header><h1>{esc(title)}</h1><p class="lead">{lead}</p><p class="links">{nav}</p></header>
{body}
<footer>Built by <code>{esc(command)}</code> from the files in this repository, with no API call.
One file, no server: it also opens straight from disk.</footer>
</main>
</body>
</html>
"""


def brl(x):
    return f"R$ {x:,.2f}"


def build(out=OUT):
    reports = ROOT / "output"
    months = sorted(p.stem for p in reports.glob("20??-??.json"))
    last = json.loads((reports / f"{months[-1]}.json").read_text(encoding="utf-8"))
    evaluation = (reports / "eval.md").read_text(encoding="utf-8")
    accuracy = re.search(r"Accuracy \(all answers\): ([\d.]+%)", evaluation)
    body = [
        kpis(
            [
                (brl(last["income"]), f"income in {last['month']}"),
                (brl(-last["expenses"]), "expenses, every row in a category"),
                (f"{last['savings_rate']:.0%}", "savings rate"),
                ("OK" if last["reconciled"] else "check", "balance reconciled with the statement"),
                (accuracy.group(1) if accuracy else "-", "AI classifier accuracy on a hand-labelled set"),
            ]
        ),
        figure(ROOT / "docs" / "overview.png", "Monthly overview built from the synthetic statements"),
        "<h2>Monthly reports</h2>",
        (
            '<p class="note">Synthetic data: the real statements are private. Rules handle the usual shops; '
            "the AI handles the rest, and anything it is unsure about waits for my review and becomes a new rule.</p>"
        ),
    ]
    for k, month in enumerate(reversed(months)):
        report = (reports / f"{month}.md").read_text(encoding="utf-8")
        body.append(details(f"Report {month}", md(report, "output", shift=2), open_=k == 0))
    body.append("<h2>How well the AI classifies</h2>")
    body.append(details("Evaluation on the hand-labelled set", md(evaluation, "output", shift=2)))
    lead = (
        "Public version of the system I use for my own finances: it reads the bank statement, puts every transaction "
        "in a category and writes the monthly report, with rules first and the AI only for what the rules miss."
    )
    links = [("Code on GitHub", REPO), ("Final report (PDF)", f"{REPO}/blob/main/final-report.pdf")]
    html_ = page("Personal finance automation", esc(lead), links, "\n".join(body), "python -m finance_automation.page")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_, encoding="utf-8")
    return out


if __name__ == "__main__":
    sys.stdout.write(f"Written: {build().relative_to(ROOT)}\n")
