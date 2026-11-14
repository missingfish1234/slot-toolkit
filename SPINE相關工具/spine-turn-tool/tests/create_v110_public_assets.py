"""Original vector-style demonstration artwork; no supplied artwork is copied."""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def draw_badge(back=False):
    scale, size = 4, 240
    image = Image.new('RGBA', (size * scale, size * scale))
    d = ImageDraw.Draw(image)
    points = []
    for i in range(32):
        a = -math.pi / 2 + i * math.pi / 16
        r = 112 if i % 2 == 0 else 92
        points.append(((120 + math.cos(a) * r) * scale,
                       (120 + math.sin(a) * r) * scale))
    d.polygon(points, fill='#168f75', outline='#074e49', width=3 * scale)
    inset = [(120 * scale + (x - 120 * scale) * .94,
              120 * scale + (y - 120 * scale) * .94) for x, y in points]
    d.line(inset + inset[:1], fill='#68e5b3', width=2 * scale, joint='curve')
    def ellipse(box, fill, outline=None, width=1):
        d.ellipse(tuple(int(v * scale) for v in box), fill=fill,
                  outline=outline, width=width * scale)
    ellipse((37, 37, 203, 203), '#8d591d')
    ellipse((40, 40, 200, 200), '#f6c65b', '#ffedb2', 3)
    ellipse((49, 49, 191, 191), '#c28a2b', '#9a631c', 2)
    ellipse((52, 52, 188, 188), '#f8d67c', '#ffe9a8', 2)
    if back:
        image = ImageOps.mirror(image)
        d = ImageDraw.Draw(image)
    font_path = Path('C:/Windows/Fonts/arialbd.ttf')
    font = ImageFont.truetype(str(font_path), 82 * scale)
    d.text((120 * scale, 114 * scale), 'B' if back else 'F', font=font,
           fill='#906021', stroke_width=scale, stroke_fill='#fff0bb', anchor='mm')
    d.polygon([(118 * scale, 167 * scale), (126 * scale, 177 * scale),
               (110 * scale, 177 * scale)], fill='#906021')
    return image.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == '__main__':
    for back, role in ((False, 'front'), (True, 'back')):
        target = ROOT / 'assets' / f'demo-irregular-{role}.png'
        draw_badge(back).save(target)
        print(target)
