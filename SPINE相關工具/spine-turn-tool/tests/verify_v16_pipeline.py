"""Official/runtime/native compatibility and editable-project round trips."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/v1.6'
USER_IMAGE = Path(r'D:\SLOT工作區\727_MoneyGong\圖騰靜態張\Symbol_Multiplier.png')
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, build_package, prepare_images, resolve_options, motion_key_progress
from spine_turn_formats import SPINE_TARGETS, convert_skeleton
from spine_native import convert_project, export_binary
from spine_turn_project import save_project, load_project
from spine_turn_sequence import export_sequence
from verify_v12_pipeline import validate
from verify_v14_pipeline import contact_sheet, preview_gif, region_guide, compare_runtime


def sample(skeleton, output, family, progresses):
    progress_file = output.with_suffix('.progress.json')
    progress_file.write_text(json.dumps(progresses), encoding='utf-8')
    result = subprocess.run(['node', str(ROOT / 'tests/sample_runtime_v16.cjs'), str(skeleton),
        str(output), str(progress_file), family], capture_output=True, text=True,
        encoding='utf-8', timeout=60, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(output.read_text(encoding='utf-8'))


def validate_target(reference, sampled, options, width, height):
    result = validate(reference, sampled, options, width, height)
    authored = json.loads(reference.read_text(encoding='utf-8'))['skins'][0]['attachments']
    uv_error = 0.
    for action in sampled['animations'].values():
        for pose in action['poses']:
            for slot, mesh in pose['geometry'].items():
                expected = authored[slot][mesh['name']]['uvs']
                uv_error = max(uv_error, max(abs(a - b) for a, b in zip(expected, mesh['uvs'])))
    result['source_uv_error'] = uv_error
    return result


def run_case(label, front, options, destination=None):
    folder = QA / 'native-targets' / label
    original_hash = hashlib.sha256(Path(front).read_bytes()).hexdigest()
    prepared = prepare_images(front, None, None, options)
    options = resolve_options(prepared, options)
    canonical_options = replace(options, spine_version='4.0.56')
    canonical = build_package(front, None, None, folder / 'canonical', canonical_options)
    reference = Path(canonical['json_path'])
    progresses = sorted(set([index / 240 for index in range(241)] + list(motion_key_progress(options))))
    checks = {}
    for family, exact in SPINE_TARGETS.items():
        target = replace(options, spine_version=exact)
        authored_folder = folder / f'spine-{family}'
        package = build_package(front, None, None, authored_folder, target)
        authored_path = Path(package['json_path'])
        target_document = json.loads(authored_path.read_text(encoding='utf-8'))
        selected_fps = target_document['skeleton']['fps']
        if family in ('3.8', '4.2'):
            with patch('spine_turn_formats.select_native_safe_fps', return_value=30):
                fixed_fps_document = convert_skeleton(json.loads(reference.read_text(encoding='utf-8')), exact)
            fixed_fps_document['skeleton']['fps'] = selected_fps
            assert fixed_fps_document == target_document, 'FPS compatibility changed geometry or key times.'
        else:
            assert selected_fps == json.loads(reference.read_text(encoding='utf-8'))['skeleton']['fps']
        native = convert_project(authored_path, authored_folder / f'{target.name}.spine',
            target_version=exact, overwrite=True)
        assert native['ok'], native
        binary_export = export_binary(native['project_path'], authored_folder / 'native-binary', target_version=exact)
        assert binary_export['ok'], binary_export
        binary = Path(binary_export['binary_paths'][0])
        for extension in ('.atlas', '.png'):
            shutil.copy2(authored_path.with_suffix(extension), binary.with_suffix(extension))
        family_checks = {}
        for kind, skeleton in [('authored-json', authored_path), ('native-binary', binary)]:
            sampled = sample(skeleton, folder / f'{family}-{kind}-poses.json', family, progresses)
            assert sampled['data_version'] == exact
            if family == '3.8' and kind == 'native-binary':
                assert sampled['authoring_fps'] == selected_fps, 'Native editor did not honor selected authoring FPS.'
            family_checks[kind] = validate_target(reference, sampled, canonical_options,
                prepared['width'], prepared['height'])
            for field in ('bone_motion_error', 'world_vertex_error', 'preview_world_vertex_error'):
                assert family_checks[kind][field] < .02, (label, family, kind, field, family_checks[kind][field])
            assert family_checks[kind]['source_uv_error'] < .000001
            assert family_checks[kind]['preview_tint_error'] < .001
            assert family_checks[kind]['root_drift'] < .0001
            assert family_checks[kind]['loop_world_vertex_seam'] < .002
        manifest_path = authored_folder / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update(native_project_created=True, native_project=f'{target.name}.spine',
            native_roundtrip_verified=True, native_runtime_verification_format='binary',
            native_editor_version=exact, official_runtime_verified=True,
            official_runtime_family=family, input_back_image_supplied=False, back_reuses_front=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        if destination:
            target_destination = destination / f'spine-{family}'
            target_destination.mkdir(parents=True, exist_ok=True)
            for item in authored_folder.iterdir():
                if item.name == 'native-binary':
                    continue
                if item.is_dir():
                    shutil.copytree(item, target_destination / item.name, dirs_exist_ok=True)
                elif item.is_file():
                    shutil.copy2(item, target_destination / item.name)
        checks[family] = {'revision': exact, 'authoring_fps': selected_fps,
            'fps_adjustment_metadata_only': True, 'checks': family_checks}
        print(json.dumps({'case': label, 'target': exact, 'authoring_fps': selected_fps, 'ok': True}), flush=True)
    if destination:
        destination.mkdir(parents=True, exist_ok=True)
        selected = replace(options, spine_version=SPINE_TARGETS['4.2'])
        project_name = 'user_multiplier.spturn' if label == 'private-ridge' else 'ridge_stone.spturn'
        project_file = destination / project_name
        ui_state = {'animation': 'rotate_loop', 'background': 'checker', 'preview_zoom': 100,
            'show_ground': False, 'native_export': True, 'progress': 0, 'playing': True}
        save_project(project_file, {'front': str(front), 'back': None, 'edge': None}, selected, ui_state)
        loaded = load_project(project_file)
        try:
            assert asdict(loaded.options) == asdict(selected)
            assert loaded.paths['back'] is None and loaded.paths['edge'] is None
            assert Path(loaded.paths['front']).read_bytes() == Path(front).read_bytes()
            assert loaded.ui_state == ui_state
            loaded_package = build_package(loaded.paths['front'], None, None,
                folder / 'project-reopened', loaded.options)
            original_target = folder / 'spine-4.2' / f'{options.name}.json'
            assert json.loads(Path(loaded_package['json_path']).read_text(encoding='utf-8')) == \
                json.loads(original_target.read_text(encoding='utf-8'))
        finally:
            loaded.close()
        stage = Path(tempfile.mkdtemp(prefix='sequence-', dir=folder))
        sequence = export_sequence(prepared, selected, stage, fps=30, size=(512, 512))
        shutil.copytree(stage, destination / 'png-sequence', dirs_exist_ok=True)
        sequence_manifest = json.loads(Path(sequence['manifest_path']).read_text(encoding='utf-8'))
        assert sequence_manifest['frame_count'] == 60 and sequence_manifest['status'] == 'complete'
        contact_sheet(prepared, selected, sequence_manifest['camera'], destination / 'preview-contact-sheet.png')
        preview_gif(destination / 'png-sequence', destination / 'preview.gif')
        region_guide(prepared, selected, destination / 'raised-region-guide.png')
        delivery = {'format': 'multi-target-spine-delivery-v1.6', 'targets': dict(SPINE_TARGETS),
            'tool_project': project_name, 'tool_project_selected_target': selected.spine_version,
            'tool_project_reload_geometry_identical': True, 'one_front_image': True,
            'back_reuses_front': True, 'side_material_used': False,
            'private_art': label == 'private-ridge', 'checks': checks}
        (destination / 'delivery.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding='utf-8')
        (destination / 'README_zh-TW.md').write_text(
            '# 可繼續編輯的單圖旋轉石塊\n\n'
            f'在工具按「開啟編輯檔」選擇 `{project_name}`，即可恢復原始圖片、圈選範圍、厚度、'
            'Y／Z 彈跳、明暗與預覽設定。此編輯檔已內含原始正面圖，可搬移到其他資料夾使用。\n\n'
            '原生 Spine 專案分別位於 `spine-3.8`、`spine-4.0`、`spine-4.2`；'
            '請使用對應的 3.8.99、4.0.56、4.2.43 開啟。資料格式與 native Binary 實際播放已分別驗證。\n\n'
            '本範例僅有一張正面圖；背面沿用正面，石塊模式不使用側邊貼圖。'
            '原圖內既有顏色與裝飾保留。`raised-region-guide.png` 顯示圈選範圍，'
            '`preview.gif` 與 60 張透明 PNG 使用同一組動畫設定。\n', encoding='utf-8')
    assert hashlib.sha256(Path(front).read_bytes()).hexdigest() == original_hash
    return {'checks': checks, 'source_unchanged': True,
        'editable_project_reload_verified': bool(destination), 'destination': str(destination) if destination else None}


def regressions():
    results = {}
    for label in ('default-strip', 'manual-strip', 'ridge'):
        previous_folder = QA / f'baseline-v1.5-{label}'
        old_manifest = json.loads((previous_folder / 'manifest.json').read_text(encoding='utf-8'))
        options = TurnOptions(**old_manifest['options'])
        package = build_package(previous_folder / 'images/front.png', previous_folder / 'images/back.png',
            previous_folder / 'images/edge.png', QA / f'regression-{label}', options)
        previous_file = next(p for p in previous_folder.glob('*.json') if p.name != 'manifest.json')
        old = json.loads(previous_file.read_text(encoding='utf-8'))
        current = json.loads(Path(package['json_path']).read_text(encoding='utf-8'))
        for section in ('skins', 'animations', 'slots', 'bones'):
            assert old[section] == current[section], (label, section)
        baseline = json.loads((QA / f'baseline-v1.5-{label}-poses.json').read_text(encoding='utf-8'))
        progresses = [pose['progress'] for pose in next(iter(baseline['animations'].values()))['poses']]
        updated = sample(Path(package['json_path']), QA / f'regression-{label}-poses.json', '4.0', progresses)
        results[label] = compare_runtime(baseline, updated)
    return results


def main():
    QA.mkdir(parents=True, exist_ok=True)
    generic_old = json.loads((ROOT / 'examples/ridge-stone-v1.5/manifest.json').read_text(encoding='utf-8'))
    generic = replace(TurnOptions(**generic_old['options']), name='multi_version_v16')
    private_old = json.loads((ROOT / 'output/user-multiplier-v1.5/manifest.json').read_text(encoding='utf-8'))
    private = replace(TurnOptions(**private_old['options']), name='user_multiplier_v16')
    results = {}
    results['complex-ridge'] = run_case('complex-ridge', ROOT / 'assets/demo-octagon.png', generic,
        ROOT / 'examples/multi-version-v1.6')
    results['default-strip'] = run_case('default-strip', ROOT / 'assets/demo-front.png',
        TurnOptions(name='default_strip_v16'))
    results['private-ridge'] = run_case('private-ridge', USER_IMAGE, private,
        ROOT / 'output/user-multiplier-v1.6')
    regression = regressions()
    report = {'ok': True, 'targets': dict(SPINE_TARGETS), 'native_cases': 9,
        'cases': results, 'v1_5_regression_world_vertex_error': regression,
        'runtime_note': 'Official branch3.8 compiled core; official npm spine-core4.0.31 and4.2.43.'}
    (QA / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'report': str(QA / 'verification.json'), 'regressions': regression}), flush=True)


if __name__ == '__main__':
    main()
