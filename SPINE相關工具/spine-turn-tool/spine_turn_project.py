"""Self-contained editable .spturn projects: JSON settings plus original images.

This is the tool's editable project, separate from a native Spine .spine file.
No archive paths are extracted directly and no executable project data is used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

from PIL import Image, UnidentifiedImageError
import spine_turn_core as core

PROJECT_FORMAT = 'spine-turn-studio-project'
SCHEMA_VERSION = 1
APPLICATION_VERSION = '1.14.0'
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 192 * 1024 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_PROJECT_BYTES = MAX_TOTAL_ASSET_BYTES + MAX_MANIFEST_BYTES + 1024 * 1024
ASSET_LABELS = {'front': '正面', 'back': '背面', 'edge': '側邊'}
IMAGE_EXTENSIONS = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp', 'BMP': '.bmp', 'TIFF': '.tiff', 'GIF': '.gif'}


def _json_copy(value, label):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, RecursionError):
        raise ValueError(f'{label}包含無法儲存的資料。') from None


def _ui_snapshot(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('畫面設定必須是設定物件。')
    result = _json_copy(value, '畫面設定')
    for key, choices in {'animation': set(core.CLIP_ARCS),
                         'background': {'checker', 'dark', 'light'}}.items():
        if key in result and (not isinstance(result[key], str) or result[key] not in choices):
            raise ValueError(f'編輯檔的畫面設定「{key}」無效。')
    if 'current_animation' in result and not isinstance(result['current_animation'], str):
        raise ValueError('編輯檔的畫面設定「current_animation」必須是文字。')
    for key in ('show_ground', 'native_export', 'playing'):
        if key in result and not isinstance(result[key], bool):
            raise ValueError(f'編輯檔的畫面設定「{key}」必須是開關值。')
    for key, minimum, maximum in [('preview_zoom', 25, 250), ('progress', 0, 1)]:
        if key in result:
            number = result[key]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not minimum <= number <= maximum:
                raise ValueError(f'編輯檔的畫面設定「{key}」需介於 {minimum} 到 {maximum}。')
    # Missing keys are valid for older projects; the UI supplies its defaults.
    return result


def _freeze(value):
    return tuple(_freeze(item) for item in value) if isinstance(value, (list, tuple)) else value


def _option_snapshot(value):
    if isinstance(value, core.TurnOptions):
        data = asdict(value)
    elif isinstance(value, dict):
        data = dict(value)
    else:
        raise ValueError('請提供有效的工具設定。')
    definitions = {field.name: field for field in fields(core.TurnOptions)}
    unknown = sorted(set(data) - set(definitions))
    if unknown:
        raise ValueError('此編輯檔包含較新版本的設定，請更新工具後再開啟：' + '、'.join(unknown))
    for name, field in definitions.items():
        if name not in data:
            continue
        if isinstance(field.default, bool) and not isinstance(data[name], bool):
            raise ValueError(f'編輯檔的設定「{name}」必須是開關值。')
        if isinstance(field.default, str) and not isinstance(data[name], str):
            raise ValueError(f'編輯檔的設定「{name}」必須是文字。')
        if isinstance(field.default, tuple):
            data[name] = _freeze(data[name])
    try:
        options = core.TurnOptions(**data)
        name = options.name
        if not name or len(name) > 80 or any(character in name for character in '<>:"/\\|?*') or name in ('.', '..'):
            raise ValueError('專案名稱需為 1–80 字，且不可包含路徑或特殊符號。')
        if isinstance(options.segments, bool) or float(options.segments) != int(options.segments):
            raise ValueError('側邊分段數必須是整數。')
        core.normalize_options(options)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f'編輯檔的工具設定無效：{error}') from None
    _json_copy(asdict(options), '工具設定')
    return options


def _inspect_image(data, kind):
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError(f'{ASSET_LABELS[kind]}圖片超過 4,000 萬像素上限。')
            if image.format not in IMAGE_EXTENSIONS:
                raise ValueError(f'{ASSET_LABELS[kind]}圖片格式不支援。')
            format_name = image.format
            image.verify()
        return format_name, [width, height]
    except Image.DecompressionBombError:
        raise ValueError(f'{ASSET_LABELS[kind]}圖片超過 4,000 萬像素上限。') from None
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError(f'{ASSET_LABELS[kind]}素材不是可讀取的圖片。') from None


def _validate_content(paths, options, animations=None):
    try:
        checked = set()
        for record in animations or [{'options': {}}]:
            normalized = core.normalize_options(core.animation_effective_options(options, record['options'])
                                                if animations else options)
            # Only the flip axis changes how artwork is prepared; check each one once.
            if normalized.axis in checked:
                continue
            checked.add(normalized.axis)
            prepared = core.prepare_images(paths['front'], paths['back'], paths['edge'], normalized)
            core.resolve_options(prepared, normalized)
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError(f'編輯檔的圖片或設定無法使用：{error}') from None


def _animation_snapshot(value, options):
    """Validated animation records; missing means a project saved before animation sets."""
    if value is None:
        return core.legacy_animation_set(options)
    try:
        records = core.normalize_animation_set(_json_copy(value, '動畫清單'))
        for record in records:
            core.normalize_options(core.animation_effective_options(options, record['options']))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f'編輯檔的動畫清單無效：{error}') from None
    return records


def _collect_sources(paths):
    if not isinstance(paths, dict) or not paths.get('front'):
        raise ValueError('請先放入正面圖片，再儲存編輯檔。')
    assets, payloads, total = {}, {}, 0
    for kind, label in ASSET_LABELS.items():
        filename = paths.get(kind)
        if not filename:
            assets[kind] = None
            continue
        source = Path(filename)
        try:
            if not source.is_file():
                raise ValueError(f'找不到{label}原始圖片，請重新選取素材。')
            if source.stat().st_size > MAX_ASSET_BYTES:
                raise ValueError(f'{label}原始圖片超過 64 MiB 上限。')
            with source.open('rb') as stream:
                data = stream.read(MAX_ASSET_BYTES + 1)
        except OSError:
            raise ValueError(f'無法讀取{label}原始圖片，請檢查檔案位置與權限。') from None
        if len(data) > MAX_ASSET_BYTES:
            raise ValueError(f'{label}原始圖片超過 64 MiB 上限。')
        total += len(data)
        if total > MAX_TOTAL_ASSET_BYTES:
            raise ValueError('原始圖片合計超過 192 MiB 上限。')
        image_format, dimensions = _inspect_image(data, kind)
        member = f'assets/{kind}{IMAGE_EXTENSIONS[image_format]}'
        assets[kind] = {'member': member, 'original_name': source.name, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'format': image_format, 'size': dimensions}
        payloads[member] = data
    return assets, payloads


def _materialize(assets, payloads, destination):
    folder = Path(destination) / 'assets'
    folder.mkdir()
    paths = {}
    for kind in ASSET_LABELS:
        asset = assets[kind]
        if asset is None:
            paths[kind] = None
            continue
        extension = IMAGE_EXTENSIONS[asset['format']]
        output = folder / f'{kind}{extension}'
        with output.open('xb') as stream:
            stream.write(payloads[asset['member']])
        paths[kind] = str(output)
    return paths


def save_project(path, paths, options, ui_state=None, animations=None):
    """Atomically snapshot raw artwork/settings; earlier files survive failures.

    `animations` is the animation set; without it the clips chosen by
    `options` are stored as one animation each.
    """
    options = _option_snapshot(options)
    state = _ui_snapshot(ui_state)
    records = _animation_snapshot(animations, options)
    assets, payloads = _collect_sources(paths)
    # Validate exactly the bytes being archived, rather than rereading source
    # paths that could be moved or changed during the save operation.
    with tempfile.TemporaryDirectory(prefix='spturn-validate-') as temporary:
        staged_paths = _materialize(assets, payloads, temporary)
        _validate_content(staged_paths, options, records)
    manifest = {'format': PROJECT_FORMAT, 'schema_version': SCHEMA_VERSION,
        'application_version': APPLICATION_VERSION, 'options': asdict(options), 'ui_state': state,
        'animations': records, 'assets': assets}
    encoded = json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError('編輯檔的設定資料過大。')
    destination = Path(path).resolve()
    if destination.is_dir():
        raise ValueError('請選擇編輯檔檔名，不是資料夾。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(prefix=f'.{destination.name}.', suffix='.tmp', dir=destination.parent)
    os.close(descriptor)
    staging = Path(staging_name)
    try:
        with zipfile.ZipFile(staging, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=False) as archive:
            archive.writestr('manifest.json', encoded)
            for member, data in payloads.items():
                archive.writestr(member, data)
        with staging.open('r+b') as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, destination)
    except OSError:
        raise ValueError('無法儲存編輯檔；原有檔案已保留。請檢查目的位置與磁碟空間。') from None
    finally:
        staging.unlink(missing_ok=True)
    return {'path': str(destination), 'format': PROJECT_FORMAT, 'schema_version': SCHEMA_VERSION,
        'asset_count': sum(asset is not None for asset in assets.values()), 'bytes': destination.stat().st_size}


def _safe_member(info):
    name = info.filename
    candidate = name[:-1] if info.is_dir() else name
    parts = candidate.split('/')
    if not candidate or len(name) > 128 or '\\' in name or ':' in name or name.startswith('/') or any(part in ('', '.', '..') for part in parts):
        raise ValueError('編輯檔包含不安全的素材路徑。')
    if PurePosixPath(candidate).is_absolute() or stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError('編輯檔包含不支援的素材連結。')
    if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ValueError('編輯檔使用不支援的壓縮或加密方式。')


def _read_archive(path):
    source = Path(path).resolve()
    try:
        if not source.is_file():
            raise ValueError('找不到指定的工具編輯檔。')
        if source.stat().st_size > MAX_PROJECT_BYTES:
            raise ValueError('工具編輯檔超過大小上限。')
        with zipfile.ZipFile(source, 'r') as archive:
            entries = archive.infolist()
            if len(entries) > 8 or len({entry.filename for entry in entries}) != len(entries):
                raise ValueError('編輯檔包含過多或重複的素材。')
            for entry in entries:
                _safe_member(entry)
            names = {entry.filename for entry in entries if not entry.is_dir()}
            if 'manifest.json' not in names:
                raise ValueError('這不是有效的工具編輯檔（.spturn）。')
            if archive.getinfo('manifest.json').file_size > MAX_MANIFEST_BYTES:
                raise ValueError('編輯檔的設定資料過大。')
            manifest = json.loads(archive.read('manifest.json').decode('utf-8'),
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError('編輯檔不可包含非有限數值。')))
            if not isinstance(manifest, dict) or manifest.get('format') != PROJECT_FORMAT:
                raise ValueError('這不是有效的工具編輯檔（.spturn）。')
            if type(manifest.get('schema_version')) is not int or manifest['schema_version'] != SCHEMA_VERSION:
                raise ValueError('此編輯檔版本尚未支援，請更新工具後再開啟。')
            options = _option_snapshot(manifest.get('options'))
            state = _ui_snapshot(manifest.get('ui_state'))
            animations = _animation_snapshot(manifest.get('animations'), options)
            assets = manifest.get('assets')
            if not isinstance(assets, dict) or not assets.get('front') or set(assets) != set(ASSET_LABELS):
                raise ValueError('編輯檔缺少完整的素材清單或正面圖片。')
            payloads, used, total = {}, {'manifest.json'}, 0
            for kind, asset in assets.items():
                if asset is None:
                    continue
                if not isinstance(asset, dict) or not isinstance(asset.get('member'), str):
                    raise ValueError('編輯檔的素材清單無效。')
                member = asset['member']
                if member not in names or not member.startswith('assets/'):
                    raise ValueError(f'編輯檔缺少{ASSET_LABELS[kind]}素材。')
                info = archive.getinfo(member)
                if info.file_size > MAX_ASSET_BYTES or type(asset.get('bytes')) is not int or asset['bytes'] != info.file_size:
                    raise ValueError('編輯檔的素材大小無效或超過上限。')
                total += info.file_size
                if total > MAX_TOTAL_ASSET_BYTES:
                    raise ValueError('編輯檔的素材合計超過大小上限。')
                data = archive.read(member)
                if len(data) != asset['bytes'] or hashlib.sha256(data).hexdigest() != asset.get('sha256'):
                    raise ValueError(f'編輯檔的{ASSET_LABELS[kind]}素材已損毀。')
                image_format, _ = _inspect_image(data, kind)
                if asset.get('format') != image_format:
                    raise ValueError('編輯檔記錄的圖片格式與素材不符。')
                payloads[member] = data
                used.add(member)
            if names != used:
                raise ValueError('編輯檔包含未列入素材清單的檔案。')
            return source, manifest, assets, payloads, options, state, animations
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError('工具編輯檔內容不完整或已損毀。') from None
    except OSError:
        raise ValueError('無法讀取工具編輯檔，請檢查檔案位置與權限。') from None


@dataclass
class LoadedProject:
    paths: dict
    options: core.TurnOptions
    ui_state: dict
    metadata: dict
    workspace_dir: str
    _temporary: tempfile.TemporaryDirectory
    closed: bool = False
    animations: list = field(default_factory=list)

    def close(self):
        if not self.closed:
            self._temporary.cleanup()
            self.closed = True

    cleanup = close

    def __enter__(self):
        if self.closed:
            raise ValueError('此編輯檔的暫存素材已關閉。')
        return self

    def __exit__(self, *args):
        self.close()


def load_project(path, workspace_dir=None):
    """Validate then open an owned temporary image workspace; caller keeps it alive."""
    source, manifest, assets, payloads, options, state, animations = _read_archive(path)
    temporary = tempfile.TemporaryDirectory(prefix='spturn-project-', dir=workspace_dir, ignore_cleanup_errors=True)
    try:
        paths = _materialize(assets, payloads, temporary.name)
        _validate_content(paths, options, animations)
        metadata = _json_copy(manifest, '編輯檔資訊')
        metadata['project_path'] = str(source)
        return LoadedProject(paths, options, state, metadata, temporary.name, temporary,
                             animations=animations)
    except BaseException:
        temporary.cleanup()
        raise
