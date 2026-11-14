"""Exercise v1.1 features through native Spine and inspect official world vertices."""
from pathlib import Path
import json
import math
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa' / 'v1.1'
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, build_package, motion_at, pose_at, animation_pose_at
from spine_native import convert_project, export_runtime


def sample_runtime(skeleton, output):
    progress_file = QA / 'feature-progresses.json'
    progress_file.write_text(json.dumps(sorted(set([i / 240 for i in range(241)] +
        [0, .08, .16, .4, .8, .86, .93, 1]))), encoding='utf-8')
    run = subprocess.run(['node', str(ROOT / 'tests' / 'sample_runtime_v11.cjs'), str(skeleton), str(output), str(progress_file)],
        capture_output=True, text=True, encoding='utf-8')
    if run.returncode:
        raise RuntimeError(run.stderr or run.stdout)
    return json.loads(output.read_text(encoding='utf-8'))


def deform_at(frames, length, time):
    def unpack(frame):
        result = [0.] * length
        offset = frame.get('offset', 0)
        for index, value in enumerate(frame.get('vertices', [])):
            result[index + offset] = value
        return result
    if time < frames[0].get('time', 0):
        return [0.] * length
    for index, frame in enumerate(frames):
        if index == len(frames) - 1:
            return unpack(frame)
        after = frames[index + 1]
        if time < after.get('time', 0):
            a, b = unpack(frame), unpack(after)
            alpha = (time - frame.get('time', 0)) / (after.get('time', 0) - frame.get('time', 0))
            assert not frame.get('curve'), 'QA expects linear deform interpolation.'
            return [x + (y - x) * alpha for x, y in zip(a, b)]
    raise AssertionError('Timeline sampling failed.')


def validate_world(skeleton_path, sampled, options, height):
    raw = json.loads(Path(skeleton_path).read_text(encoding='utf-8'))
    skin = next(s for s in raw['skins'] if s['name'] == 'default')['attachments']
    maximum = {'bone_motion_error': 0., 'world_vertex_error': 0., 'shade_error': 0.,
        'preview_world_vertex_error': 0., 'preview_tint_error': 0., 'root_drift': 0.}
    maximum['ground_contact_error'] = 0.
    maximum['loop_world_vertex_seam'] = 0.
    for name, action in sampled['animations'].items():
        timeline = raw['animations'][name]
        for pose in action['poses']:
            progress = pose['progress']
            expected_motion = motion_at(progress, options, height=height)
            turn = pose['bones']['turn']
            for field in ['x', 'y', 'scale_x', 'scale_y']:
                maximum['bone_motion_error'] = max(maximum['bone_motion_error'], abs(turn[field] - expected_motion[field]))
            root = pose['bones']['root']
            maximum['root_drift'] = max(maximum['root_drift'], abs(root['world_x']), abs(root['world_y']))
            if progress in [0, .08, .8, .86, .93, 1]:
                min_y = min(value for mesh in pose['geometry'].values()
                    for index, value in enumerate(mesh['vertices']) if index % 2)
                maximum['ground_contact_error'] = max(maximum['ground_contact_error'],
                    abs(min_y + height * options.base_scale / 2))
            start = 180 if name == 'flip_to_front' else 0
            arc = 360 if name == 'rotate_loop' else 180
            shades = {m['name']: int(m['color'][:2], 16) / 255 for m in pose_at(start + arc * progress, options)}
            preview = {m['name']: m for m in animation_pose_at(progress, options,
                width=raw['skins'][0]['attachments']['front']['front']['width'], height=height, animation_name=name)}
            for slot, mesh in pose['geometry'].items():
                source = skin[slot][mesh['name']]
                frames = timeline['deform']['default'][slot][mesh['name']]
                delta = deform_at(frames, len(source['vertices']), progress * action['duration'])
                local = [v + d for v, d in zip(source['vertices'], delta)]
                expected = []
                for i in range(0, len(local), 2):
                    expected.extend((local[i] * expected_motion['scale_x'] + expected_motion['x'],
                        local[i + 1] * expected_motion['scale_y'] + expected_motion['y']))
                maximum['world_vertex_error'] = max(maximum['world_vertex_error'],
                    max(abs(a - b) for a, b in zip(expected, mesh['vertices'])))
                preview_local = preview[slot]['vertices']
                preview_world = []
                for i in range(0, len(preview_local), 2):
                    preview_world.extend((preview_local[i] * expected_motion['scale_x'] + expected_motion['x'],
                        preview_local[i + 1] * expected_motion['scale_y'] + expected_motion['y']))
                maximum['preview_world_vertex_error'] = max(maximum['preview_world_vertex_error'],
                    max(abs(a - b) for a, b in zip(preview_world, mesh['vertices'])))
                maximum['preview_tint_error'] = max(maximum['preview_tint_error'],
                    max(abs(a - b) for a, b in zip(preview[slot]['tint'], mesh['color'])))
                rgba = mesh['color']
                assert abs(rgba[3] - 1) < 1e-6, 'Slot shading changed alpha.'
                assert max(rgba[:3]) - min(rgba[:3]) < 1e-6, 'Slot shading is not neutral grayscale.'
                if slot in ['front', 'back']:
                    maximum['shade_error'] = max(maximum['shade_error'], abs(rgba[0] - shades[slot]))
        if name == 'rotate_loop':
            first, last = action['poses'][0]['geometry'], action['poses'][-1]['geometry']
            assert set(first) == set(last), 'Loop attachment seam.'
            for slot in first:
                maximum['loop_world_vertex_seam'] = max(maximum['loop_world_vertex_seam'],
                    max(abs(a - b) for a, b in zip(first[slot]['vertices'], last[slot]['vertices'])))
    assert maximum['root_drift'] < .0001, maximum
    return maximum


def compare_default_to_v1(skeleton):
    sample_file = QA / 'regression-progresses.json'
    sample_file.write_text(json.dumps([i / 24 for i in range(24)]), encoding='utf-8')
    output = QA / 'default-regression-poses.json'
    run = subprocess.run(['node', str(ROOT / 'tests' / 'sample_runtime_v11.cjs'), str(skeleton), str(output), str(sample_file)],
        capture_output=True, text=True, encoding='utf-8')
    assert run.returncode == 0, run.stderr
    new = json.loads(output.read_text(encoding='utf-8'))['animations']['rotate_loop']['poses']
    old = json.loads((QA / 'baseline-v1-runtime-poses.json').read_text(encoding='utf-8'))['poses']
    error = 0
    for a, b in zip(old, new):
        assert set(a['geometry']) == set(b['geometry'])
        for slot, mesh in a['geometry'].items():
            error = max(error, max(abs(x - y) for x, y in zip(mesh['vertices'], b['geometry'][slot]['vertices'])))
            assert mesh['color'] == b['geometry'][slot]['color']
    assert error < .0001, error
    return error


def main():
    QA.mkdir(parents=True, exist_ok=True)
    source = QA / 'authored'
    options = TurnOptions(name='spin_bounce_v11', edge_orientation='auto',
        base_scale=1.1, bounce_enabled=True, bounce_height=100, peak_scale=1.15,
        landing_squash=.12, shade_faces=True, min_brightness=.35, shade_curve=1.4, light_angle=30)
    from PIL import Image
    vertical = QA / 'edge-vertical.png'
    with Image.open(ROOT / 'assets' / 'demo-edge.png') as im:
        im.transpose(Image.Transpose.ROTATE_270).save(vertical)
    result = build_package(ROOT / 'assets' / 'demo-front.png', ROOT / 'assets' / 'demo-back.png',
        vertical, source, options)
    native = convert_project(result['json_path'], source / 'spin_bounce_v11.spine', overwrite=True)
    assert native['ok'], native
    exported = export_runtime(native['project_path'], QA / 'native-roundtrip')
    assert exported['ok'], exported
    roundtrip = Path(exported['json_paths'][0])
    for ext in ['.atlas', '.png']:
        shutil.copy2(Path(result['json_path']).with_suffix(ext), roundtrip.with_suffix(ext))
    checks = {}
    for label, skeleton in [('authored', Path(result['json_path'])), ('native-roundtrip', roundtrip)]:
        sampled = sample_runtime(skeleton, QA / f'{label}-world-poses.json')
        checks[label] = validate_world(skeleton, sampled, options, result['height'])
        assert checks[label]['bone_motion_error'] < (.01 if label == 'authored' else .4), checks[label]
        assert checks[label]['world_vertex_error'] < (.02 if label == 'authored' else .5), checks[label]
        assert checks[label]['shade_error'] < .035, checks[label]
        assert checks[label]['preview_world_vertex_error'] < (.02 if label == 'authored' else .5), checks[label]
        assert checks[label]['preview_tint_error'] < .001, checks[label]
        assert checks[label]['ground_contact_error'] < (.001 if label == 'authored' else .12), checks[label]
        assert checks[label]['loop_world_vertex_seam'] < .001, checks[label]
    default = build_package(ROOT / 'assets' / 'demo-front.png', ROOT / 'assets' / 'demo-back.png',
        ROOT / 'assets' / 'demo-edge.png', QA / 'default-regression', TurnOptions(name='demo_coin'))
    checks['default_regression_vertex_error'] = compare_default_to_v1(default['json_path'])
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update(native_project_created=True, native_project='spin_bounce_v11.spine',
        native_roundtrip_verified=True, official_runtime_verified=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    example = ROOT / 'examples' / 'spin-bounce-v1.1'
    shutil.copytree(source, example, dirs_exist_ok=True)
    report = {'ok': True, 'runtime': 'official Spine 4.0.31', 'native_editor': '4.0.56',
        'samples_per_action': len(sampled['animations']['rotate_loop']['poses']),
        'sampled_actions': ['rotate_loop', 'flip_to_back', 'flip_to_front'],
        'checks': checks, 'example': str(example), 'options': vars(options)}
    (QA / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
