"""Frozen irregular-contour native/official-runtime matrix, including painter order."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from spine_turn_core import TurnOptions,build_package,ordered_surfaces
from spine_turn_formats import SPINE_TARGETS
from spine_native import _run
from verify_v17_pipeline import validate_diamond,area
from verify_v19_pipeline import run_case
from native_data_preview import native_delivery_preview

QA=ROOT/'qa/v1.10'
APP=Path(os.environ.get('SPINE_TURN_FROZEN_APP',str(ROOT)))
ASSETS=APP/'assets'
EXAMPLE=ROOT/'examples/irregular-v1.10'
PRIVATE=ROOT/'output/user-irregular-v1.10'
SOURCE=Path(os.environ.get('SPINE_TURN_PRIVATE_IMAGE',
    r'D:\SLOT工作區\805_彌勒佛\出圖\Symbols\LuckyBuddha_MG_SuperScatter.png'))
PRIVATE_SHA='fdeb461af933d0fe3d7adf3e16c9d920bffb564f558c306803041f50abf0cb22'
QUARTERS=tuple(sorted({max(0.,min(1.,center+delta)) for center in (0,.25,.5,.75,1)
                      for delta in (-1e-5,-1e-7,0,1e-7,1e-5)} | {i/8 for i in range(9)}))


def hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in APP.glob('*.py')}


def validate_irregular(reference,sampled,options,prepared,pose_cache=None,*,allow_edge=True):
    cache={} if pose_cache is None else pose_cache
    result=validate_diamond(reference,sampled,options,prepared,cache,allow_edge=allow_edge)
    document=json.loads(reference.read_text(encoding='utf-8'))
    attachments=document['skins'][0]['attachments']
    count=near=triangle_samples=0
    for name,action in sampled['animations'].items():
        for pose in action['poses']:
            for slot,mesh in pose['geometry'].items():
                triangles=mesh.get('triangles',[])
                attachment=attachments[slot][mesh['name']]
                source=attachment['triangles']
                assert len(mesh['vertices'])==len(attachment['vertices']),(
                    name,pose['progress'],slot,'native vertex count changed')
                assert len(mesh['uvs'])==len(attachment['uvs']),(
                    name,pose['progress'],slot,'native UV count changed')
                assert triangles and len(triangles)%3==0,(name,pose['progress'],slot,'empty/invalid native triangles')
                assert all(isinstance(index,int) and 0<=index<len(mesh['vertices'])//2 for index in triangles),(
                    name,pose['progress'],slot,'native triangle vertex index outside mesh')
                assert len(triangles)==len(source),(name,pose['progress'],slot,'triangle count changed')
                if triangles!=source:
                    normalized=lambda values:sorted(tuple(sorted(values[i:i+3])) for i in range(0,len(values),3))
                    assert normalized(triangles)==normalized(source),(name,pose['progress'],slot,'native triangle index sets changed')
                triangle_samples+=1
            motion,preview=cache[(name,pose['progress'])]
            expected=ordered_surfaces([dict(mesh,name=slot) for slot,mesh in preview.items()])
            visible={mesh['name'] for mesh in expected if mesh['visible']}
            determinant=abs(motion['scale_x']*motion['scale_y'])
            keep={slot for slot,mesh in pose['geometry'].items() if slot in visible
                  and area(mesh)>.02 and area(preview[slot])*determinant>.02}
            actual_order=[slot for slot in pose['geometry'] if slot in keep]
            expected_order=[mesh['name'] for mesh in expected if mesh['name'] in keep]
            assert actual_order==expected_order,(name,pose['progress'],'native painter order differs',
                                                  actual_order,expected_order)
            count+=1
            near+=any(abs(pose['progress']-quarter)<=1.1e-5 for quarter in (0,.25,.5,.75,1))
    assert count>100 and near>20
    return dict(result,draw_order_poses=count,quarter_epsilon_draw_order_poses=near,
                renderable_triangle_mesh_samples=triangle_samples,authored_triangle_index_sets_exact=True,
                authored_vertex_and_uv_counts_exact=True,
                draw_order_matches_after_only_zero_area_switch_exclusion=True)


def synthetic_holes_and_deep_c():
    folder=QA/'fixtures'
    folder.mkdir(parents=True,exist_ok=True)
    scale=4
    image=Image.new('RGBA',(192*scale,192*scale),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    box=lambda values:tuple(round(value*scale) for value in values)
    draw.rounded_rectangle(box((12,12,180,180)),radius=12*scale,fill=(32,153,183,255))
    draw.rectangle(box((70,58,193,134)),fill=(0,0,0,0))
    draw.ellipse(box((30,28,60,52)),fill=(0,0,0,0))
    draw.rectangle(box((20,78,45,112)),fill=(72,222,184,255))
    image=image.resize((192,192),Image.Resampling.LANCZOS)
    path=folder/'deep-c-with-alpha-hole.png'
    image.save(path)
    assert image.getpixel((45,40))[3]==0 and image.getpixel((140,96))[3]==0
    assert image.getpixel((30,96))[3]==255
    return path


def regressions():
    checks={}
    for label in ('ellipse-y','polygon-y','bevel-x-yz','ridge-y'):
        old=ROOT/'qa/v1.9/native-targets'/label/'canonical'
        manifest=json.loads((old/'manifest.json').read_text(encoding='utf-8'))
        options=TurnOptions(**manifest['options'])
        result=build_package(old/'images/front.png',old/'images/back.png',old/'images/edge.png',
                             QA/'legacy-regression'/label,options)
        old_json=old/f'{options.name}.json'
        assert json.loads(Path(result['json_path']).read_text(encoding='utf-8'))==json.loads(old_json.read_text(encoding='utf-8'))
        checks[label]=dict(full_skeleton_exact_v19=True,new_native_launches=0)
    return checks


def delivery_readme(folder,project_name,*,private=False,stress=False):
    if private:
        text=('此資料夾僅包含使用者提供的原圖及其製作結果，不放入工具公開套件。'
              '中央綠色方塊在原圖是不透明顏色，仍保留為有色區域；沒有自動挖孔。'
              '沒有提供背面，依Y軸翻轉方向鏡射正面作為背面，不補畫細節。')
    else:
        text=('此星花徽章圖片是本工具原創範例，透明外框的凹口保留實際厚度側邊。'
              '正面與背面均有獨立原始透明PNG。')
    versions=('此複合動作使用 Spine4.0.56，原生檔位於 `spine-4.0/`。' if stress else
              '三版本原生專案位於 `spine-3.8/`、`spine-4.0/`、`spine-4.2/`，分別用3.8.99、4.0.56、4.2.43開啟。')
    (folder/'README_zh-TW.md').write_text('# 不規則透明輪廓翻轉\n\n'
        f'在工具開啟 `{project_name}` 可繼續調整；編輯檔保存原圖、輪廓門檻、誤差及全部動畫設定。'
        +text+'\n\n'+versions+'\n\n`preview.gif`、`preview-contact-sheet.png` 與 `png-sequence/` '
        '的60張512×512透明PNG，使用相同設定與整段固定取景。\n',encoding='utf-8')
    with (folder/'README_zh-TW.md').open('a',encoding='utf-8') as readme:
        readme.write('\n交付預覽以 Spine4.0.56 原生專案重新匯出的 Binary，由官方runtime計算實際網格、骨骼與繪製順序，再用共用CPU繪圖器產生；不是Spine GPU截圖。\n')


def main():
    QA.mkdir(exist_ok=True)
    before=hashes()
    unit=json.loads((QA/'unit-tests.json').read_text(encoding='utf-8'))
    assert unit.get('ok',unit.get('success'))
    assert unit.get('source_sha256',unit.get('source_hashes_before'))==before
    assert unit.get('source_hashes_after',before)==before
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==PRIVATE_SHA
    with Image.open(SOURCE) as image:
        assert image.size==(270,240) and image.convert('RGBA').getpixel((135,120))==(57,240,29,255)
    options=TurnOptions(name='irregular_v110',shape='irregular',outline_alpha_threshold=16,
                        outline_tolerance=1,coin_shine_enabled=False)
    shared=dict(qa_dir=QA,release='1.10',validator=validate_irregular,
                extra_progresses=QUARTERS,delivery_kind='irregular')
    cases={}
    cases['public-irregular-y']=run_case('public-irregular-y',options,ASSETS/'demo-irregular-front.png',
        ASSETS/'demo-irregular-back.png',ASSETS/'demo-edge.png',destination=EXAMPLE,
        project_name='irregular.spturn',**shared)
    cases['public-irregular-y']['native_data_preview']=native_delivery_preview(
        QA/'native-targets/public-irregular-y',EXAMPLE,options)
    delivery_readme(EXAMPLE,'irregular.spturn')
    fixture=synthetic_holes_and_deep_c()
    c_options=replace(options,name='deep_c_hole_x_v110',axis='x',coin_shine_enabled=True,
                      coin_shine_width=.4,coin_shine_end=.8,coin_shine_repeat=2)
    cases['deep-c-hole-x']=run_case('deep-c-hole-x',c_options,fixture,
        destination=QA/'deep-c-hole-x-preview',project_name='holes.spturn',**shared)
    cases['deep-c-hole-x']['native_data_preview']=native_delivery_preview(
        QA/'native-targets/deep-c-hole-x',QA/'deep-c-hole-x-preview',c_options)
    private_options=replace(options,name='user_irregular_v110')
    cases['user-irregular-y']=run_case('user-irregular-y',private_options,SOURCE,
        destination=PRIVATE,project_name='symbol.spturn',original_artwork=False,**shared)
    cases['user-irregular-y']['native_data_preview']=native_delivery_preview(
        QA/'native-targets/user-irregular-y',PRIVATE,private_options)
    delivery_readme(PRIVATE,'symbol.spturn',private=True)
    stress=replace(options,name='irregular_x_yz_shine_v110',axis='x',coin_shine_enabled=True,
        coin_shine_strength=.65,coin_shine_width=.35,coin_shine_angle=32,
        coin_shine_repeat=2,coin_shine_end=.8,bounce_enabled=True,bounce_height=80,
        bounce_start=.3,bounce_apex=.5,bounce_land=.7,bounce_end=.85,
        z_bounce_enabled=True,z_bounce_depth=-140,z_offset=20,peak_z_scale=1.25,
        z_bounce_start=.1,z_bounce_apex=.2,z_bounce_end=.45)
    cases['public-x-yz-shine']=run_case('public-x-yz-shine',stress,ASSETS/'demo-irregular-front.png',
        ASSETS/'demo-irregular-back.png',ASSETS/'demo-edge.png',families=('4.0',),
        destination=EXAMPLE/'motion-shine',project_name='motion.spturn',**shared)
    cases['public-x-yz-shine']['native_data_preview']=native_delivery_preview(
        QA/'native-targets/public-x-yz-shine',EXAMPLE/'motion-shine',stress)
    delivery_readme(EXAMPLE/'motion-shine','motion.spturn',stress=True)
    old=regressions()
    assert hashes()==before,'Frozen application source changed during the matrix.'
    restored=_run([r'C:\Program Files\Spine\Spine.com','--update','4.0.56','--version'],60)
    assert restored['ok']
    report=dict(ok=True,native_cases=10,targets=dict(SPINE_TARGETS),cases=cases,
        legacy_regression=old,source_sha256=before,application_source=str(APP),
        private_input_sha256=PRIVATE_SHA,private_center_opaque_green_preserved=True,
        max_world_error=max(check[field] for case in cases.values() for family in case['checks'].values()
            for check in family['checks'].values() for field in ('world_vertex_error','preview_world_vertex_error')),
        restored_launcher_version=restored.get('editor_version'))
    (QA/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    for p in PRIVATE.rglob('*'):
        assert not p.name.startswith('.spine-import-')
    archive=Path(str(PRIVATE)+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(PRIVATE.rglob('*')):
            if path.is_file():z.write(path,path.relative_to(PRIVATE.parent))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    (QA/'private-delivery.json').write_text(json.dumps(dict(archive=str(archive),
        bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest()),indent=2),encoding='utf-8')
    print(json.dumps(dict(ok=True,native_cases=10,report=str(QA/'verification.json'))),flush=True)


if __name__=='__main__':main()
