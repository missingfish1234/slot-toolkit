"""Check virtual depth using native 4.0.56 and actual official runtime geometry."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa' / 'v1.2'
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, build_package, depth_at, motion_at, animation_pose_at
from spine_native import convert_project, export_runtime
from verify_v11_pipeline import deform_at


PROGRESSES = sorted(set([i / 240 for i in range(241)] + [0, .08, .16, .4, .8, .86, .93, 1]))


def sample_runtime(skeleton: Path, destination: Path, progresses=PROGRESSES):
    sample_file = destination.with_suffix('.progress.json')
    sample_file.write_text(json.dumps(progresses), encoding='utf-8')
    completed = subprocess.run(['node', str(ROOT / 'tests' / 'sample_runtime_v11.cjs'),
        str(skeleton), str(destination), str(sample_file)], capture_output=True,
        text=True, encoding='utf-8', timeout=60, check=False)
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(destination.read_text(encoding='utf-8'))


def validate(skeleton: Path, sampled: dict, options: TurnOptions, width: float, height: float):
    document = json.loads(skeleton.read_text(encoding='utf-8'))
    attachments = next(s for s in document['skins'] if s['name'] == 'default')['attachments']
    maxima = dict.fromkeys(['bone_motion_error', 'world_vertex_error', 'preview_world_vertex_error',
        'preview_tint_error', 'root_drift', 'loop_world_vertex_seam', 'z_only_y_drift',
        'depth_uniform_scale_error', 'depth_preserves_physical_aspect_error'], 0.)
    count = 0
    for name, action in sampled['animations'].items():
        timeline = document['animations'][name]
        for sample in action['poses']:
            progress = sample['progress']
            expected_motion = motion_at(progress, options, height)
            physical_motion = sample['bones']['turn']
            active_bone = sample['bones'].get('depth', physical_motion)
            actual_motion = {'x': active_bone['world_x'], 'y': active_bone['world_y'],
                'scale_x': active_bone['a'], 'scale_y': active_bone['d']}
            if 'depth' in sample['bones']:
                depth_bone = sample['bones']['depth']
                maxima['depth_uniform_scale_error'] = max(maxima['depth_uniform_scale_error'],
                    abs(depth_bone['scale_x'] - depth_bone['scale_y']))
                maxima['depth_preserves_physical_aspect_error'] = max(
                    maxima['depth_preserves_physical_aspect_error'],
                    abs(actual_motion['scale_x'] / actual_motion['scale_y'] -
                        physical_motion['scale_x'] / physical_motion['scale_y']))
            for channel in ('x', 'y', 'scale_x', 'scale_y'):
                maxima['bone_motion_error'] = max(maxima['bone_motion_error'],
                    abs(expected_motion[channel] - actual_motion[channel]))
            root = sample['bones']['root']
            maxima['root_drift'] = max(maxima['root_drift'], abs(root['world_x']), abs(root['world_y']))
            if not options.bounce_enabled:
                maxima['z_only_y_drift'] = max(maxima['z_only_y_drift'], abs(actual_motion['y']))
            if options.z_bounce_enabled and not options.bounce_enabled:
                assert abs(actual_motion['scale_x'] - actual_motion['scale_y']) < .00001, 'Z-only depth added squash.'
            for value in actual_motion.values():
                assert abs(value) < 1e7, 'Implausible or invalid transform.'
            preview = {m['name']: m for m in animation_pose_at(progress, options,
                width=width, height=height, animation_name=name)}
            for slot, mesh in sample['geometry'].items():
                source = attachments[slot][mesh['name']]
                delta = deform_at(timeline['deform']['default'][slot][mesh['name']],
                    len(source['vertices']), progress * action['duration'])
                local = [value + offset for value, offset in zip(source['vertices'], delta)]
                world = []
                preview_world = []
                for index in range(0, len(local), 2):
                    world.extend((local[index] * expected_motion['scale_x'] + expected_motion['x'],
                        local[index + 1] * expected_motion['scale_y'] + expected_motion['y']))
                    preview_local = preview[slot]['vertices']
                    preview_world.extend((preview_local[index] * expected_motion['scale_x'] + expected_motion['x'],
                        preview_local[index + 1] * expected_motion['scale_y'] + expected_motion['y']))
                maxima['world_vertex_error'] = max(maxima['world_vertex_error'],
                    max(abs(a - b) for a, b in zip(world, mesh['vertices'])))
                maxima['preview_world_vertex_error'] = max(maxima['preview_world_vertex_error'],
                    max(abs(a - b) for a, b in zip(preview_world, mesh['vertices'])))
                maxima['preview_tint_error'] = max(maxima['preview_tint_error'],
                    max(abs(a - b) for a, b in zip(preview[slot]['tint'], mesh['color'])))
                assert abs(mesh['color'][3] - 1) < .000001, 'Brightness modified alpha.'
                assert max(mesh['color'][:3]) - min(mesh['color'][:3]) < .000001, 'Neutral brightness altered hue.'
                count += 1
        if name == 'rotate_loop':
            first, last = action['poses'][0]['geometry'], action['poses'][-1]['geometry']
            assert set(first) == set(last), 'Loop attachments fail to return.'
            for slot in first:
                maxima['loop_world_vertex_seam'] = max(maxima['loop_world_vertex_seam'],
                    max(abs(a - b) for a, b in zip(first[slot]['vertices'], last[slot]['vertices'])))
    maxima['visible_mesh_samples'] = count
    return maxima


def default_regression():
    result = build_package(ROOT / 'assets/demo-front.png', ROOT / 'assets/demo-back.png',
        ROOT / 'assets/demo-edge.png', QA / 'default-regression', TurnOptions(name='demo_coin'))
    samples = sample_runtime(Path(result['json_path']), QA / 'default-regression-poses.json',
        [index / 24 for index in range(24)])['animations']['rotate_loop']['poses']
    baseline = json.loads((ROOT / 'qa/v1.1/baseline-v1-runtime-poses.json').read_text(encoding='utf-8'))['poses']
    error = 0.
    for old, new in zip(baseline, samples):
        assert set(old['geometry']) == set(new['geometry'])
        for slot, mesh in old['geometry'].items():
            current = new['geometry'][slot]
            error = max(error, max(abs(a - b) for a, b in zip(mesh['vertices'], current['vertices'])))
            assert mesh['color'] == current['color']
    assert error < .0001, error
    return error


def run_case(label, options):
    folder = QA / label
    source = folder / 'authored'
    result = build_package(ROOT / 'assets/demo-front.png', ROOT / 'assets/demo-back.png',
        ROOT / 'assets/demo-edge.png', source, options)
    native = convert_project(result['json_path'], source / f'{options.name}.spine', overwrite=True)
    assert native['ok'], native
    exported = export_runtime(native['project_path'], folder / 'native-roundtrip')
    assert exported['ok'], exported
    roundtrip = Path(exported['json_paths'][0])
    for extension in ('.atlas', '.png'):
        shutil.copy2(Path(result['json_path']).with_suffix(extension), roundtrip.with_suffix(extension))
    checks = {}
    for kind, skeleton in [('authored', Path(result['json_path'])), ('native-roundtrip', roundtrip)]:
        sampled = sample_runtime(skeleton, folder / f'{kind}-world-poses.json')
        checks[kind] = validate(skeleton, sampled, options, result['width'], result['height'])
        limit = .25 if kind == 'native-roundtrip' else .02
        assert checks[kind]['bone_motion_error'] < limit, (label, kind, checks[kind])
        assert checks[kind]['world_vertex_error'] < limit, (label, kind, checks[kind])
        assert checks[kind]['preview_world_vertex_error'] < limit, (label, kind, checks[kind])
        assert checks[kind]['preview_tint_error'] < .001, (label, kind, checks[kind])
        assert checks[kind]['root_drift'] < .0001, (label, kind, checks[kind])
        assert checks[kind]['z_only_y_drift'] < .0001, (label, kind, checks[kind])
        assert checks[kind]['depth_uniform_scale_error'] < .00001, (label, kind, checks[kind])
        assert checks[kind]['depth_preserves_physical_aspect_error'] < .00001, (label, kind, checks[kind])
        assert checks[kind]['loop_world_vertex_seam'] < .002, (label, kind, checks[kind])
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update(native_project_created=True, native_project=f'{options.name}.spine',
        native_roundtrip_verified=True, official_runtime_verified=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if label == 'both':
        shutil.copytree(source, ROOT / 'examples/z-bounce-v1.2', dirs_exist_ok=True)
    return {'options': vars(options), 'checks': checks,
        'depth_apex': depth_at(.4, options), 'project': native['project_path']}


def main():
    QA.mkdir(parents=True, exist_ok=True)
    light = dict(shade_faces=True, min_brightness=.35, shade_curve=1.4, light_angle=30)
    both = TurnOptions(name='z_bounce_v12', base_scale=1.1, bounce_enabled=True,
        bounce_height=110, peak_scale=1.15, landing_squash=.12,
        z_scale=1.2, peak_z_scale=1.5, z_bounce_enabled=True,
        z_bounce_depth=180, z_offset=40, camera_distance=1000, **light)
    cases = {
        'z-only': replace(both, name='z_only', bounce_enabled=False),
        'z-only-far': replace(both, name='z_only_far', bounce_enabled=False,
            z_bounce_depth=-220),
        'y-only': replace(both, name='y_only', z_bounce_enabled=False, z_offset=0,
            z_scale=1, peak_z_scale=1),
        'both': both,
        'static-depth': TurnOptions(name='static_depth', base_scale=.9,
            z_offset=150, camera_distance=1000, z_scale=1.4, **light),
        'thickness-only': TurnOptions(name='thickness_only', z_scale=2.25, **light),
    }
    checks = {}
    for label, options in cases.items():
        checks[label] = run_case(label, options)
        print(json.dumps({'case': label, 'ok': True}), flush=True)
    regression = default_regression()
    report = {'ok': True, 'native_editor': '4.0.56', 'runtime': 'official Spine 4.0.31',
        'samples_per_action': len(PROGRESSES), 'actions_per_case': 3,
        'native_roundtrip_cases': len(cases), 'checks': checks,
        'default_regression_world_vertex_error': regression,
        'example': str(ROOT / 'examples/z-bounce-v1.2'),
        'review_scope': 'Structural/native/runtime geometry and tint; visual artist acceptance remains separate.'}
    (QA / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'report': str(QA / 'verification.json'),
        'cases': list(cases), 'default_regression_error': regression}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
