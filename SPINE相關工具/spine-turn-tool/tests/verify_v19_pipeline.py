"""Once-frozen six-case coin sweep native/runtime and editable delivery gate."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from spine_turn_core import (TurnOptions,prepare_images,resolve_options,build_package,
                             motion_key_progress)
from spine_turn_formats import SPINE_TARGETS,animation_key_times
from spine_native import convert_project,export_binary,_run
from spine_turn_project import save_project,load_project
from spine_turn_sequence import export_sequence
from verify_v17_pipeline import validate_diamond
from verify_v16_pipeline import sample
from verify_v14_pipeline import contact_sheet,preview_gif

QA=ROOT/'qa/v1.9'
APP=Path(os.environ.get('SPINE_TURN_FROZEN_APP',str(ROOT)))
ASSETS=APP/'assets'
EXAMPLE=ROOT/'examples/coin-shine-v1.9'


def hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in APP.glob('*.py')}


def run_case(label,options,front,back=None,edge=None,*,families=None,destination=None,
             qa_dir=None,release='1.9',project_name='coin.spturn',validator=validate_diamond,
             extra_progresses=(),original_artwork=True,delivery_kind='coin-shine'):
    families=dict(SPINE_TARGETS) if families is None else {family:SPINE_TARGETS[family] for family in families}
    folder=(qa_dir or QA)/'native-targets'/label
    input_hashes={str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest()
                  for path in (front,back,edge) if path is not None}
    prepared=prepare_images(front,back,edge,options)
    options=resolve_options(prepared,options)
    canonical_options=replace(options,spine_version=SPINE_TARGETS['4.0'])
    canonical=build_package(front,back,edge,folder/'canonical',canonical_options)
    reference=Path(canonical['json_path'])
    document=json.loads(reference.read_text(encoding='utf-8'))
    times=sorted(set(animation_key_times(document)))
    progresses=set(i/180 for i in range(181)) | set(motion_key_progress(options)) | set(extra_progresses)
    for name,animation in document['animations'].items():
        duration=options.duration if name=='rotate_loop' else options.duration/2
        for time in times:
            if time<=duration:
                progresses.add(time/duration)
        for a,b in zip(times,times[1:]):
            if b<=duration:
                progresses.add((a+b)/(2*duration))
    progresses=sorted(progresses)
    checks={}
    pose_cache={}
    for family,exact in families.items():
        target=replace(options,spine_version=exact)
        authored_folder=folder/f'spine-{family}'
        package=build_package(front,back,edge,authored_folder,target)
        authored=Path(package['json_path'])
        selected_fps=json.loads(authored.read_text(encoding='utf-8'))['skeleton']['fps']
        native=convert_project(authored,authored_folder/f'{options.name}.spine',target_version=exact,overwrite=True)
        assert native['ok'],native
        exported=export_binary(native['project_path'],authored_folder/'native-binary',target_version=exact)
        assert exported['ok'],exported
        binary=Path(exported['binary_paths'][0])
        for extension in ('.atlas','.png'):
            shutil.copy2(authored.with_suffix(extension),binary.with_suffix(extension))
        family_checks={}
        for kind,skeleton in [('authored-json',authored),('native-binary',binary)]:
            sampled=sample(skeleton,folder/f'{family}-{kind}-poses.json',family,progresses)
            assert sampled['data_version']==exact
            if family=='3.8' and kind=='native-binary':
                assert sampled['authoring_fps']==selected_fps
            try:
                family_checks[kind]=validator(reference,sampled,canonical_options,prepared,
                    pose_cache,allow_edge=True)
            except AssertionError as failure:
                raise AssertionError((label,family,kind,str(failure))) from failure
        manifest_path=authored_folder/'manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update(native_project_created=True,native_project=f'{options.name}.spine',
            native_roundtrip_verified=True,native_runtime_verification_format='binary',
            native_editor_version=exact,official_runtime_verified=True,official_runtime_family=family,
            input_back_image_supplied=back is not None,back_reuses_front=back is None,original_artwork=original_artwork)
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        if destination:
            target_folder=destination/f'spine-{family}'
            target_folder.mkdir(parents=True,exist_ok=True)
            for path in authored_folder.iterdir():
                if path.name=='native-binary':continue
                if path.is_dir():shutil.copytree(path,target_folder/path.name,dirs_exist_ok=True)
                else:shutil.copy2(path,target_folder/path.name)
        checks[family]=dict(revision=exact,authoring_fps=selected_fps,samples_per_action=len(progresses),checks=family_checks)
        print(json.dumps(dict(case=label,target=exact,ok=True)),flush=True)
    if destination:
        selected=replace(options,spine_version=SPINE_TARGETS['4.0'])
        paths=dict(front=str(front),back=str(back) if back else None,edge=str(edge) if edge else None)
        state=dict(animation='rotate_loop',background='checker',preview_zoom=100,
            show_ground=False,native_export=True,progress=0,playing=original_artwork)
        save_project(destination/project_name,paths,selected,state)
        loaded=load_project(destination/project_name)
        try:
            assert asdict(loaded.options)==asdict(selected) and loaded.ui_state==state
            for role,path in paths.items():
                if path is None:assert loaded.paths[role] is None
                else:assert Path(loaded.paths[role]).read_bytes()==Path(path).read_bytes()
            reopened=build_package(loaded.paths['front'],loaded.paths['back'],loaded.paths['edge'],
                folder/'project-reopened',loaded.options)
            assert json.loads(Path(reopened['json_path']).read_text(encoding='utf-8'))==document
        finally:loaded.close()
        stage=Path(tempfile.mkdtemp(prefix='sequence-',dir=folder))
        sequence=export_sequence(prepared,selected,stage,fps=30,size=(512,512))
        shutil.copytree(stage,destination/'png-sequence',dirs_exist_ok=True)
        data=json.loads(Path(sequence['manifest_path']).read_text(encoding='utf-8'))
        assert data['status']=='complete' and data['frame_count']==60
        contact_sheet(prepared,selected,data['camera'],destination/'preview-contact-sheet.png')
        preview_gif(destination/'png-sequence',destination/'preview.gif')
        (destination/'delivery.json').write_text(json.dumps(dict(format=f'{delivery_kind}-delivery-v{release}',
            targets=families,tool_project=project_name,tool_project_selected_target=selected.spine_version,
            tool_project_reload_geometry_identical=True,original_artwork=original_artwork,
            source_roles={key:path is not None for key,path in paths.items()},checks=checks),indent=2),encoding='utf-8')
        version_note=('三個版本的原生專案分別位於 `spine-3.8`、`spine-4.0`、`spine-4.2`；'
            '使用對應的 Spine 3.8.99、4.0.56、4.2.43 開啟。' if len(families)==3 else
            '此複合動作的原生專案位於 `spine-4.0`，以 Spine 4.0.56 開啟。')
        source_note=('此編輯檔嵌入本工具原創的正面、背面與側邊材質。' if back else
            '此編輯檔嵌入本工具原創的正面圖片；背面沿用正面。')
        (destination/'README_zh-TW.md').write_text(
            f'# 硬幣旋轉與掃光範例\n\n在工具開啟 `{project_name}`，可調整旋轉、彈跳與「硬幣掃光」設定。'
            +source_note+f'掃光在整圈的 {options.coin_shine_start*options.duration:g}–'
            f'{options.coin_shine_end*options.duration:g} 秒之間通過 {options.coin_shine_repeat} 次，'
            '只覆蓋正反面，不照亮側邊。\n\n'+version_note+'`preview.gif` 與 `png-sequence` 的 60 張透明 PNG '
            '採用相同設定，固定 512×512 畫布。\n',encoding='utf-8')
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in input_hashes.items())
    return dict(checks=checks,editable_project_reload_verified=bool(destination),source_images_unchanged=True)


def regressions():
    proof=json.loads((QA/'baseline-provenance.json').read_text(encoding='utf-8'))
    result={}
    for label,case in proof['cases'].items():
        front=ASSETS/('demo-front.png' if label=='ellipse' else 'demo-octagon.png')
        back=ASSETS/'demo-back.png' if label=='ellipse' else None
        edge=None if label=='ridge' else ASSETS/'demo-edge.png'
        options=TurnOptions(**case['options'])
        baseline=QA/f'baseline-v1.8-{label}'
        package=build_package(front,back,edge,QA/'off-regressions'/label,options)
        current=Path(package['json_path'])
        assert json.loads(current.read_text(encoding='utf-8'))==json.loads((baseline/current.name).read_text(encoding='utf-8'))
        sampled=sample(current,QA/'off-regressions'/f'{label}-poses.json','4.0',[i/60 for i in range(61)])
        prior=json.loads((QA/f'baseline-v1.8-{label}-poses.json').read_text(encoding='utf-8'))
        assert sampled==prior,(label,'official runtime changed while shine disabled')
        result[label]=dict(full_skeleton_exact=True,official_runtime_three_actions_exact=True)
    return result


def main():
    QA.mkdir(exist_ok=True)
    before=hashes()
    unit=json.loads((QA/'unit-tests.json').read_text(encoding='utf-8'))
    assert unit.get('ok',unit.get('success'))
    assert unit.get('source_sha256',unit.get('source_hashes_before'))==before
    assert unit.get('source_hashes_after',before)==before
    base=TurnOptions(name='coin_shine_v19',coin_shine_enabled=True,
        coin_shine_start=0,coin_shine_end=.25,coin_shine_repeat=1)
    cases={}
    cases['ellipse-y']=run_case('ellipse-y',base,ASSETS/'demo-front.png',ASSETS/'demo-back.png',
        ASSETS/'demo-edge.png',destination=EXAMPLE)
    polygon=replace(base,name='polygon_shine_v19',shape='polygon',coin_shine_angle=32,
        coin_shine_repeat=2,coin_shine_end=.8,coin_shine_width=.35,coin_shine_strength=.65)
    cases['polygon-y']=run_case('polygon-y',polygon,ASSETS/'demo-octagon.png',edge=ASSETS/'demo-edge.png',families=('4.0',))
    bevel=replace(polygon,name='bevel_x_yz_shine_v19',axis='x',thickness=32,bevel_width=.07,
        bounce_enabled=True,bounce_height=80,bounce_start=.3,bounce_apex=.5,bounce_land=.7,bounce_end=.85,
        z_bounce_enabled=True,z_bounce_depth=-140,z_offset=20,peak_z_scale=1.25,
        z_bounce_start=.1,z_bounce_apex=.2,z_bounce_end=.45)
    cases['bevel-x-yz']=run_case('bevel-x-yz',bevel,ASSETS/'demo-octagon.png',edge=ASSETS/'demo-edge.png',
        families=('4.0',),destination=EXAMPLE/'bevel-x-yz')
    ridge=replace(polygon,name='ridge_shine_v19',side_mode='ridge',thickness=32,
        coin_shine_repeat=3,coin_shine_width=.5,coin_shine_angle=-40)
    cases['ridge-y']=run_case('ridge-y',ridge,ASSETS/'demo-octagon.png',families=('4.0',))
    with (EXAMPLE/'README_zh-TW.md').open('a',encoding='utf-8') as readme:
        readme.write('\n`bevel-x-yz/` 另附原創多邊形斜面的 X 軸旋轉與獨立 Y/Z 彈跳；其掃光參數為 0–80%、2 次、寬度35%、角度32°，附4.0.56原生專案與相同設定的透明序列。\n')
    old=regressions()
    assert hashes()==before,'Application source changed during the native matrix.'
    restored=_run([r'C:\Program Files\Spine\Spine.com','--update','4.0.56','--version'],60)
    assert restored['ok']
    report=dict(ok=True,native_cases=6,targets=dict(SPINE_TARGETS),cases=cases,legacy_regression=old,
        source_sha256=before,application_source=str(APP),
        max_world_error=max(check[field] for case in cases.values() for family in case['checks'].values()
            for check in family['checks'].values() for field in ('world_vertex_error','preview_world_vertex_error')),
        max_parent_weight_error=max(check['coin_parent_weight_error'] for case in cases.values()
            for family in case['checks'].values() for check in family['checks'].values()),
        restored_launcher_version=restored.get('editor_version'))
    (QA/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(ok=True,native_cases=6,report=str(QA/'verification.json'))),flush=True)


if __name__=='__main__':main()
