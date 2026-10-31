"""マンガ風コマ割りメーカー komawari

画像1〜4枚とレイアウトを選ぶと、白地に黒枠コマと下部キャプション帯を持つ
マンガページ風 PNG を合成するツール。
日本語フォントは実行時に公開 URL から取得して /tmp にキャッシュする。
単一ファイル Flask（DB なし）。
"""
import io
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, render_template_string, request, send_file

app = Flask(__name__)

PAGE_W = 1000
MARGIN = 30
GAP = 20
BORDER = 6
CAPTION_H = 56
FONT_URL = "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf"
FONT_CACHE = os.path.join("/tmp", "komawari_font.otf")

# レイアウト名 -> (列数, 行数, コマ数, コマ高さ)
LAYOUTS = {
    "縦2コマ": (1, 2, 2, 460),
    "横2コマ": (2, 1, 2, 640),
    "3コマ": (1, 3, 3, 300),
    "4コマ": (2, 2, 4, 460),
}


class FontUnavailable(Exception):
    pass


def fetch_font_file():
    if os.path.exists(FONT_CACHE) and os.path.getsize(FONT_CACHE) > 100000:
        return FONT_CACHE
    try:
        req = urllib.request.Request(FONT_URL, headers={"User-Agent": "komawari"})
        with urllib.request.urlopen(req, timeout=30) as res:
            data = res.read()
    except Exception as e:
        raise FontUnavailable(str(e))
    if len(data) < 100000:
        raise FontUnavailable("downloaded font looks too small")
    with open(FONT_CACHE, "wb") as fh:
        fh.write(data)
    return FONT_CACHE


def get_font(size):
    """テストから差し替え可能にするため関数に切り出している。"""
    return ImageFont.truetype(fetch_font_file(), size)


def panel_boxes(layout):
    cols, rows, count, ph = LAYOUTS[layout]
    pw = (PAGE_W - MARGIN * 2 - GAP * (cols - 1)) // cols
    boxes = []
    for i in range(count):
        r, c = divmod(i, cols)
        x = MARGIN + c * (pw + GAP)
        y = MARGIN + r * (ph + GAP)
        boxes.append((x, y, pw, ph))
    total_h = MARGIN * 2 + rows * ph + GAP * (rows - 1)
    return boxes, total_h


def crop_to(img, w, h):
    src = img.convert("RGB")
    scale = max(w / src.width, h / src.height)
    resized = src.resize((max(int(src.width * scale + 0.5), w), max(int(src.height * scale + 0.5), h)))
    left = (resized.width - w) // 2
    top = (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def build_page(images, layout, captions):
    boxes, total_h = panel_boxes(layout)
    page = Image.new("RGB", (PAGE_W, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(page)
    font = get_font(30)
    for i, (x, y, w, h) in enumerate(boxes):
        if i < len(images) and images[i] is not None:
            panel = crop_to(images[i], w, h)
        else:
            panel = Image.new("RGB", (w, h), (230, 230, 230))
        page.paste(panel, (x, y))
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=(0, 0, 0), width=BORDER)
        caption = captions[i] if i < len(captions) else ""
        if caption:
            band_y = y + h - CAPTION_H
            draw.rectangle([x, band_y, x + w - 1, y + h - 1], fill=(255, 255, 255))
            draw.line([x, band_y, x + w - 1, band_y], fill=(0, 0, 0), width=3)
            text = caption
            while text and draw.textlength(text, font=font) > w - 20:
                text = text[:-1]
            tw = draw.textlength(text, font=font)
            draw.text((x + (w - tw) / 2, band_y + 12), text, font=font, fill=(0, 0, 0))
    return page


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>マンガ風コマ割りメーカー</title>
<style>body{font-family:sans-serif;max-width:640px;margin:2em auto;padding:0 1em}
.err{color:#b00}fieldset{margin:1em 0}</style>
</head><body>
<h1>マンガ風コマ割りメーカー</h1>
<p>写真やイラストをコマ割りレイアウトに流し込み、台詞つきのマンガ風ページ画像を作ります。</p>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('make') }}" enctype="multipart/form-data">
  <label>レイアウト
    <select name="layout">{% for name in layouts %}<option>{{ name }}</option>{% endfor %}</select></label>
  {% for i in range(1, 5) %}
  <fieldset><legend>コマ {{ i }}</legend>
    <input type="file" name="img{{ i }}" accept=".png,.jpg,.jpeg,.webp">
    <input type="text" name="cap{{ i }}" placeholder="台詞・キャプション（任意）" size="40">
  </fieldset>
  {% endfor %}
  <button type="submit">ページを作る</button>
</form>
</body></html>"""


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template_string(PAGE, layouts=list(LAYOUTS.keys()), error=None)


@app.route("/make", methods=["POST"])
def make():
    layout = request.form.get("layout", "縦2コマ")
    if layout not in LAYOUTS:
        layout = "縦2コマ"
    images, captions = [], []
    for i in range(1, 5):
        f = request.files.get(f"img{i}")
        img = None
        if f is not None and f.filename:
            try:
                img = Image.open(io.BytesIO(f.read()))
                img.load()
            except Exception:
                return render_template_string(PAGE, layouts=list(LAYOUTS.keys()), error=f"コマ{i}の画像を読み込めませんでした。"), 400
        images.append(img)
        captions.append((request.form.get(f"cap{i}") or "").strip())
    if all(img is None for img in images):
        return render_template_string(PAGE, layouts=list(LAYOUTS.keys()), error="画像を少なくとも1枚アップしてください。"), 400
    try:
        page = build_page(images, layout, captions)
    except FontUnavailable:
        return (
            render_template_string(PAGE, layouts=list(LAYOUTS.keys()),
                                   error="日本語フォントの取得に失敗しました。ネットワーク環境を確認して、もう一度お試しください。"),
            500,
        )
    out = io.BytesIO()
    page.save(out, format="PNG")
    out.seek(0)
    return send_file(out, mimetype="image/png", download_name="komawari.png", as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
