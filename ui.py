"""Visual language for the dashboard (owner 2026-11-24: premium, Apple-like, "feel like magic").

Pure functions that return HTML/CSS strings so the look is testable without Streamlit.
All text passed in is escaped; nothing here reads or writes data."""
import datetime as dt
import html

CSS = """<style>
:root{
  --bg:#000;--card:rgba(28,28,30,.62);--card-solid:#1c1c1e;--line:rgba(255,255,255,.09);--line-strong:rgba(255,255,255,.16);
  --text:#f5f5f7;--dim:#a1a1a6;--faint:#6e6e73;--blue:#0a84ff;--indigo:#5e5ce6;--purple:#bf5af2;--pink:#ff375f;
  --green:#30d158;--orange:#ff9f0a;--red:#ff453a;--teal:#64d2ff;
  --radius:22px;--shadow:0 1px 0 rgba(255,255,255,.04) inset,0 20px 50px -20px rgba(0,0,0,.8);
}
html,body,[class*="css"],.stApp,button,input,textarea,select{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Helvetica Neue",Inter,Arial,sans-serif!important;-webkit-font-smoothing:antialiased;letter-spacing:-.003em}
.stApp{background:
  radial-gradient(1200px 600px at 15% -10%,rgba(94,92,230,.22),transparent 60%),
  radial-gradient(900px 500px at 95% 0%,rgba(10,132,255,.18),transparent 60%),
  radial-gradient(800px 600px at 50% 110%,rgba(191,90,242,.10),transparent 60%),#000!important}
.block-container{padding-top:2.2rem;max-width:1120px}
header[data-testid="stHeader"]{background:transparent}
h1,h2,h3{letter-spacing:-.025em;font-weight:680}
h3{font-size:1.3rem!important}
@keyframes vmc-rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes vmc-pulse{0%{box-shadow:0 0 0 0 var(--glow)}70%{box-shadow:0 0 0 14px transparent}100%{box-shadow:0 0 0 0 transparent}}
@keyframes vmc-sheen{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes vmc-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}

.vmc-hero{animation:vmc-rise .6s cubic-bezier(.2,.8,.2,1) both;margin:.2rem 0 1.4rem}
.vmc-eyebrow{display:flex;align-items:center;gap:.6rem;color:var(--dim);font-size:.82rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
.vmc-orb{--glow:rgba(48,209,88,.55);width:10px;height:10px;border-radius:50%;background:var(--green);animation:vmc-pulse 2.2s infinite}
.vmc-orb.warn{--glow:rgba(255,159,10,.55);background:var(--orange)}
.vmc-orb.bad{--glow:rgba(255,69,58,.6);background:var(--red)}
.vmc-orb.busy{--glow:rgba(10,132,255,.6);background:var(--blue)}
.vmc-title{font-size:3.1rem;font-weight:760;letter-spacing:-.045em;line-height:1.04;margin:.35rem 0 .2rem;
  background:linear-gradient(92deg,#fff 0%,#e8e8ff 35%,#a7b4ff 62%,#d6a8ff 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.vmc-lede{color:var(--dim);font-size:1.16rem;line-height:1.45;max-width:760px}
.vmc-lede b{color:var(--text);font-weight:620}

.vmc-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:0 0 1.2rem}
@media (max-width:820px){.vmc-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.vmc-title{font-size:2.3rem}}
.vmc-tile{position:relative;overflow:hidden;background:var(--card);backdrop-filter:blur(24px) saturate(160%);-webkit-backdrop-filter:blur(24px) saturate(160%);
  border:1px solid var(--line);border-radius:var(--radius);padding:18px 18px 16px;box-shadow:var(--shadow);animation:vmc-rise .6s cubic-bezier(.2,.8,.2,1) both}
.vmc-tile:nth-child(2){animation-delay:.05s}.vmc-tile:nth-child(3){animation-delay:.1s}.vmc-tile:nth-child(4){animation-delay:.15s}
.vmc-tile::after{content:"";position:absolute;inset:-1px;border-radius:inherit;pointer-events:none;background:linear-gradient(135deg,var(--tint,rgba(10,132,255,.18)),transparent 45%)}
.vmc-tile .k{color:var(--dim);font-size:.8rem;font-weight:600;letter-spacing:.02em}
.vmc-tile .v{font-size:2.3rem;font-weight:720;letter-spacing:-.04em;line-height:1.1;margin-top:.2rem;color:var(--text)}
.vmc-tile .s{color:var(--faint);font-size:.8rem;margin-top:.15rem}
.vmc-meter{height:5px;border-radius:9px;background:rgba(255,255,255,.08);margin-top:.6rem;overflow:hidden}
.vmc-meter>i{display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,var(--blue),var(--purple))}

.vmc-card{background:var(--card);backdrop-filter:blur(24px) saturate(160%);-webkit-backdrop-filter:blur(24px) saturate(160%);border:1px solid var(--line);
  border-radius:var(--radius);padding:20px 22px;box-shadow:var(--shadow);margin-bottom:14px;animation:vmc-rise .55s cubic-bezier(.2,.8,.2,1) both}
.vmc-card h4{margin:0 0 .35rem;font-size:1.08rem;font-weight:660;letter-spacing:-.015em;color:var(--text)}
.vmc-row{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--line)}
.vmc-row:first-of-type{border-top:0}
.vmc-icon{flex:0 0 30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:.95rem;background:rgba(255,255,255,.07)}
.vmc-icon.ok{background:rgba(48,209,88,.16);color:var(--green)}.vmc-icon.warn{background:rgba(255,159,10,.16);color:var(--orange)}
.vmc-icon.info{background:rgba(10,132,255,.16);color:var(--blue)}.vmc-icon.pause{background:rgba(191,90,242,.16);color:var(--purple)}
.vmc-row .t{font-weight:620;color:var(--text);font-size:.95rem}
.vmc-row .d{color:var(--dim);font-size:.86rem;line-height:1.4;margin-top:.1rem}
.vmc-row .d code{background:rgba(255,255,255,.08);border-radius:6px;padding:.05rem .35rem;color:var(--text);font-size:.82rem}
.vmc-chip{display:inline-flex;align-items:center;gap:.3rem;padding:.16rem .62rem;border-radius:999px;font-size:.74rem;font-weight:620;
  background:rgba(255,255,255,.08);color:var(--text);margin:.15rem .3rem .15rem 0;white-space:nowrap}
.vmc-chip.blue{background:rgba(10,132,255,.16);color:#7cc0ff}.vmc-chip.green{background:rgba(48,209,88,.15);color:#6fe08f}
.vmc-chip.orange{background:rgba(255,159,10,.15);color:#ffc266}.vmc-chip.purple{background:rgba(191,90,242,.16);color:#dcaaff}
.vmc-chip.pink{background:rgba(255,55,95,.15);color:#ff8aa5}.vmc-chip.teal{background:rgba(100,210,255,.14);color:#9fe3ff}
.vmc-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-top:.5rem}
.vmc-short{display:block;text-decoration:none!important;color:var(--text)!important;border-radius:16px;overflow:hidden;background:var(--card-solid);
  border:1px solid var(--line);transition:transform .25s cubic-bezier(.2,.8,.2,1),border-color .25s}
.vmc-short:hover{transform:translateY(-3px) scale(1.02);border-color:var(--line-strong)}
.vmc-short img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}
.vmc-short div{padding:8px 10px 10px;font-size:.8rem;line-height:1.3;color:var(--dim)}
.vmc-short b{display:block;color:var(--text);font-weight:600;font-size:.82rem;margin-bottom:.15rem;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.vmc-meta{color:var(--dim);font-size:.86rem;line-height:1.4;margin-bottom:.45rem}
[data-testid="stToolbar"],[data-testid="stDecoration"],.stDeployButton,#MainMenu{display:none!important}
.vmc-empty{color:var(--dim);text-align:center;padding:26px 10px;font-size:.95rem}
.vmc-sheen{background:linear-gradient(90deg,var(--dim) 0%,#fff 50%,var(--dim) 100%);background-size:200% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:vmc-sheen 2.6s linear infinite;font-weight:620}

div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:var(--radius);border-color:var(--line)!important;background:var(--card);
  backdrop-filter:blur(24px) saturate(160%);-webkit-backdrop-filter:blur(24px) saturate(160%);box-shadow:var(--shadow);transition:border-color .25s}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:var(--line-strong)!important}
.stButton>button,.stDownloadButton>button,.stLinkButton>a,.stFormSubmitButton>button{border-radius:980px;font-weight:620;padding:.5rem 1.15rem;
  border:1px solid var(--line-strong);background:rgba(255,255,255,.06);transition:transform .15s,filter .2s,background .2s}
.stButton>button:hover,.stLinkButton>a:hover{background:rgba(255,255,255,.12);transform:translateY(-1px)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:linear-gradient(180deg,#2b95ff,#0a74ff);border:0;color:#fff;
  box-shadow:0 8px 24px -10px rgba(10,132,255,.9)}
.stButton>button[kind="primary"]:hover{filter:brightness(1.1)}
.stButton>button:disabled{opacity:.45;transform:none}
div[data-baseweb="tab-list"]{gap:4px;background:rgba(255,255,255,.06);padding:4px;border-radius:14px;width:fit-content;border:1px solid var(--line)}
button[data-baseweb="tab"]{font-weight:620;font-size:.95rem;padding:.42rem 1.05rem;border-radius:10px;height:auto}
button[data-baseweb="tab"][aria-selected="true"]{background:rgba(255,255,255,.14)}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none}
[data-testid="stExpander"] details{border-radius:16px;border-color:var(--line);background:rgba(255,255,255,.02)}
[data-testid="stImage"] img,video{border-radius:16px}
[data-testid="stImage"] img{transition:transform .35s cubic-bezier(.2,.8,.2,1)}
[data-testid="stImage"]:hover img{transform:scale(1.02)}
.stProgress>div>div>div>div{background:linear-gradient(90deg,var(--blue),var(--purple),var(--pink));background-size:200% 100%;animation:vmc-sheen 3s linear infinite}
input,textarea,[data-baseweb="select"]>div{border-radius:12px!important}
</style>"""

NICHE_COLORS = {'World news': 'orange', 'Politics': 'orange', 'Crime and incidents': 'pink', 'Celebrities': 'purple',
                'Football': 'green', 'Sports': 'green', 'GTA 6 and gaming': 'blue', 'Streamers and creators': 'blue',
                'Money and business': 'teal', 'Tech and engineering': 'teal', 'Dance and music culture': 'purple',
                'Movies and TV': 'pink', 'Interviews and debates': 'orange', 'Viral moments': 'blue'}


def esc(text):
    return html.escape(str(text if text is not None else ''), quote=True)


def chip(text, color=''):
    return f'<span class="vmc-chip {esc(color)}">{esc(text)}</span>'


def niche_chip(name):
    return chip(name, NICHE_COLORS.get(name, 'blue'))


def orb_class(health_status, busy=False, autopilot_on=True):
    if busy: return 'busy'
    if health_status == 'needs_you': return 'warn'
    if not autopilot_on: return 'warn'
    return ''


def hero(eyebrow, lede_html, orb=''):
    return (f'<div class="vmc-hero"><div class="vmc-eyebrow"><span class="vmc-orb {esc(orb)}"></span>{esc(eyebrow)}</div>'
            f'<div class="vmc-title">Viral Moment Clips</div><div class="vmc-lede">{lede_html}</div></div>')


def tile(label, value, sub='', meter=None, tint=''):
    style = f' style="--tint:{esc(tint)}"' if tint else ''
    bar = f'<div class="vmc-meter"><i style="width:{max(0, min(100, int(meter)))}%"></i></div>' if meter is not None else ''
    return f'<div class="vmc-tile"{style}><div class="k">{esc(label)}</div><div class="v">{esc(value)}</div><div class="s">{esc(sub)}</div>{bar}</div>'


def tiles(items):
    return '<div class="vmc-tiles">' + ''.join(items) + '</div>'


def row(icon, title, detail_html='', kind=''):
    return (f'<div class="vmc-row"><div class="vmc-icon {esc(kind)}">{esc(icon)}</div><div><div class="t">{esc(title)}</div>'
            f'<div class="d">{detail_html}</div></div></div>')


def card(title, body_html, subtitle=''):
    sub = f'<div class="vmc-meta" style="margin-bottom:.4rem">{esc(subtitle)}</div>' if subtitle else ''
    return f'<div class="vmc-card"><h4>{esc(title)}</h4>{sub}{body_html}</div>'


def code(text):
    return f'<code>{esc(text)}</code>'


def health_card(report):
    """The self-repair summary: what needs the owner (rare), what the app handled, what is paused."""
    rows = []
    for item in report.get('needs_you', []):
        detail = esc(item.get('why', '')) + '<br><b style="color:var(--text)">Do this:</b> ' + esc(item.get('owner') or item.get('action', ''))
        rows.append(row('!', f"{item['title']}", detail, 'warn'))
    for item in report.get('handled', [])[:6]:
        times = f" · {item['times']}×" if item.get('times', 1) > 1 else ''
        rows.append(row('✓', item['title'] + times, esc(item.get('action', '')), 'ok'))
    for item in report.get('paused', []):
        rows.append(row('❚❚', f"Paused: {item['name']}", 'Until ' + esc(item.get('until', '')[:16].replace('T', ' ')) + ' UTC · ' + esc(item.get('reason', '')[:120]), 'pause'))
    for item in [x for x in report.get('fixes', []) if not x.get('message', '').startswith('Paused')][-4:]:
        rows.append(row('✦', 'Fixed automatically', esc(item.get('message', '')), 'info'))
    if not rows:
        rows.append(row('✓', 'No problems in the last 24 hours', 'Every step finished on the first try.', 'ok'))
    return card('Self-repair', ''.join(rows), report.get('headline', ''))


def shorts_strip(items):
    """Today's posted Shorts as thumbnails linking to YouTube. items: dicts with video_id, title, when."""
    if not items: return '<div class="vmc-empty">Nothing posted yet today. The first post goes out at the next slot.</div>'
    cells = []
    for item in items:
        vid = esc(item['video_id'])
        cells.append(f'<a class="vmc-short" href="https://youtube.com/shorts/{vid}" target="_blank" rel="noopener">'
                     f'<img src="https://i.ytimg.com/vi/{vid}/mqdefault.jpg" alt="" loading="lazy">'
                     f'<div><b>{esc(item.get("title", ""))}</b>{esc(item.get("when", ""))}</div></a>')
    return '<div class="vmc-strip">' + ''.join(cells) + '</div>'


def next_tick(now_local):
    """Autopilot runs every hour at :07."""
    candidate = now_local.replace(minute=7, second=0, microsecond=0)
    if candidate <= now_local: candidate += dt.timedelta(hours=1)
    return candidate


def clock(moment):
    text = moment.strftime('%I:%M %p')
    return text[1:] if text.startswith('0') else text


def greeting(now_local):
    hour = now_local.hour
    return 'Good morning' if 5 <= hour < 12 else 'Good afternoon' if hour < 18 else 'Good evening'
