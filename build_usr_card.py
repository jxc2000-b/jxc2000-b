#!/usr/bin/env python3
"""
Sources (plain text, no tags, no escaping):
  art.txt  — the ASCII art, one line per row # replace with your own art
  text.txt — the stats column:
               line 1            -> user header (dash rule is added)
               "- Something"     -> section header (dash rule + blank row above)
               ""                -> spacer row
               "Key: value"      -> ". " margin + yellow key + green value (exact colors can be changed)
               words before ":" yellow
               all single "." turn green
               "..." runs turn gray,
               "123++" green, "123--" red,  for Github stats row
               "Status:" rows get the  pulsing status dot.
                all regex matched 

Outputs:
  usr_card_mono.svg  — system font stack (Dina if installed, else Menlo...)
  usr_card_dina.svg — Dina embedded as a base64 data: URI (DINA_TTF),
                         16px on Dina's 0.5em grid, em-dashes swapped for
                         hyphens (Dina has no U+2014 glyph); art stays on the
                         Consolas/Menlo stack. "dina_regular" must be availiable in the directory otherwise this step is skipped
"""
import base64
import os
import re
import sys

ART_SRC = "art.txt"
TEXT_SRC = "text.txt"
DINA_TTF = "dina_regular.ttf"

ART_X = 32
TITLE_H = 41
LINE_W = 60          # header rules pad to this many characters
TYPE_CPS = 340       # typing speed, characters per second
LINE_GAP = 0.02      # pause between lines ("enter key")
PAL_W, PAL_H, PAL_GAP = 34, 18, 28
ANSI = ["#484f58", "#ff7b72", "#3fb950", "#d29922",
        "#58a6ff", "#bc8cff", "#39c5cf", "#b1bac4"]
BRIGHT = ["#6e7681", "#ffa198", "#56d364", "#e3b341",
          "#79c0ff", "#d2a8ff", "#56d4dd", "#f0f6fc"]


def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- art ----
if not os.path.exists(ART_SRC):
    sys.exit(f"{ART_SRC} not found - put the ASCII art there, one line per row")
art = [l.rstrip() for l in open(ART_SRC, encoding="utf-8").read().splitlines()] # art is read line by line into an array
while art and not art[0].strip():
    art.pop(0) 
while art and not art[-1].strip():
    art.pop()
lead = min(len(l) - len(l.lstrip(" ")) for l in art if l.strip())
art = [l[lead:] for l in art]

cols = max(len(l) for l in art)   # cols
n = len(art)                      # rows

# ---- stats ----
TOKEN = re.compile(r'(?P<dots>\.{2,})'
                   r'|(?P<add>[\d,]+\+\+)' #lmao lol
                   r'|(?P<del>[\d,]+--)'
                   r'|(?P<key>[A-Za-z_][A-Za-z_. ]*?)(?=:)')


def colorize(s):
    out, pos = [], 0
    for m in TOKEN.finditer(s):
        out.append(escape(s[pos:m.start()]))
        if m.lastgroup == "key":
            out.append(".".join(f'<tspan class="key">{escape(p)}</tspan>'
                                for p in m.group().split(".")))
        else:
            cls = {"dots": "cc", "add": "addColor", "del": "delColor"}[m.lastgroup]
            out.append(f'<tspan class="{cls}">{escape(m.group())}</tspan>')
        pos = m.end()
    out.append(escape(s[pos:]))
    return "".join(out)


if not os.path.exists(TEXT_SRC):
    sys.exit(f"{TEXT_SRC} not found - put the stats column there")
kept = []
for i, raw in enumerate(open(TEXT_SRC, encoding="utf-8").read().splitlines()):
    raw = raw.rstrip()
    if i == 0 or raw.startswith("- "):
        rule = "—" * (LINE_W - len(raw) - 1)
        kept.append((escape(raw) + " " + rule, raw + " " + rule))
    elif not raw:
        kept.append(('<tspan class="cc">. </tspan>', ". "))
    else:
        if raw.startswith("Status: "):
            # widen the gap after the colon to make room for the status dot
            raw = raw.replace("Status: ", "Status:    ", 1)
        kept.append(('<tspan class="cc">. </tspan>' + colorize(raw), ". " + raw))

# re-flow rows top to bottom: section headers ("- ...") get a blank row above
rel, cur = [], 0
for _, p in kept:
    if rel:
        cur += 40 if p.startswith("- ") else 20
    rel.append(cur)


def build(dst, char, stats_fs, font_family, extra_font_face="", dash_sub=None,
          title_fs=13, art_font=None, art_char=None):
    art_char = art_char or char       # art may use a different font/metrics
    art_font_css = f" font-family: {art_font};" if art_font else ""
    stats_w = max(round(len(p) * char * stats_fs) for _, p in kept)
    stats_h = rel[-1] + PAL_GAP + 2 * PAL_H

    # ---- layout: width-driven art scale, center the shorter column ----
    TOP_Y = TITLE_H + 33              # first baseline of the taller column
    art_budget = 1290 - stats_w - (ART_X + 40 + 20)
    art_fs = max(6, min(16, int(art_budget / (cols * art_char))))
    art_step = round(art_fs * 1.25)
    art_w = round(cols * art_char * art_fs)
    art_h = (n - 1) * art_step

    art_y0 = TOP_Y + max(0, (stats_h - art_h) // 2)
    stats_y0 = TOP_Y + max(0, (art_h - stats_h) // 2)
    art_bottom = art_y0 + art_h

    stats_x = ART_X + art_w + 40
    out_stats = []
    status_y = status_delay = None
    t = 0.15         # initial pause before typing starts
    for (l, plain), r in zip(kept, rel):
        y_new = stats_y0 + r
        chars = len(plain)
        dur = max(0.05, chars / TYPE_CPS)
        fill = "#3fb950" if plain.startswith(". ") else "#2dd4bf"  # headers in teal
        out_stats.append(
            f'<text class="line" x="{stats_x}" y="{y_new}" fill="{fill}" '
            f'style="animation-delay:{t:.2f}s;animation-duration:{dur:.2f}s;'
            f'animation-timing-function:steps({max(chars, 1)})">{l}</text>')
        if plain.startswith(". Status:"):
            status_y, status_delay = y_new, t + dur
        t += dur + LINE_GAP
    stats_bottom = stats_y0 + rel[-1]
    last_delay = t

    pal_y = stats_bottom + PAL_GAP
    pal_rects = []
    for r, row in enumerate((ANSI, BRIGHT)):
        for j, c in enumerate(row):
            delay = last_delay + 0.15 + (r * 8 + j) * 0.045
            pal_rects.append(f'<rect x="{stats_x + j * PAL_W}" y="{pal_y + r * PAL_H}" '
                             f'width="{PAL_W}" height="{PAL_H}" fill="{c}" '
                             f'style="animation-delay:{delay:.2f}s"/>')
    palette = '<g class="pal">\n' + "\n".join(pal_rects) + "\n</g>"

    status_dot = ""
    if status_y is not None:
        # centered in the 4-space gap that follows ". Status:" (9 chars in)
        cx = stats_x + round(9 * char * stats_fs) + 18
        cy = status_y - 5
        status_dot = (
            f'<g class="sdot" style="animation-delay:{status_delay:.2f}s">\n'
            f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="#22c55e" stroke-width="2" opacity="0.6"/>\n'
            f'<circle cx="{cx}" cy="{cy}" r="4" fill="#22c55e">\n'
            f'<animate attributeName="opacity" values="1;0.3;1" dur="3s" repeatCount="indefinite"/>\n'
            f'</circle>\n</g>')

    W = stats_x + stats_w + 20
    body_bottom = max(art_bottom, pal_y + 2 * PAL_H)
    prompt_y = body_bottom + 40
    H = prompt_y + 24
    cursor_x = ART_X + round(len("jxc2000-b@github:~$ ") * char * stats_fs)

    art_ts = "\n".join(f'<tspan x="{ART_X}" y="{art_y0 + i * art_step}">{escape(l)}</tspan>'
                       for i, l in enumerate(art))

    out = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="{font_family}" width="{W}px" height="{H}px" font-size="{stats_fs}px" role="img" aria-labelledby="cardtitle">
<title id="cardtitle">jxc2000-b@github — GitHub profile card</title>
<style>
{extra_font_face}@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
text {{ white-space: pre; }}
.art {{ font-size: {art_fs}px;{art_font_css} fill: #2dd4bf; }}
.line {{ font-size: {stats_fs}px; }}
.title {{ font-size: {title_fs}px; fill: #8b949e; }}
.key {{fill: #e3b341;}}
.value {{fill: #3fb950;}}
.addColor {{fill: #3fb950;}}
.delColor {{fill: #f85149;}}
.cc {{fill: #616e7f;}}
.pu {{fill: #39d353;}}
.pp {{fill: #79c0ff;}}
@keyframes type {{ from {{ clip-path: inset(-6px 100% -6px -4px); }} to {{ clip-path: inset(-6px -12px -6px -4px); }} }}
@keyframes blink {{ 0%, 45% {{opacity: 1;}} 50%, 95% {{opacity: 0;}} 100% {{opacity: 1;}} }}
@keyframes pop {{ from {{opacity: 0;}} to {{opacity: 1;}} }}
.line {{ animation: type .4s steps(40) both; }}
.pal rect, .sdot {{ animation: pop .12s ease-out both; }}
.prompt {{ animation: type .3s steps(16) {last_delay + 1.0:.2f}s both; }}
.cursor {{ fill: #c9d1d9; animation: blink 1.1s linear infinite {last_delay + 1.35:.2f}s; }}
@media (prefers-reduced-motion: reduce) {{ .line, .pal rect, .sdot, .prompt, .cursor {{ animation: none; }} }}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#0d1117"/>
<stop offset="1" stop-color="#161b22"/>
</linearGradient>
<radialGradient id="glowg">
<stop offset="0" stop-color="#2dd4bf" stop-opacity="0.08"/>
<stop offset="1" stop-color="#2dd4bf" stop-opacity="0"/>
</radialGradient>
<radialGradient id="glowp">
<stop offset="0" stop-color="#3fb950" stop-opacity="0.06"/>
<stop offset="1" stop-color="#3fb950" stop-opacity="0"/>
</radialGradient>
<clipPath id="card"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="15"/></clipPath>
</defs>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="15.5" fill="url(#bg)" stroke="#30363d"/>
<g clip-path="url(#card)">
<rect x="1" y="1" width="{W - 2}" height="{TITLE_H - 1}" fill="#010409"/>
<line x1="1" y1="{TITLE_H}.5" x2="{W - 1}" y2="{TITLE_H}.5" stroke="#21262d"/>
<circle cx="26" cy="21" r="6.5" fill="#ff5f57"/>
<circle cx="48" cy="21" r="6.5" fill="#febc2e"/>
<circle cx="70" cy="21" r="6.5" fill="#28c840"/>
<text class="title" x="{W // 2}" y="26" text-anchor="middle">jxc2000-b@github: ~ — neofetch</text>
<ellipse cx="{ART_X + art_w // 2}" cy="{H // 2}" rx="{art_w // 2 + 80}" ry="{H // 2 - 40}" fill="url(#glowg)"/>
<ellipse cx="{stats_x + stats_w // 2}" cy="{H // 2}" rx="{stats_w // 2 + 60}" ry="{H // 2 - 40}" fill="url(#glowp)"/>
</g>
<text class="art" x="{ART_X}" y="{art_y0}">
{art_ts}
</text>
{chr(10).join(out_stats)}
{status_dot}
{palette}
<text class="prompt" x="{ART_X}" y="{prompt_y}"><tspan class="pu">jxc2000-b@github</tspan><tspan class="cc">:</tspan><tspan class="pp">~</tspan><tspan class="cc">$</tspan></text>
<rect class="cursor" x="{cursor_x}" y="{prompt_y - 12}" width="{round(char * stats_fs)}" height="15" rx="1"/>
</svg>
"""

    if dash_sub:
        out = out.replace("—", dash_sub)
    out = "\n".join(l.rstrip() for l in out.splitlines()) + "\n"
    open(dst, "w", encoding="utf-8").write(out)
    print(f"{dst}: art {n}x{cols} @ {art_fs}px/{art_step}px ({art_w}px wide), "
          f"stats @ x={stats_x} ({stats_w}px), card {W}x{H}")


build("usr_card_mono.svg", 0.6, 15,
      "Dina,Menlo,ConsolasFallback,Consolas,'SF Mono','DejaVu Sans Mono',monospace")

if os.path.exists(DINA_TTF):
    b64 = base64.b64encode(open(DINA_TTF, "rb").read()).decode()
    dina_face = ("@font-face {\n"
                 "font-family: 'DinaEmbed';\n"
                 f"src: url(data:font/ttf;base64,{b64}) format('truetype');\n"
                 "}\n")
    build("usr_card_dina.svg", 0.5, 16, "DinaEmbed,Dina,Menlo,monospace",
          extra_font_face=dina_face, dash_sub="-", title_fs=16,
          art_font="Menlo,ConsolasFallback,Consolas,'SF Mono','DejaVu Sans Mono',monospace",
          art_char=0.6)
else:
    print(f"{DINA_TTF} not found - skipped usr_card_dina.svg")
