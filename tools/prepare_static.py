"""Build the existing static browser app; never deploy or contact the retired origin.

Only allowlisted public source and the open-font bank enter app.zip. Runtime
packages are pinned and downloaded only with --download-runtime, or copied from
an existing --runtime directory. No private bank, metadata or photos are used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
from urllib.request import urlopen
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PYODIDE_VERSION = '314.0.7'
RUNTIME_URL = f'https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/'
HEIC_URL = 'https://cdn.jsdelivr.net/npm/heic-to@1.5.2/dist/iife/heic-to.js'
MODULES = ('solver.py', 'solver_ui.py', 'tritowers_cli.py', 'web_core.py', 'web_shared.py')
VISION = ('__init__.py', 'image.py', 'reader.py', 'register.py', 'automatic.py', 'scene.py', 'glyphs.py', 'rank.py', 'rank2.py', 'layout.py', 'schema.py', 'recognizer.py', 'occupancy.py', 'annotation.py')
WEB = ('photo-input.js', 'heic-worker.js', 'tt-bridge.js', 'pw.js')


def _download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=90) as response, path.open('wb') as out:
        shutil.copyfileobj(response, out)


def download_runtime(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json'):
        _download(RUNTIME_URL + name, destination / name)
    lock = json.loads((destination / 'pyodide-lock.json').read_text())
    needed = set()
    def add(name):
        if name in needed: return
        needed.add(name)
        for dep in lock['packages'][name].get('depends', []): add(dep)
    for name in ('numpy', 'pillow', 'opencv-python'): add(name)
    for name in sorted(needed):
        package = lock['packages'][name]; path = destination / package['file_name']
        _download(RUNTIME_URL + package['file_name'], path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != package['sha256']:
            raise ValueError(f'Runtime package checksum mismatch: {name}')


def stage(destination, source=ROOT, runtime=None, download=False):
    destination, source = Path(destination).resolve(), Path(source).resolve()
    if destination == source or source in destination.parents:
        raise ValueError('Destination must be outside the checkout.')
    if destination.exists(): raise ValueError('Destination exists; choose a new directory.')
    destination.mkdir(parents=True)
    public = [*MODULES, *(f'tritowers_vision/{name}' for name in VISION), 'tritowers_vision/data/font_glyphs.npz']
    with ZipFile(destination / 'app.zip', 'w', ZIP_DEFLATED) as archive:
        for name in public:
            # automatic.py is required once the automatic reader ships.
            archive.write(source / name, name)
    (destination / 'web').mkdir()
    for name in WEB:
        shutil.copy2(source / 'web' / name, destination / 'web' / name)
    for name in ('tt-bridge.js', 'pw.js'):
        shutil.copy2(source / 'web' / name, destination / name)
    html = (source / 'web/index.html').read_text()
    html = html.replace('<title>', '<script src="/tt-bridge.js"></script><title>', 1)
    (destination / 'index.html').write_text(html)
    if runtime:
        shutil.copytree(runtime, destination / 'pyodide')
    elif download:
        download_runtime(destination / 'pyodide')
    if download:
        _download(HEIC_URL, destination / 'web/vendor/heic-to.js')
        worker = destination / 'web/heic-worker.js'
        worker.write_text(worker.read_text().replace(HEIC_URL, '/web/vendor/heic-to.js'))
        _download('https://cdn.jsdelivr.net/npm/heic-to@1.5.2/LICENSE', destination / 'web/vendor/HEIC-LICENSE')
    (destination / 'build.json').write_text(json.dumps({'pyodide': PYODIDE_VERSION, 'sources': public, 'sha256': hashlib.sha256((destination / 'app.zip').read_bytes()).hexdigest()}, indent=2))
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--download-runtime', action='store_true')
    args = parser.parse_args()
    print(stage(args.destination, runtime=args.runtime, download=args.download_runtime))
