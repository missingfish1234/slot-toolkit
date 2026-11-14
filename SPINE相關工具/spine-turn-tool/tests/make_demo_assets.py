"""Draw original asymmetric fixtures; no external artwork or network required."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

ROOT = Path(__file__).resolve().parents[1]


def make_demo_assets(destination=None):
    dest = Path(destination or ROOT / 'assets')
    dest.mkdir(parents=True, exist_ok=True)
    font_path = Path('C:/Windows/Fonts/arialbd.ttf')
    font = ImageFont.truetype(str(font_path), 116) if font_path.exists() else ImageFont.load_default(size=116)
    small = ImageFont.truetype(str(font_path), 25) if font_path.exists() else ImageFont.load_default(size=25)
    paths = {}
    for side, base, label, top in [
        ('front', '#dfa937', 'F', 'FRONT'),
        ('back', '#ae7030', 'B', 'BACK'),
    ]:
        im = Image.new('RGBA', (320, 320))
        d = ImageDraw.Draw(im)
        d.ellipse((13, 13, 307, 307), fill=base, outline='#603d16', width=5)
        d.ellipse((25, 25, 295, 295), outline='#ffdb7e', width=5)
        d.ellipse((39, 39, 281, 281), outline='#80501c', width=3)
        for k in range(40):
            a = 2 * math.pi * k / 40
            p0 = (160 + 132 * math.sin(a), 160 + 132 * math.cos(a))
            p1 = (160 + 138 * math.sin(a), 160 + 138 * math.cos(a))
            d.line((p0, p1), fill='#fff0b5', width=3)
        d.text((160, 154), label, anchor='mm', font=font, fill='#ffe9a6', stroke_fill='#774a19', stroke_width=2)
        d.text((160, 72), top, anchor='mm', font=small, fill='#5c3716')
        # Deliberately asymmetric symbols expose accidental mirrored artwork.
        d.polygon(((76, 224), (76, 205), (104, 215)), fill='#fff1be')
        d.ellipse((226, 206, 242, 222), fill='#6d4218')
        path = dest / f'demo-{side}.png'
        im.save(path)
        paths[side] = path
    edge = Image.new('RGBA', (512, 32), '#b67c29')
    d = ImageDraw.Draw(edge)
    for x in range(0, 512, 12):
        d.rectangle((x, 2, x + 3, 29), fill='#ffe3a1')
        d.line((x + 4, 2, x + 4, 29), fill='#724519', width=2)
    d.line((0, 0, 511, 0), fill='#ffedb1', width=2)
    d.line((0, 31, 511, 31), fill='#654018', width=2)
    paths['edge'] = dest / 'demo-edge.png'
    edge.save(paths['edge'])
    return paths


if __name__ == '__main__':
    for key, value in make_demo_assets().items():
        print(f'{key}: {value}')
