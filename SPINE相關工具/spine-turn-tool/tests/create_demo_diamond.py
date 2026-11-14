"""Create an original geometric gemstone fixture, with no external artwork."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCALE = 4
SIZE = 384
sys.path.insert(0, str(ROOT))
from spine_turn_diamond import diamond_pose


def main():
    image = Image.new('RGBA', (SIZE * SCALE, SIZE * SCALE))
    draw = ImageDraw.Draw(image)
    surfaces = diamond_pose(0, dict(axis='y', diamond_view_tilt=12), SIZE, SIZE)
    crown = ['#81eaff', '#c1f8ff', '#d4fdff', '#96eaff',
             '#51bce9', '#44abdf', '#2c91ca', '#3bb1e4']
    pavilion = ['#147bc1', '#2c9cdb', '#81e5ff', '#bbf5ff',
                '#57c8f4', '#339fdd', '#176fb3', '#0d58a1']
    table_colors = ['#f0feff', '#e3fcff', '#cbf6ff', '#b1eaff',
                    '#a1dff8', '#c1efff', '#d8faff', '#e8ffff']
    for surface in surfaces:
        if not surface['visible']:
            continue
        points = [(round((x + SIZE/2) * SCALE), round((SIZE/2 - y) * SCALE))
                  for x,y in zip(surface['vertices'][::2],surface['vertices'][1::2])]
        zone = surface['zone']
        if zone == 'table':
            for i in range(8):
                triangle = [points[index] for index in surface['triangles'][i*3:i*3+3]]
                draw.polygon(triangle,fill=table_colors[i])
        else:
            index = int(surface['name'].rsplit('_',1)[1])
            color = '#a5f2ff' if zone=='girdle' else (crown if zone=='crown' else pavilion)[index]
            draw.polygon(points,fill=color)
    image = image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    destination = ROOT / 'assets/demo-diamond.png'
    image.save(destination)
    assert image.mode == 'RGBA' and image.getpixel((0, 0))[3] == 0
    print(destination)


if __name__ == '__main__':
    main()
