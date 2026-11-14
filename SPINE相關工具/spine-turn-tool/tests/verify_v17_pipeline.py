"""Independent Diamond authoring/native/runtime and editable-project evidence."""
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/v1.7'
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, build_package, prepare_images, resolve_options,
    motion_key_progress, motion_at, animation_pose_at)
from spine_turn_formats import SPINE_TARGETS, convert_skeleton, animation_key_times, spine_family
from spine_native import convert_project, export_binary, _run
from spine_turn_project import save_project, load_project
from spine_turn_sequence import export_sequence
from verify_v11_pipeline import deform_at
from verify_v14_pipeline import contact_sheet, preview_gif, compare_runtime
from verify_v16_pipeline import sample


def area(mesh):
    points = list(zip(mesh['vertices'][::2], mesh['vertices'][1::2]))
    total = 0.
    for index in range(0, len(mesh['triangles']), 3):
        a, b, c = [points[mesh['triangles'][index + j]] for j in range(3)]
        total += abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2
    return total


def validate_diamond(reference, sampled, options, prepared, pose_cache=None, *, allow_edge=False):
    document = json.loads(reference.read_text(encoding='utf-8'))
    attachments = document['skins'][0]['attachments']
    expected_blends = {slot['name']: {'normal':0, 'additive':1, 'multiply':2, 'screen':3}
        [slot.get('blend', 'normal')] for slot in document['slots']}
    maxima = dict.fromkeys(('bone_motion_error', 'world_vertex_error', 'preview_world_vertex_error',
        'tint_error', 'uv_error', 'root_drift', 'loop_world_vertex_seam', 'loop_color_seam',
        'visibility_mismatch_area','shine_parent_spill_pixels','coin_parent_weight_error'), 0.)
    count = shell_count = fx_count = 0
    locations = {}
    pose_cache = {} if pose_cache is None else pose_cache
    for name, action in sampled['animations'].items():
        timeline = document['animations'][name]
        for pose in action['poses']:
            progress = pose['progress']
            cache_key = (name,progress)
            if cache_key not in pose_cache:
                motion = motion_at(progress, options, prepared['height'])
                preview = {mesh['name']:{key:mesh[key] for key in ('vertices','tint','visible','kind','triangles',
                    'source_face','cell_weights','draw_order') if key in mesh}
                    for mesh in animation_pose_at(progress, options,prepared['width'],prepared['height'],name)}
                pose_cache[cache_key] = motion,preview
            expected_motion,preview = pose_cache[cache_key]
            active = pose['bones'].get('depth', pose['bones']['turn'])
            actual = dict(x=active['world_x'], y=active['world_y'], scale_x=active['a'], scale_y=active['d'])
            for key in actual:
                maxima['bone_motion_error'] = max(maxima['bone_motion_error'], abs(actual[key]-expected_motion[key]))
            root = pose['bones']['root']
            maxima['root_drift'] = max(maxima['root_drift'], abs(root['world_x']), abs(root['world_y']))
            visible = {slot for slot, mesh in preview.items() if mesh['visible']}
            for slot in visible.symmetric_difference(pose['geometry']):
                mesh = preview[slot]
                if mesh['tint'][3] > .001:
                    maxima['visibility_mismatch_area'] = max(maxima['visibility_mismatch_area'], area(mesh))
            for slot, mesh in pose['geometry'].items():
                expected = preview[slot]
                source = attachments[slot][mesh['name']]
                assert mesh['path'] == source['path']
                assert allow_edge or mesh['path'] != 'edge'
                assert mesh['blend_mode'] == expected_blends[slot]
                delta = deform_at(timeline['deform']['default'][slot][mesh['name']],
                    len(source['vertices']), progress * action['duration'])
                authored_local = [v+d for v,d in zip(source['vertices'], delta)]
                for key, local in [('world_vertex_error', authored_local),
                                   ('preview_world_vertex_error', expected['vertices'])]:
                    world = [value * expected_motion['scale_x' if index % 2 == 0 else 'scale_y'] +
                        expected_motion['x' if index % 2 == 0 else 'y'] for index,value in enumerate(local)]
                    error = max(abs(a-b) for a,b in zip(world, mesh['vertices']))
                    if error > maxima[key]:
                        maxima[key] = error
                        locations[key] = dict(animation=name,progress=progress,slot=slot,alpha=mesh['color'][3])
                maxima['tint_error'] = max(maxima['tint_error'], max(abs(a-b) for a,b in zip(expected['tint'], mesh['color'])))
                maxima['uv_error'] = max(maxima['uv_error'], max(abs(a-b) for a,b in zip(source['uvs'], mesh['uvs'])))
                if expected['kind'] == 'diamond_face':
                    assert abs(mesh['color'][3]-1) < .000001, 'Diamond body became translucent.'
                assert 0 <= mesh['color'][3] <= 1
                if expected['kind'] in ('diamond_fx','coin_fx'):
                    fx_count += 1
                else:
                    shell_count += 1
                if expected['kind'] == 'coin_fx':
                    parent_name = expected['source_face']
                    parent = pose['geometry'].get(parent_name)
                    if parent is None:
                        assert mesh['color'][3] < .001
                    else:
                        parent_points = list(zip(parent['vertices'][::2],parent['vertices'][1::2]))
                        for vertex, weights in enumerate(expected['cell_weights']):
                            assert abs(sum(weight for _,weight in weights)-1) < 1e-8
                            assert min(weight for _,weight in weights) >= -1e-12
                            for coordinate in (0,1):
                                inherited = sum(parent_points[i][coordinate]*weight for i,weight in weights)
                                maxima['coin_parent_weight_error'] = max(maxima['coin_parent_weight_error'],
                                    abs(mesh['vertices'][vertex*2+coordinate]-inherited))
                elif '_shine_' in slot:
                    parent_name=slot.rsplit('_shine_',1)[0]
                    parent=pose['geometry'].get(parent_name)
                    if parent is None:
                        assert mesh['color'][3]<.001
                    elif mesh['vertices']==parent['vertices'] and mesh['triangles']==parent['triangles']:
                        # A cut patch and its light use exactly the same mesh.
                        # This is stronger than half-plane tests, whose edge
                        # normals are unstable on tiny collinear subdivisions.
                        pass
                    else:
                        hull=attachments[parent_name][parent['name']]['hull']
                        points=list(zip(parent['vertices'][::2],parent['vertices'][1::2]))[:hull]
                        winding=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
                        if abs(winding)>.04:
                            sign=1 if winding>0 else -1
                            for x,y in zip(mesh['vertices'][::2],mesh['vertices'][1::2]):
                                for a,b in zip(points,points[1:]+points[:1]):
                                    dx,dy=b[0]-a[0],b[1]-a[1]
                                    length=math.hypot(dx,dy)
                                    if length>1e-8:
                                        maxima['shine_parent_spill_pixels']=max(maxima['shine_parent_spill_pixels'],
                                            -sign*(dx*(y-a[1])-dy*(x-a[0]))/length)
                count += 1
        if name == 'rotate_loop':
            first, last = action['poses'][0]['geometry'], action['poses'][-1]['geometry']
            for slot in set(first).intersection(last):
                maxima['loop_world_vertex_seam'] = max(maxima['loop_world_vertex_seam'],
                    max(abs(a-b) for a,b in zip(first[slot]['vertices'], last[slot]['vertices'])))
                maxima['loop_color_seam'] = max(maxima['loop_color_seam'],
                    max(abs(a-b) for a,b in zip(first[slot]['color'], last[slot]['color'])))
            for slot in set(first).symmetric_difference(last):
                assert max(first.get(slot, last.get(slot))['color'][3], 0) < .001
    for field in ('bone_motion_error', 'world_vertex_error', 'preview_world_vertex_error'):
        assert maxima[field] < .02, (field, maxima[field], locations.get(field))
    assert maxima['tint_error'] < .001
    assert maxima['uv_error'] < .000001
    assert maxima['root_drift'] < .0001
    assert maxima['loop_world_vertex_seam'] < .002
    assert maxima['loop_color_seam'] < .001
    assert maxima['visibility_mismatch_area'] < .02
    assert maxima['shine_parent_spill_pixels'] < .02, maxima['shine_parent_spill_pixels']
    assert maxima['coin_parent_weight_error'] < .02, maxima['coin_parent_weight_error']
    return {**maxima, 'mesh_samples': count, 'shell_mesh_samples': shell_count, 'fx_mesh_samples': fx_count}


def run_case(label, options, destination=None, project_name='diamond.spturn', *,
             front_path=None, qa_dir=None, release='1.7', original_artwork=True,
             selected_version=None):
    folder = (qa_dir or QA) / 'native-targets' / label
    front = Path(front_path) if front_path else ROOT / 'assets/demo-diamond.png'
    source_hash = hashlib.sha256(front.read_bytes()).hexdigest()
    prepared = prepare_images(front, None, None, options)
    options = resolve_options(prepared, options)
    canonical_options = replace(options, spine_version=SPINE_TARGETS['4.0'])
    canonical = build_package(front, None, None, folder / 'canonical', canonical_options)
    reference = Path(canonical['json_path'])
    source_document = json.loads(reference.read_text(encoding='utf-8'))
    events = sorted(set(animation_key_times(source_document)))
    progresses = set(i / 240 for i in range(241)) | set(motion_key_progress(options))
    for animation in source_document['animations'].values():
        # Capture authored event poses and between-key interpolation, for every clip.
        duration = options.duration if animation is source_document['animations']['rotate_loop'] else options.duration/2
        for time in events:
            if time <= duration:
                progresses.add(time / duration)
        for a,b in zip(events, events[1:]):
            if b <= duration:
                progresses.add((a+b) / (2*duration))
    progresses = sorted(progresses)
    checks = {}
    pose_cache = {}
    for family, exact in SPINE_TARGETS.items():
        target = replace(options, spine_version=exact)
        authored_folder = folder / f'spine-{family}'
        package = build_package(front, None, None, authored_folder, target)
        authored = Path(package['json_path'])
        document = json.loads(authored.read_text(encoding='utf-8'))
        selected_fps = document['skeleton']['fps']
        if family in ('3.8', '4.2'):
            with patch('spine_turn_formats.select_native_safe_fps', return_value=30):
                fixed = convert_skeleton(source_document, exact)
            fixed['skeleton']['fps'] = selected_fps
            assert fixed == document, 'Native FPS policy changed shape or key times.'
        else:
            assert document == source_document
        native = convert_project(authored, authored_folder / f'{target.name}.spine', target_version=exact, overwrite=True)
        assert native['ok'], native
        exported = export_binary(native['project_path'], authored_folder / 'native-binary', target_version=exact)
        assert exported['ok'], exported
        binary = Path(exported['binary_paths'][0])
        for extension in ('.atlas', '.png'):
            shutil.copy2(authored.with_suffix(extension), binary.with_suffix(extension))
        family_checks = {}
        for kind,skeleton in [('authored-json',authored),('native-binary',binary)]:
            sampled = sample(skeleton, folder / f'{family}-{kind}-poses.json', family, progresses)
            assert sampled['data_version'] == exact
            if family=='3.8' and kind=='native-binary':
                assert sampled['authoring_fps']==selected_fps
            try:
                family_checks[kind] = validate_diamond(reference, sampled, canonical_options, prepared, pose_cache)
            except AssertionError as failure:
                raise AssertionError((label,family,kind,str(failure))) from failure
        manifest_path = authored_folder / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update(native_project_created=True, native_project=f'{target.name}.spine',
            native_roundtrip_verified=True, native_runtime_verification_format='binary',
            native_editor_version=exact, official_runtime_verified=True, official_runtime_family=family,
            input_back_image_supplied=False, back_reuses_front=True, original_artwork=original_artwork)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        if destination:
            target_folder = destination / f'spine-{family}'
            target_folder.mkdir(parents=True, exist_ok=True)
            for path in authored_folder.iterdir():
                if path.name == 'native-binary':
                    continue
                if path.is_dir():
                    shutil.copytree(path, target_folder / path.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(path, target_folder / path.name)
        checks[family] = {'revision':exact, 'authoring_fps':selected_fps, 'samples_per_action':len(progresses),
            'checks':family_checks, 'fps_adjustment_metadata_only':True}
        print(json.dumps({'case':label,'target':exact,'authoring_fps':selected_fps,'ok':True}), flush=True)
    assert hashlib.sha256(front.read_bytes()).hexdigest() == source_hash
    if destination:
        selected = replace(options, spine_version=selected_version or SPINE_TARGETS['4.2'])
        project_path = destination / project_name
        state = dict(animation='rotate_loop', background='checker', preview_zoom=100,
            show_ground=False,native_export=True,progress=0,playing=original_artwork)
        save_project(project_path, dict(front=str(front),back=None,edge=None),selected,state)
        loaded = load_project(project_path)
        try:
            assert asdict(loaded.options) == asdict(selected)
            assert loaded.ui_state == state and Path(loaded.paths['front']).read_bytes() == front.read_bytes()
            assert loaded.paths['back'] is None and loaded.paths['edge'] is None
            reopened = build_package(loaded.paths['front'],None,None,folder/'project-reopened',loaded.options)
            assert json.loads(Path(reopened['json_path']).read_text(encoding='utf-8')) == json.loads(
                (folder/f'spine-{spine_family(selected.spine_version)}'/f'{options.name}.json').read_text(encoding='utf-8'))
        finally:
            loaded.close()
        stage = Path(tempfile.mkdtemp(prefix='sequence-',dir=folder))
        sequence = export_sequence(prepared,selected,stage,fps=30,size=(512,512))
        shutil.copytree(stage,destination/'png-sequence',dirs_exist_ok=True)
        sequence_data = json.loads(Path(sequence['manifest_path']).read_text(encoding='utf-8'))
        assert sequence_data['status']=='complete' and sequence_data['frame_count']==60
        contact_sheet(prepared,selected,sequence_data['camera'],destination/'preview-contact-sheet.png')
        preview_gif(destination/'png-sequence',destination/'preview.gif')
        (destination/'delivery.json').write_text(json.dumps(dict(format=f'diamond-delivery-v{release}',
            targets=dict(SPINE_TARGETS),tool_project=project_name,tool_project_selected_target=selected.spine_version,
            tool_project_reload_geometry_identical=True,original_artwork=original_artwork,one_front_image=True,
            side_material_used=False,checks=checks),indent=2),encoding='utf-8')
        (destination/'README_zh-TW.md').write_text(
            '# 鑽石體積旋轉範例\n\n'
            f'在工具以「開啟編輯檔」選擇 `{project_name}`，即可繼續調整鑽石剖面、視角、反光分區、掃光、星芒和動畫。'
            '編輯檔內含原始透明 PNG。'+('這張青藍色切面圖片為本工具原創的幾何範例素材。' if original_artwork else
            '這張圖片由使用者提供，僅保存在此私人交付資料夾。')+'\n\n'
            '三個對應版本的 Spine 專案位於 `spine-3.8`、`spine-4.0`、`spine-4.2`。'
            '以相符的 3.8.99、4.0.56、4.2.43 開啟；皆已經原生匯入和官方 runtime 驗證。\n\n'
            '`preview.gif`、`preview-contact-sheet.png` 和 60 張透明 PNG 與原生專案使用相同設定。'
            '鑽石由台面、冠部、腰圍和底尖構成封閉體積；只需一張正面圖，未使用側邊材質。\n',encoding='utf-8')
    return dict(checks=checks,source_unchanged=True,editable_project_reload_verified=bool(destination))


def regressions():
    results = {}
    for label in ('default-strip','ridge'):
        old_folder = QA / f'baseline-v1.6-{label}'
        manifest = json.loads((old_folder/'manifest.json').read_text(encoding='utf-8'))
        options = TurnOptions(**manifest['options'])
        package = build_package(old_folder/'images/front.png',old_folder/'images/back.png',
            old_folder/'images/edge.png',QA/f'regression-{label}',options)
        old_file = next(p for p in old_folder.glob('*.json') if p.name!='manifest.json')
        old = json.loads(old_file.read_text(encoding='utf-8'))
        current = json.loads(Path(package['json_path']).read_text(encoding='utf-8'))
        for key in ('skins','animations','bones','slots'):
            assert old[key]==current[key],(label,key)
        baseline = json.loads((QA/f'baseline-v1.6-{label}-poses.json').read_text(encoding='utf-8'))
        progresses = [p['progress'] for p in next(iter(baseline['animations'].values()))['poses']]
        updated = sample(Path(package['json_path']),QA/f'regression-{label}-poses.json','4.0',progresses)
        results[label] = compare_runtime(baseline,updated)
    return results


def main():
    QA.mkdir(exist_ok=True)
    base = TurnOptions(name='diamond_v17',model='diamond',trim_transparent=False,
        diamond_shine_enabled=True,diamond_sparkles_enabled=True)
    cases = {
        'diamond-y-fx': base,
        'diamond-x-no-fx': replace(base,name='diamond_x_no_fx',axis='x',bounce_enabled=True,
            bounce_height=80,z_bounce_enabled=True,z_bounce_depth=140,peak_z_scale=1.25,
            bounce_start=.3,bounce_apex=.5,bounce_land=.7,bounce_end=.85,
            z_bounce_start=.1,z_bounce_apex=.2,z_bounce_end=.45,
            diamond_shine_enabled=False,diamond_sparkles_enabled=False),
        'diamond-y-cuts-fx':replace(base,name='diamond_cuts_v17',diamond_cut_regions=(
            (((-.45,.06),(-.23,.34),(-.12,.30),(-.18,.015)),-22,12),
            (((-.18,-.02),(.18,-.02),(0,-.48)),18,-15),
            (((.18,.02),(.45,.08),(.23,.33),(.12,.30)),30,8))),
    }
    results = {}
    for name,options in cases.items():
        destination = ROOT/'examples/diamond-v1.7' if name=='diamond-y-fx' else None
        if name=='diamond-y-cuts-fx':
            destination=ROOT/'examples/diamond-v1.7/cuts'
        results[name] = run_case(name,options,destination,'cuts.spturn' if 'cuts' in name else 'diamond.spturn')
        if name=='diamond-y-cuts-fx':
            shutil.copy2(destination/'cuts.spturn',destination.parent/'cuts.spturn')
            with (destination.parent/'README_zh-TW.md').open('a',encoding='utf-8') as readme:
                readme.write('\n另附 `cuts.spturn`，包含3個原圖反光分區及各自左右／上下朝向。其原生專案與匹配的60張透明PNG、GIF位於 `cuts/` 子資料夾。\n')
    regression = regressions()
    restored = _run([r'C:\Program Files\Spine\Spine.com','--update','4.0.56','--version'],60)
    assert restored['ok']
    report = dict(ok=True,targets=dict(SPINE_TARGETS),native_cases=9,cases=results,
        v1_6_regression_world_vertex_error=regression,restored_launcher_version=restored.get('editor_version'))
    (QA/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(ok=True,report=str(QA/'verification.json'),regressions=regression)),flush=True)


if __name__=='__main__':
    main()
