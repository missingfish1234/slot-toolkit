"""Optional local regression inputs are not distributed with source checkouts."""
from pathlib import Path


def require_historical_files(test_case, paths):
    missing = [str(path) for path in map(Path, paths) if not path.is_file()]
    if missing:
        test_case.skipTest('Local historical fixture not distributed with source checkout; missing: '
                           + ', '.join(missing[:3]))


def require_historical_packages(test_case, folders):
    """Require each old skeleton and the exact image inputs read by its test.

    Only missing inputs skip. Existing malformed JSON/images still reach the
    original parser and assertions, so a broken fixture is not called a pass.
    """
    folders = [Path(folder) for folder in folders]
    required = [folder / name for folder in folders for name in
                ('manifest.json', 'images/front.png', 'images/back.png', 'images/edge.png')]
    require_historical_files(test_case, required)
    for folder in folders:
        if not any(path.name != 'manifest.json' for path in folder.glob('*.json')):
            test_case.skipTest('Local historical fixture not distributed with source checkout; '
                               f'missing skeleton JSON: {folder}')
