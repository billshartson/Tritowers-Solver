"""Replay exact local image bytes and TTPhoto.normalize output in Python and Pyodide.

See tools/REPLAY-PHOTOS.md. Reports contain hashes/counts, never images or ranks.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import prepare_static

RANKS = set('A 2 3 4 5 6 7 8 9 10 J Q K'.split())
MAX_BYTES = 60 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def records(path):
    document = json.loads(Path(path).read_text())
    entries = document['photos'] if isinstance(document, dict) else document
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError('Manifest and labels must contain a list of photo objects')
    return entries


def load_cases(paths=(), manifest=None, labels=None):
    """Verify every requested digest before any decoding or recognition occurs."""
    if bool(paths) == bool(manifest):
        raise ValueError('Supply image paths or --manifest, not both')
    entries = ([{'path': Path(path)} for path in paths] if paths else
               [{**entry, 'path': Path(manifest).resolve().parent / entry['image']}
                for entry in records(manifest)])
    if not entries:
        raise ValueError('At least one image is required')
    labelled = {}
    if labels:
        for entry in records(labels):
            path = (Path(labels).resolve().parent / entry['image']).resolve()
            board = entry['board'].split() if isinstance(entry['board'], str) else entry['board']
            if len(board) != 28 or any(card not in RANKS | {'?', '--'} for card in board):
                raise ValueError('Labels require 28 valid board tokens')
            waste = entry['waste']
            if waste not in RANKS | {'?', ''}:
                raise ValueError('Labels require a valid waste token')
            truth = {f'board-{i}': card for i, card in enumerate(board, 1)}
            truth['waste'] = waste or '?'
            stock = entry.get('stock_with_joker', entry.get('stock'))
            if stock is not None:
                stock = stock.split() if isinstance(stock, str) else list(stock)
                stock = ['*' if card == 'JOKER' else card for card in stock]
                if len(stock) == 23:
                    stock.append('*')
                if len(stock) != 24 or stock[-1] != '*' or any(card not in RANKS for card in stock[:-1]):
                    raise ValueError('Full-deal labels require 23 normal stock ranks and the final joker')
                if Counter(board + [waste] + stock[:-1]) != Counter({rank: 4 for rank in RANKS}):
                    raise ValueError('Full-deal labels must contain four of each normal rank')
                truth.update({f'stock-{i}': card for i, card in enumerate(stock, 1)})
            labelled[path] = truth
    result = []
    for index, entry in enumerate(entries, 1):
        path = entry['path'].resolve()
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(f'Case {index} exceeds 60 MB')
        data = path.read_bytes()
        digest = sha256(data)
        if 'sha256' in entry and not re.fullmatch(r'[0-9a-fA-F]{64}', str(entry['sha256'])):
            raise ValueError(f'Case {index}: expected SHA-256 must contain 64 hexadecimal digits')
        if entry.get('sha256') and entry['sha256'].lower() != digest:
            raise ValueError(f'Case {index}: SHA-256 mismatch; no images were replayed')
        result.append({'data': data, 'sha256': digest, 'truth': labelled.get(path)})
    if labels and any(case['truth'] is None for case in result):
        raise ValueError('Every selected image needs a matching labels entry')
    return result


def slots(response):
    output = {f'board-{i}': token for i, token in enumerate(response.get('board', []), 1)}
    if 'waste' in response:
        output['waste'] = response['waste'] or '?'
    if isinstance(response.get('stock'), list):
        output.update({f'stock-{i}': token for i, token in enumerate(response['stock'], 1)})
    return output


def metrics(response, truth=None):
    """Only aggregate API-visible values; '?' does not distinguish covered/unread."""
    tokens = slots(response)
    values = list(tokens.values())
    result = {'ok': bool(response.get('ok')), 'trusted': bool(response.get('trusted')),
              'layout': response.get('mode', 'error'), 'slot_count': len(tokens),
              'state_counts': {'named': sum(v in RANKS for v in values),
                               'unknown_or_covered': sum(v in ('?', '') for v in values),
                               'empty': values.count('--'), 'inferred_joker': values.count('*')},
              'review_count': len(response.get('review', []))}
    if truth is not None:
        known = {key: value for key, value in truth.items() if value in RANKS}
        result['accuracy'] = {
            'expected_named': len(known),
            'correct': sum(tokens.get(key) == value for key, value in known.items()),
            'wrong': sum(tokens.get(key) in RANKS and tokens[key] != value for key, value in known.items()),
            'abstain': sum(tokens.get(key) not in RANKS for key in known),
            'false_named_on_empty_or_covered': sum(tokens.get(key) in RANKS for key, value in truth.items() if value in ('?', '--')),
            'false_empty': sum(tokens.get(key) == '--' and value != '--' for key, value in truth.items()),
            'all_labelled_tokens_match': all(tokens.get(key) == value for key, value in truth.items()),
        }
    return result


def parity(left, right):
    a, b = slots(left), slots(right)
    return {'same_tokens': a == b, 'different_slots': sum(a.get(k) != b.get(k) for k in a.keys() | b.keys()),
            'same_layout': left.get('mode') == right.get('mode'),
            'same_trusted': bool(left.get('trusted')) == bool(right.get('trusted'))}


def native_read(data, truth):
    from web_shared import photo_response
    started = time.perf_counter()
    response = photo_response(data)
    return response, {**metrics(response, truth), 'seconds': round(time.perf_counter() - started, 4)}


def identity(site):
    with ZipFile(site / 'app.zip') as archive:
        sources = {name: sha256(archive.read(name)) for name in archive.namelist()}
    assets = {str(path.relative_to(site)): sha256(path.read_bytes())
              for path in sorted(site.rglob('*')) if path.is_file()}
    loader = (site / 'pyodide/pyodide.mjs').read_text()
    declared = re.findall(r'\b(?:var|let|const)\s+\w+\s*=\s*[\"\'](\d+\.\d+\.\d+)[\"\'];', loader)
    if prepare_static.PYODIDE_VERSION not in declared:
        raise ValueError('Cached runtime loader does not declare the pinned Pyodide version')
    lock = json.loads((site / 'pyodide/pyodide-lock.json').read_text())
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    versions = {'python': platform.python_version()}
    for package in ('numpy', 'Pillow', 'opencv-python-headless', 'pillow-heif', 'playwright'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {'git_commit': commit, 'native_versions': versions,
            'runtime': {'pyodide': prepare_static.PYODIDE_VERSION, **lock['info'],
                        'packages': {name: lock['packages'][name]['version'] for name in ('numpy', 'pillow', 'opencv-python')}},
            'source_sha256': sources, 'asset_sha256': assets,
            'replay_tool_sha256': sha256(Path(__file__).read_bytes())}


@contextmanager
def serve(site):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def bounded(script, timeout_ms=120000):
    """page.evaluate has no default deadline; close the context after any stall."""
    return f"""async input => {{let timer;try{{return await Promise.race([
      ({script})(input),new Promise((resolve,reject)=>{{timer=setTimeout(()=>reject(new Error('replay_deadline')), {timeout_ms})}})
    ])}}finally{{clearTimeout(timer)}}}}"""


NORMALIZE_JS = bounded("""async encoded => {
  const file=new File([Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))], 'input.bin');
  const start=performance.now(),blob=await TTPhoto.normalize(file);
  const seconds=(performance.now()-start)/1000;
  const encodedOutput=await new Promise((resolve,reject)=>{const reader=new FileReader();
    reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)});
  const image=await createImageBitmap(blob),dimensions=[image.width,image.height];image.close();
  return {encoded:encodedOutput,seconds,dimensions};
}""")
READ_JS = bounded("""async encoded => {
  const data=new FormData();data.append('file',new Blob([Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))]),'input.bin');
  const start=performance.now();
  const response=await (await fetch('/api/photo',{method:'POST',body:data})).json();
  return {response,seconds:(performance.now()-start)/1000};
}""")


def run(cases, runtime=None, download=False, chromium=None):
    """Fresh build and per-case browser contexts; each bridge response is awaited."""
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='tritowers-replay-') as temporary:
        site = prepare_static.stage(Path(temporary) / 'site', runtime=runtime, download=download)
        # Reuse only the already-downloaded public HEIC codec when a cache has it.
        if runtime and (Path(runtime).parent / 'web/vendor/heic-to.js').is_file():
            vendor = site / 'web/vendor'
            vendor.mkdir(parents=True)
            for name in ('heic-to.js', 'HEIC-LICENSE'):
                source = Path(runtime).parent / 'web/vendor' / name
                if source.is_file():
                    shutil.copy2(source, vendor / name)
            worker = site / 'web/heic-worker.js'
            worker.write_text(worker.read_text().replace(prepare_static.HEIC_URL, '/web/vendor/heic-to.js'))
        build = identity(site)
        report = {'schema_version': 1, 'identity': build,
                  'state_scope': 'API-visible tokens: covered and unread ranks both appear as unknown_or_covered.',
                  'timing_scope': 'Native calls share one process. Each case uses a fresh browser context and warmed worker; startup and TTPhoto normalization are timed separately. Worker timings include adapter response/overlay serialization.',
                  'normalization': 'Unmodified TTPhoto.normalize: EXIF orientation, maximum side 1600, canvas JPEG quality 0.94.',
                  'cases': []}
        with serve(site) as url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(**({'executable_path': chromium} if chromium else {}))
            report['identity']['browser_version'] = browser.version
            try:
                for index, case in enumerate(cases, 1):
                    record = {'case': index, 'original': {'sha256': case['sha256'], 'bytes': len(case['data'])}, 'reads': {}}
                    report['cases'].append(record)
                    context = browser.new_context(viewport={'width': 390, 'height': 760})
                    # Only public build files are served. Photo bytes go through the local bridge.
                    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
                    page = context.new_page()
                    network_api = []
                    page.on('request', lambda request: network_api.append(1) if '/api/' in request.url else None)
                    page.set_default_timeout(120000)
                    try:
                        record['stage'] = 'native_original'
                        original_native, scored = native_read(case['data'], case['truth'])
                        record['reads']['original_native'] = scored
                        record['stage'] = 'worker_startup'
                        started = time.perf_counter()
                        page.goto(url)
                        page.wait_for_selector('#editBoard .c')
                        record['worker_startup_seconds'] = round(time.perf_counter() - started, 4)
                        encoded = base64.b64encode(case['data']).decode('ascii')
                        record['stage'] = 'browser_normalization'
                        prepared = page.evaluate(NORMALIZE_JS, encoded)
                        normalized = base64.b64decode(prepared['encoded'])
                        record['normalized'] = {'sha256': sha256(normalized), 'bytes': len(normalized),
                                                'dimensions': prepared['dimensions'], 'seconds': round(prepared['seconds'], 4)}
                        responses = {}
                        for variant, data, browser_data in (('original', case['data'], encoded), ('normalized', normalized, prepared['encoded'])):
                            record['stage'] = variant + '_native'
                            native = original_native
                            if variant != 'original':
                                native, scored = native_read(data, case['truth'])
                                record['reads'][variant + '_native'] = scored
                            record['stage'] = variant + '_worker'
                            got = page.evaluate(READ_JS, browser_data)
                            responses[variant] = (native, got['response'])
                            record['reads'][variant + '_worker'] = {**metrics(got['response'], case['truth']), 'seconds': round(got['seconds'], 4)}
                        record['parity'] = {variant: parity(*pair) for variant, pair in responses.items()}
                        record['normalization_changes'] = {engine: parity(responses['original'][i], responses['normalized'][i]) for i, engine in enumerate(('native', 'worker'))}
                        record.pop('stage')
                    except Exception as error:
                        record['error_type'] = type(error).__name__
                    finally:
                        record['network_api_requests'] = len(network_api)
                        context.close()
            finally:
                browser.close()
        report['source_unchanged_during_run'] = all(sha256((ROOT / name).read_bytes()) == digest for name, digest in build['source_sha256'].items())
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='*', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--labels', type=Path)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--runtime', type=Path, help='Cached prepare_static build/pyodide directory')
    choice.add_argument('--download-runtime', action='store_true')
    parser.add_argument('--chromium', help='Optional installed Chromium/Chrome executable')
    parser.add_argument('--output', type=Path, help='Write aggregate JSON here instead of stdout')
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.images, args.manifest, args.labels)
        report = run(cases, args.runtime, args.download_runtime, args.chromium)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    content = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(content)
    else:
        print(content, end='')
    failed = not report['source_unchanged_during_run'] or any(case.get('error_type') or case['network_api_requests'] or any(not read['ok'] for read in case['reads'].values()) for case in report['cases'])
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
