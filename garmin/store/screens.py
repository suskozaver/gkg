"""The three store screens, 454x454, drawn after Items.mc, Lists.mc and Pair.mc. Run: python screens.py"""
import math
import pathlib

from playwright.sync_api import sync_playwright

d = pathlib.Path(__file__).resolve().parent
Y, B = "#f9b600", "#007cc3"
CSS = """
body{margin:0;width:454px;height:454px;background:#000;font-family:"Roboto Condensed","Arial Narrow",Arial,sans-serif;color:#fff;overflow:hidden;position:relative}
svg.ring{position:absolute;inset:0}
.c{position:absolute;width:100%;text-align:center}
.hd b{display:block;color:#f9b600;font-size:38px;line-height:44px}
.hd span{color:#9e9e9e;font-size:28px}
.gk{color:#f9b600}.g{color:#007cc3}
.rows{position:absolute;left:0;right:0}
.row{height:86px;display:flex;align-items:center;gap:18px;border-radius:16px;font-size:38px;font-weight:700;color:#9e9e9e;box-sizing:border-box;padding:0 22px}
.row.on{background:#1e1e1e;color:#fff}
.box{width:36px;height:36px;border-radius:8px;border:3px solid #9e9e9e;box-sizing:border-box;flex:none;position:relative}
.on .box{border-color:#fff}
.done{color:#6b6b6b;text-decoration:line-through}
.done .box{background:#6b6b6b;border:0}
.done .box::after{content:"";position:absolute;left:12px;top:5px;width:8px;height:18px;border:solid #000;border-width:0 5px 5px 0;transform:rotate(45deg)}
.lrow{height:100px;border-radius:16px;text-align:center;box-sizing:border-box;padding-top:10px;position:relative}
.lrow.on{background:#1e1e1e}
.lrow.on::before{content:"";position:absolute;left:0;top:18px;bottom:18px;width:6px;border-radius:3px;background:#f9b600}
.lrow b{display:block;font-size:43px;color:#9e9e9e;line-height:50px}
.lrow.on b{color:#fff}
.lrow span{font-size:28px;color:#6b6b6b;font-weight:700}
.lrow.on span{color:#f9b600}
"""


def arc(start, sweep, color, r=220, cx=227, w=12):
    """Clockwise from `start` degrees (0 = 3 o'clock, 90 = top), as Gkg.arc draws it."""
    if sweep <= 0:
        return ""
    a0, a1 = math.radians(start), math.radians(start - sweep)
    p = lambda a: f"{cx + r * math.cos(a):.1f} {cx - r * math.sin(a):.1f}"
    if sweep >= 359.9:
        return f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}"/>'
    return f'<path d="M{p(a0)} A{r} {r} 0 {1 if sweep > 180 else 0} 1 {p(a1)}" fill="none" stroke="{color}" stroke-width="{w}"/>'


def brand_ring(frac, back=False):
    deg = 360 * frac
    out = arc(90, 360, "#1e1e1e") if back else ""
    return f'<svg class="ring" width="454" height="454">{out}{arc(90, min(deg, 180), B)}{arc(270, deg - 180, Y)}</svg>'


def logo(cx, cy, r):
    return (f'<svg style="position:absolute;left:{cx - r}px;top:{cy - r}px" width="{2 * r}" height="{2 * r}" viewBox="0 0 64 64">'
            f'<path d="M32 0a32 32 0 0 0 0 64z" fill="{Y}"/><path d="M32 0a32 32 0 0 1 0 64z" fill="{B}"/>'
            '<path d="M17 33l10 10L48 22" fill="none" stroke="#1f1c12" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def row(t, done=False, on=False):
    return f'<div class="row {"done" if done else ""} {"on" if on else ""}"><div class="box"></div>{t}</div>'


SCREENS = {
    "screen-1-items": f"""
  <div class="c hd" style="top:36px"><b>Shopping</b><span>3 of 5 open</span></div>
  <div class="rows" style="top:124px;left:44px;right:44px">{row("Bread", on=True)}{row("Apples")}{row("Coffee")}{row("Milk", done=True)}</div>""",
    "screen-2-lists": """
  <div class="c hd" style="top:36px"><b><span class="gk" style="font-size:38px;color:#f9b600">GK</span><span class="g" style="font-size:38px;color:#007cc3">G</span></b><span>3 lists</span></div>
  <div class="rows" style="top:124px;left:36px;right:36px">
   <div class="lrow on"><b>Shopping</b><span>Pinned · 3 open</span></div>
   <div class="lrow" style="margin:0 14px"><b>Hike gear</b><span>7 open</span></div>
   <div class="lrow" style="margin:0 50px"><b>This week</b><span>All done</span></div></div>""",
    "screen-3-link": f"""
  {brand_ring(134 / 180, back=True)}
  {logo(227, 80, 34)}
  <div class="c" style="top:132px;font-size:30px;font-weight:700">Link this watch</div>
  <div class="c" style="top:180px;font-size:88px;font-weight:700;letter-spacing:2px">482 913</div>
  <div class="c" style="top:288px;font-size:28px;font-weight:700;color:#9e9e9e">gkg.example.com › Home</div>
  <div class="c" style="top:328px;font-size:28px;font-weight:700;color:#6b6b6b">2:14</div>""",
}

if __name__ == "__main__":
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, body in SCREENS.items():
            pg = b.new_page(viewport={"width": 454, "height": 454})
            pg.set_content(f"<html><head><style>{CSS}</style></head><body>{body}</body></html>")
            pg.screenshot(path=str(d / f"{name}.png"))
        b.close()
