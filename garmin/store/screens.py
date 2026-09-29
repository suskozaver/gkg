from playwright.sync_api import sync_playwright
import pathlib
d = pathlib.Path(".").resolve()
CSS = """
body{margin:0;width:454px;height:454px;background:#000;font-family:"Roboto Condensed","Arial Narrow",Arial,sans-serif;color:#fff;overflow:hidden;position:relative}
.ring{position:absolute;inset:1px;border-radius:50%;border:12px solid #f9b600}
.ring.dim{border-color:#1e1e1e}
.arc{position:absolute;inset:1px;border-radius:50%;border:12px solid transparent;border-top-color:#f9b600;border-right-color:#f9b600;transform:rotate(-45deg)}
.c{position:absolute;width:100%;text-align:center}
.logo{position:absolute;left:50%;border-radius:50%;background:#f9b600;transform:translate(-50%,-50%)}
.logo::after{content:"";position:absolute;left:36%;top:22%;width:22%;height:40%;border:solid #1f1c12;border-width:0 .6em .6em 0;transform:rotate(45deg)}
.hd b{display:block;color:#f9b600;font-size:32px}
.hd span{color:#9e9e9e;font-size:24px}
.rows{position:absolute;left:0;right:0}
.row{height:72px;display:flex;align-items:center;gap:16px;border-radius:16px;font-size:32px;font-weight:700;color:#9e9e9e;box-sizing:border-box;padding:0 22px}
.row.on{background:#1e1e1e;color:#fff}
.box{width:30px;height:30px;border-radius:7px;border:3px solid #9e9e9e;box-sizing:border-box;flex:none;position:relative}
.on .box{border-color:#fff}
.done{color:#6b6b6b;text-decoration:line-through}
.done .box{background:#6b6b6b;border:0}
.done .box::after{content:"";position:absolute;left:10px;top:4px;width:7px;height:15px;border:solid #000;border-width:0 4px 4px 0;transform:rotate(45deg)}
.lrow{height:84px;border-radius:16px;text-align:center;box-sizing:border-box;padding-top:10px;position:relative}
.lrow.on{background:#1e1e1e}
.lrow.on::before{content:"";position:absolute;left:0;top:16px;bottom:16px;width:6px;border-radius:3px;background:#f9b600}
.lrow b{display:block;font-size:36px;color:#9e9e9e}
.lrow.on b{color:#fff}
.lrow span{font-size:24px;color:#6b6b6b;font-weight:700}
.lrow.on span{color:#f9b600}
"""
def row(t, done=False, on=False):
    return f'<div class="row {"done" if done else ""} {"on" if on else ""}"><div class="box"></div>{t}</div>'
SCREENS = {
 "screen-1-items": f"""
  <div class="c hd" style="top:42px"><b>Shopping</b><span>3 of 5 open</span></div>
  <div class="rows" style="top:124px;left:48px;right:48px">{row("Bread",on=True)}{row("Apples")}{row("Coffee")}{row("Milk",done=True)}</div>""",
 "screen-2-lists": """
  <div class="c hd" style="top:42px"><b>GKG</b><span>3 lists</span></div>
  <div class="rows" style="top:124px;left:40px;right:40px">
   <div class="lrow on"><b>Shopping</b><span>Pinned · 3 open</span></div>
   <div class="lrow" style="margin:0 10px"><b>Hike gear</b><span>7 open</span></div>
   <div class="lrow" style="margin:0 40px"><b>This week</b><span>All done</span></div></div>""",
 "screen-3-link": """
  <div class="ring dim"></div><div class="arc"></div>
  <div class="logo" style="top:80px;width:68px;height:68px;font-size:12px"></div>
  <div class="c" style="top:132px;font-size:30px;font-weight:700">Link this watch</div>
  <div class="c" style="top:180px;font-size:88px;font-weight:700;letter-spacing:2px">482 913</div>
  <div class="c" style="top:288px;font-size:28px;font-weight:700;color:#9e9e9e">gkg.example.com › Home</div>
  <div class="c" style="top:328px;font-size:28px;font-weight:700;color:#6b6b6b">2:14</div>""",
}
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, body in SCREENS.items():
        pg = b.new_page(viewport={"width": 454, "height": 454})
        pg.set_content(f"<html><head><style>{CSS}</style></head><body>{body}</body></html>")
        pg.screenshot(path=str(d / f"{name}.png"))
    b.close()
