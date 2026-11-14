"""Native/runtime evidence for manually drawn, off-center raised regions."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/v1.4'
USER_IMAGE = Path(r'D:\SLOT工作區\727_MoneyGong\圖騰靜態張\Symbol_Multiplier.png')
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, build_package, prepare_images, resolve_options,
    motion_at, motion_key_progress, depth_at)
from spine_native import convert_project, export_runtime, discover_spine, _run
from spine_turn_sequence import export_sequence
from spine_turn_preview import render_pose
from verify_v12_pipeline import validate
from test_v14_raised_region import TRIANGLE, PENTAGON


def sample_runtime(skeleton, destination, progresses):
    progress_file = destination.with_suffix('.progress.json')
    progress_file.write_text(json.dumps(progresses), encoding='utf-8')
    completed = subprocess.run(['node', str(ROOT / 'tests/sample_runtime_v13.cjs'),
        str(skeleton), str(destination), str(progress_file)], capture_output=True,
        text=True, encoding='utf-8', timeout=60, check=False)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(destination.read_text(encoding='utf-8'))


def timing_assertions(options, height):
    """Check physical Y contact independently of rotation and depth scale."""
    y_only = replace(options, z_bounce_enabled=False, z_offset=0)
    prep = max(0., options.bounce_start - (options.bounce_apex - options.bounce_start) / 4)
    events = sorted(set([i / 1000 for i in range(1001)] + list(motion_key_progress(options)) +
        [prep, options.bounce_start, options.bounce_apex, options.bounce_land,
         options.bounce_end, options.z_bounce_start, options.z_bounce_apex, options.z_bounce_end]))
    rest_error = contact_error = z_rest_error = 0.
    for progress in events:
        value = motion_at(progress, y_only, height)
        elevation = value['y'] - height * (value['scale_y'] - options.base_scale) / 2
        if progress <= prep + 1e-9 or progress >= options.bounce_end - 1e-9:
            rest_error = max(rest_error, abs(value['y']),
                abs(value['scale_x'] - options.base_scale), abs(value['scale_y'] - options.base_scale))
        if progress <= options.bounce_start + 1e-9 or progress >= options.bounce_land - 1e-9:
            contact_error = max(contact_error, abs(elevation))
        if progress <= options.z_bounce_start + 1e-9 or progress >= options.z_bounce_end - 1e-9:
            depth = depth_at(progress, options)
            z_rest_error = max(z_rest_error, abs(depth['z_offset'] - options.z_offset),
                abs(depth['z_scale'] - options.z_scale))
    apex = motion_at(options.bounce_apex, y_only, height)
    apex_elevation = apex['y'] - height * (apex['scale_y'] - options.base_scale) / 2
    assert rest_error < .0001, rest_error
    assert contact_error < .0001, contact_error
    assert z_rest_error < .0001, z_rest_error
    assert abs(apex_elevation - options.bounce_height) < .0001, apex_elevation
    return {'anticipation_start': prep, 'rest_error': rest_error,
        'ground_contact_error': contact_error, 'z_rest_error': z_rest_error,
        'apex_elevation': apex_elevation, 'evaluated_samples': len(events)}


def compare_runtime(old, new):
    maximum = 0.
    for name, action in old['animations'].items():
        updated = new['animations'][name]
        assert action['duration'] == updated['duration']
        assert len(action['poses']) == len(updated['poses'])
        for before, after in zip(action['poses'], updated['poses']):
            assert before['progress'] == after['progress']
            assert set(before['geometry']) == set(after['geometry'])
            for slot, mesh in before['geometry'].items():
                maximum = max(maximum, max(abs(a - b) for a, b in
                    zip(mesh['vertices'], after['geometry'][slot]['vertices'])))
                assert mesh['color'] == after['geometry'][slot]['color']
    assert maximum < .0001, maximum
    return maximum


def default_regression():
    paths = {}
    for label in ('default', 'y-z', 'auto-bevel'):
        previous_folder = QA / f'baseline-v1.3-{label}'
        previous_manifest = json.loads((previous_folder / 'manifest.json').read_text(encoding='utf-8'))
        options = TurnOptions(**previous_manifest['options'])
        baseline = json.loads((QA / f'baseline-v1.3-{label}-poses.json').read_text(encoding='utf-8'))
        package = build_package(previous_folder / 'images/front.png', previous_folder / 'images/back.png',
            previous_folder / 'images/edge.png', QA / f'regression-{label}', options)
        first_action = next(iter(baseline['animations'].values()))
        progresses = [pose['progress'] for pose in first_action['poses']]
        updated = sample_runtime(Path(package['json_path']), QA / f'regression-{label}-poses.json', progresses)
        paths[label] = compare_runtime(baseline, updated)
    return paths


def contact_sheet(prepared, options, camera, output_path):
    sheet = Image.new('RGB', (4 * 276, 2 * 304), '#202637')
    painter = ImageDraw.Draw(sheet)
    for cell, angle in enumerate(range(0, 360, 45)):
        thumb = render_pose(prepared, options, angle, size=(512, 512),
            background='transparent', progress=angle / 360, show_ground=False, camera=camera)
        thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
        x, y = (cell % 4) * 276 + 10, (cell // 4) * 304 + 12
        for checker_y in range(0, 256, 16):
            for checker_x in range(0, 256, 16):
                shade = '#343d50' if (checker_x + checker_y) // 16 % 2 else '#283044'
                painter.rectangle((x + checker_x, y + checker_y, x + checker_x + 15,
                    y + checker_y + 15), fill=shade)
        sheet.paste(thumb, (x + (256 - thumb.width) // 2, y + (256 - thumb.height) // 2), thumb)
        painter.text((x, y + 267), f'{angle / 360 * options.duration:.2f}s / {angle} deg', fill='#edf2fa')
    sheet.save(output_path)


def preview_gif(sequence_folder, output_path, fps=30):
    rgb_frames = []
    for frame in sorted(sequence_folder.glob('frame_*.png')):
        with Image.open(frame) as source:
            canvas = Image.new('RGB', source.size, '#202637')
            canvas.paste(source, (0, 0), source.getchannel('A'))
            rgb_frames.append(canvas)
    swatches = Image.new('RGB', (128 * 10, 128 * 6), '#202637')
    for index, frame in enumerate(rgb_frames):
        swatches.paste(frame.resize((128, 128)), ((index % 10) * 128, (index // 10) * 128))
    palette = swatches.quantize(colors=255)
    frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in rgb_frames]
    durations = [round((index + 1) * 100 / fps) * 10 - round(index * 100 / fps) * 10
        for index in range(len(frames))]
    frames[0].save(output_path, save_all=True, append_images=frames[1:],
        duration=durations, loop=0, disposal=2, optimize=False)


def region_guide(prepared, options, output_path):
    canvas = Image.new('RGBA', (640, 680), '#192131')
    width, height = prepared['width'], prepared['height']
    scale = min(540 / width, 540 / height)
    display = prepared['front'].resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
    origin = ((640 - display.width) / 2, 85 + (540 - display.height) / 2)
    canvas.alpha_composite(display, (round(origin[0]), round(origin[1])))
    overlay = Image.new('RGBA', canvas.size)
    painter = ImageDraw.Draw(overlay)
    def project(points):
        return [(origin[0] + (x + .5) * width * scale,
            origin[1] + (.5 - y) * height * scale) for x, y in points]
    outer, inner = project(options.contour_points), project(options.raised_contour_points)
    painter.polygon(inner, fill='#ffad3030')
    painter.line(outer + outer[:1], fill='#65d5ff', width=3)
    painter.line(inner + inner[:1], fill='#ffbd57', width=4)
    for index, (x, y) in enumerate(inner, 1):
        painter.ellipse((x - 6, y - 6, x + 6, y + 6), fill='#ffbd57', outline='white', width=1)
        painter.text((x + 9, y - 13), str(index), fill='white', stroke_width=1, stroke_fill='#111827')
    canvas = Image.alpha_composite(canvas, overlay)
    painter = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf', 20)
    except OSError:
        font = ImageFont.load_default()
    painter.text((30, 22), 'Manual raised region', fill='#edf2fa', font=font)
    painter.text((30, 640), 'BLUE: outer contour    ORANGE: raised region', fill='#edf2fa', font=font)
    canvas.convert('RGB').save(output_path)


def run_case(label, front, options, destination=None, solid_edge=False):
    folder = QA / label
    source = folder / 'authored'
    source_hash = hashlib.sha256(Path(front).read_bytes()).hexdigest()
    edge = None
    if solid_edge:
        edge = QA / 'generated-purple-rim.png'
        Image.new('RGBA', (256, 32), '#9612ac').save(edge)
    prepared = prepare_images(front, None, edge, options)
    resolved = resolve_options(prepared, options)
    timing = timing_assertions(resolved, prepared['height'])
    package = build_package(front, None, edge, source, resolved)
    with Image.open(front) as original, Image.open(source / 'images/front.png') as exported_front:
        original_rgba = original.convert('RGBA')
        original_crop = original_rgba.crop(original_rgba.getchannel('A').getbbox())
        assert original_crop.size == exported_front.size
        assert original_crop.tobytes() == exported_front.convert('RGBA').tobytes(), 'Source front painting changed.'
    native = convert_project(package['json_path'], source / f'{resolved.name}.spine', overwrite=True)
    assert native['ok'], native
    reexport = export_runtime(native['project_path'], folder / 'native-roundtrip')
    assert reexport['ok'], reexport
    roundtrip = Path(reexport['json_paths'][0])
    binary_folder = folder / 'native-binary'
    binary_folder.mkdir(exist_ok=True)
    binary_export = _run([discover_spine(), '--update', '4.0.56', '-i', native['project_path'],
        '-o', str(binary_folder.resolve()), '-e', 'binary'], 120)
    assert binary_export['ok'], binary_export
    binary = next(binary_folder.glob('*.skel'))
    for extension in ('.atlas', '.png'):
        shutil.copy2(Path(package['json_path']).with_suffix(extension), roundtrip.with_suffix(extension))
        shutil.copy2(Path(package['json_path']).with_suffix(extension), binary.with_suffix(extension))
    events = sorted(set([index / 240 for index in range(241)] + list(motion_key_progress(resolved)) +
        [resolved.z_bounce_start, resolved.z_bounce_apex, resolved.z_bounce_end]))
    checks = {}
    for kind, skeleton in [('authored', Path(package['json_path'])),
        ('native-json-export', roundtrip), ('native-binary-roundtrip', binary)]:
        sampled = sample_runtime(skeleton, folder / f'{kind}-poses.json', events)
        reference = Path(package['json_path']) if kind == 'native-binary-roundtrip' else skeleton
        checks[kind] = validate(reference, sampled, resolved, prepared['width'], prepared['height'])
        authored = json.loads(Path(package['json_path']).read_text(encoding='utf-8'))
        source_attachments = authored['skins'][0]['attachments']
        uv_error = 0.
        for action in sampled['animations'].values():
            for pose in action['poses']:
                for slot, mesh in pose['geometry'].items():
                    expected_uvs = source_attachments[slot][mesh['name']]['uvs']
                    uv_error = max(uv_error, max(abs(a - b) for a, b in zip(expected_uvs, mesh['uvs'])))
        checks[kind]['source_uv_error'] = uv_error
        # Native JSON rounds control points, scales, and translations; it is
        # measured separately. Native binary is the unrounded evidence from
        # the actual saved .spine project, held to the original strict gate.
        if kind != 'native-json-export':
            for field in ('bone_motion_error', 'world_vertex_error', 'preview_world_vertex_error'):
                assert checks[kind][field] < .02, (label, kind, field, checks[kind][field])
            assert uv_error < .000001, (label, kind, 'source_uv_error', uv_error)
        assert checks[kind]['preview_tint_error'] < .001
        assert checks[kind]['root_drift'] < .0001
        assert checks[kind]['depth_uniform_scale_error'] < .00001
        assert checks[kind]['depth_preserves_physical_aspect_error'] < .00001
        assert checks[kind]['loop_world_vertex_seam'] < .002
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update(native_project_created=True, native_project=f'{resolved.name}.spine',
        native_roundtrip_verified=True, official_runtime_verified=True,
        native_runtime_verification_format='binary',
        native_json_quantization_error_px=checks['native-json-export']['preview_world_vertex_error'],
        input_back_image_supplied=False, back_reuses_front=True,
        polygon_verified_point_count=len(resolved.contour_points),
        manual_region_verified_point_count=len(resolved.raised_contour_points))
    if solid_edge:
        manifest.update(edge_is_placeholder=True,
            generated_edge_material={'kind': 'solid', 'color': '#9612ac',
                'note': 'Tool-generated placeholder; user supplied no side or back image.'})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if destination:
        shutil.copytree(source, destination, dirs_exist_ok=True)
        # Always regenerate after a geometry/UV/renderer revision, even when
        # the visible option values are unchanged. This avoids stale proofs.
        import tempfile
        stage = Path(tempfile.mkdtemp(prefix='sequence-', dir=folder))
        sequence = export_sequence(prepared, resolved, stage,
            animation_name='rotate_loop', fps=30, size=(512, 512))
        shutil.copytree(stage, destination / 'png-sequence', dirs_exist_ok=True)
        sequence_manifest = json.loads(Path(sequence['manifest_path']).read_text(encoding='utf-8'))
        assert sequence_manifest['options'] == manifest['options']
        assert sequence_manifest['frame_count'] == 60 and sequence_manifest['status'] == 'complete'
        for frame in map(Path, sequence['frame_paths']):
            with Image.open(frame) as image:
                assert image.mode == 'RGBA' and image.size == (512, 512)
                bounds = image.getchannel('A').getbbox()
                assert bounds and bounds[0] > 0 and bounds[1] > 0 and bounds[2] < 512 and bounds[3] < 512
        contact_sheet(prepared, resolved, sequence_manifest['camera'], destination / 'preview-contact-sheet.png')
        preview_gif(destination / 'png-sequence', destination / 'preview.gif')
        region_guide(prepared, resolved, destination / 'raised-region-guide.png')
        if label == 'user-multiplier':
            (destination / 'README_zh-TW.md').write_text(
                '# 八角形圖騰翻轉範例\n\n'
                '開啟 `user_multiplier_v14.spine`，在 Spine 4.0.56 的 Animate 模式選擇 '
                '`rotate_loop`。另有 `flip_to_back` 與 `flip_to_front` 半圈動畫。\n\n'
                '使用提供的 Symbol_Multiplier.png 擷取八角形透明外框，原始檔案未改動。'
                '目前背面沿用正面，側邊為工具產生的紫色材質；這些替代設定已記錄於 manifest.json。\n\n'
                '`raised-region-guide.png` 可查看本範例的圈選範圍，頂點保存在 manifest.json。\n\n'
                '整圈為 2 秒。Y 起跳／高點／落地／恢復完成為 0.6／1.0／1.4／1.7 秒；'
                'Z 開始／高點／返回為 0.2／0.4／0.9 秒。起跳前有短暫預備壓縮。'
                '厚度 32 像素，手動凸起區域為略偏中心的內八角形，深度為厚度的 25%。'
                '這是一個封閉凸多邊形與單一高度的範例；目前前後面沿用相同實體區域。\n\n'
                '`preview.gif` 與 `preview-contact-sheet.png` 供快速檢視；'
                '`png-sequence` 內含同一組設定的 60 張 512×512 透明 PNG，30 FPS、固定畫布。'
                '請保留 images 資料夾與原生專案一起使用。\n', encoding='utf-8')
    assert hashlib.sha256(Path(front).read_bytes()).hexdigest() == source_hash
    return {'checks': checks, 'timing': timing, 'samples_per_action': len(events),
        'source_png_unchanged': True, 'trimmed_front_pixels_preserved_exactly': True,
        'contour_points': resolved.contour_points, 'raised_contour_points': resolved.raised_contour_points,
        'destination': str(destination) if destination else None}


def main():
    QA.mkdir(parents=True, exist_ok=True)
    common = dict(shape='polygon', bevel_width=0, bevel_depth=.25,
        duration=2, thickness=32, bounce_enabled=True,
        bounce_height=90, base_scale=1, peak_scale=1.12, landing_squash=.12,
        bounce_start=.3, bounce_apex=.5, bounce_land=.7, bounce_end=.85,
        z_bounce_enabled=True, z_bounce_depth=160, peak_z_scale=1.3,
        z_bounce_start=.1, z_bounce_apex=.2, z_bounce_end=.45,
        shade_faces=True, min_brightness=.4, shade_curve=1.2, light_angle=20)
    generic = ROOT / 'assets/demo-octagon.png'
    triangle = TurnOptions(name='manual_triangle_v14', axis='x', raised_contour_points=TRIANGLE, **common)
    pentagon = TurnOptions(name='timed_polygon_v14', raised_contour_points=PENTAGON, **common)
    cases = {}
    cases['offcenter-triangle-x'] = run_case('offcenter-triangle-x', generic, triangle)
    print(json.dumps({'case': 'offcenter-triangle-x', 'ok': True}), flush=True)
    cases['offcenter-pentagon-y'] = run_case('offcenter-pentagon-y', generic, pentagon,
        ROOT / 'examples/timed-polygon-v1.4')
    print(json.dumps({'case': 'offcenter-pentagon-y', 'ok': True}), flush=True)
    zero_height = replace(pentagon, name='zero_height_v14', bevel_depth=0)
    cases['manual-zero-height'] = run_case('manual-zero-height', generic, zero_height)
    print(json.dumps({'case': 'manual-zero-height', 'ok': True}), flush=True)
    private_prepared = prepare_images(USER_IMAGE, options=TurnOptions(shape='polygon'))
    private_outer = resolve_options(private_prepared, TurnOptions(shape='polygon')).contour_points
    private_inner = tuple((x * .72 + .035, y * .72 + .015) for x, y in private_outer)
    private = replace(pentagon, name='user_multiplier_v14', edge_color='#9612ac',
        raised_contour_points=private_inner)
    cases['user-multiplier'] = run_case('user-multiplier', USER_IMAGE, private,
        ROOT / 'output/user-multiplier-v1.4', solid_edge=True)
    print(json.dumps({'case': 'user-multiplier', 'ok': True}), flush=True)
    regressions = default_regression()
    report = {'ok': True, 'native_editor': '4.0.56', 'runtime': 'official Spine 4.0.31',
        'cases': cases, 'regression_world_vertex_errors': regressions,
        'private_art_excluded_from_generic_examples': True}
    (QA / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'report': str(QA / 'verification.json'),
        'regressions': regressions}), flush=True)


if __name__ == '__main__':
    main()
