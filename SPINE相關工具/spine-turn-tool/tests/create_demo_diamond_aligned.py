"""Original flat-front Diamond art, calibrated to the v1.8 demo defaults."""
from pathlib import Path
import hashlib
import json
import re
import sys
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spine_turn_diamond import diamond_pose

SIZE,SCALE=384,4
options=dict(model='diamond',axis='y',diamond_facets=8,diamond_center_x=0,
    diamond_table_y=.35,diamond_waist_y=.10,diamond_tip_y=-.48,
    diamond_table_width=.5,diamond_waist_width=.96,diamond_girdle_height=.015,
    diamond_view_tilt=24,diamond_ring_phase=22.5,diamond_table_depth=0,
    diamond_waist_depth=0,z_scale=1,diamond_shading=0)
old=ROOT/'assets/demo-diamond.png'
old_hash=hashlib.sha256(old.read_bytes()).hexdigest()
surfaces=diamond_pose(0,options,SIZE,SIZE)
table=next(mesh for mesh in surfaces if mesh['zone']=='table')
assert abs(table['model_vertices'][0])>1,'v1.8 phase geometry has not landed yet.'
points=list(zip(table['vertices'][::2],table['vertices'][1::2]))[:table['hull']]
top=max(y for x,y in points)
assert sum(abs(y-top)<1e-6 for x,y in points)==2,'The demo needs a flat top/back edge.'
image=Image.new('RGBA',(SIZE*SCALE,SIZE*SCALE))
draw=ImageDraw.Draw(image)
crown=['#83ecff','#c8faff','#defeff','#a1edff','#59c4ed','#4fb5e5','#319ad1','#4abbe9']
pavilion=['#1985c9','#32a8e0','#8beaff','#c0f7ff','#65d1f6','#3ba9e2','#1f7cbd','#1266ad']
table_colors=['#f3feff','#e9fdff','#d1f8ff','#b9eeff','#abe5fb','#c9f3ff','#e0fcff','#edffff']
for mesh in surfaces:
    if not mesh['visible']:
        continue
    projected=[(round((x+SIZE/2)*SCALE),round((SIZE/2-y)*SCALE))
        for x,y in zip(mesh['vertices'][::2],mesh['vertices'][1::2])]
    if mesh['zone']=='table':
        for i in range(len(mesh['triangles'])//3):
            draw.polygon([projected[index] for index in mesh['triangles'][i*3:i*3+3]],fill=table_colors[i%8])
    else:
        sector=int(re.search(r'_(\d+)(?:_|$)',mesh['name']).group(1))
        color='#adf5ff' if mesh['zone']=='girdle' else (crown if mesh['zone']=='crown' else pavilion)[sector%8]
        draw.polygon(projected,fill=color)
image=image.resize((SIZE,SIZE),Image.Resampling.LANCZOS)
target=ROOT/'assets/demo-diamond-aligned.png'
image.save(target)
assert hashlib.sha256(old.read_bytes()).hexdigest()==old_hash
proof=ROOT/'qa/v1.8/generic-aligned-asset.json'
proof.parent.mkdir(parents=True,exist_ok=True)
proof.write_text(json.dumps(dict(original_geometric_art=True,source_asset=str(target),
    source_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),options=options,
    trim_transparent=False,old_asset_unchanged=True,old_asset_sha256=old_hash),indent=2),encoding='utf-8')
print(json.dumps(dict(asset=str(target),size=image.size,old_asset_unchanged=True)))
