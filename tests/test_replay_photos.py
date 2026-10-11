"""Opt-in exact-byte replay: hashes, private-output boundaries and real worker sequencing."""
import json
import os
import shutil
import subprocess
from pathlib import Path
import pytest
from tools import replay_photos as replay


def test_manifest_mismatch_is_rejected_before_any_replay(tmp_path, monkeypatch):
    (tmp_path / 'one.jpg').write_bytes(b'first exact image')
    (tmp_path / 'two.jpg').write_bytes(b'second exact image')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'photos': [
        {'image': 'one.jpg', 'sha256': replay.sha256(b'first exact image')},
        {'image': 'two.jpg', 'sha256': '0' * 64},
    ]}))
    def forbidden(*args, **kwargs):
        pytest.fail('No recognition may run after a manifest mismatch')
    monkeypatch.setattr(replay, 'run', forbidden)
    with pytest.raises(SystemExit) as error:
        replay.main(['--manifest', str(manifest), '--runtime', str(tmp_path)])
    assert error.value.code == 2



def test_empty_expected_hash_cannot_silently_disable_verification(tmp_path):
    (tmp_path / 'one.jpg').write_bytes(b'exact bytes')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'photos': [{'image': 'one.jpg', 'sha256': ''}]}))
    with pytest.raises(ValueError, match='64 hexadecimal'):
        replay.load_cases(manifest=manifest)


def test_labels_only_score_and_reports_never_include_ranks_or_imagery(tmp_path):
    source = tmp_path / 'private-name.jpg'
    source.write_bytes(b'exact jpeg bytes')
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps([{'image': source.name, 'board': ['--'] * 27 + ['K'], 'waste': 'Q'}]))
    case = replay.load_cases([source], labels=labels)[0]
    assert case['data'] == b'exact jpeg bytes'
    response = {'ok': True, 'mode': 'tableau', 'trusted': True, 'board': ['--'] * 27 + ['?'],
                'waste': 'J', 'review': ['28'], 'overlay': 'private-image-bytes', 'note': 'private-card-ranks'}
    result = replay.metrics(response, case['truth'])
    assert result['accuracy']['correct'] == 0
    assert result['accuracy']['wrong'] == 1 and result['accuracy']['abstain'] == 1
    assert result['state_counts'] == {'named': 1, 'unknown_or_covered': 1, 'empty': 27, 'inferred_joker': 0}
    serialized = json.dumps(result)
    assert all(value not in serialized for value in (source.name, 'private-image-bytes', 'private-card-ranks', '"K"', '"Q"', '"J"'))


def test_token_parity_detects_changed_values_even_when_counts_match():
    first = {'mode': 'tableau', 'trusted': True, 'board': ['A', '2'], 'waste': 'K'}
    second = {'mode': 'tableau', 'trusted': True, 'board': ['2', 'A'], 'waste': 'K'}
    assert replay.metrics(first) == replay.metrics(second)
    assert replay.parity(first, second) == {'same_tokens': False, 'different_slots': 2, 'same_layout': True, 'same_trusted': True}


@pytest.mark.browser
@pytest.mark.skipif(not os.getenv('TT_STATIC_SITE'), reason='Requires cached actual Pyodide runtime')
def test_fresh_worker_replays_each_exact_input_and_browser_normalization(tmp_path):
    from test_full_deal import make_grid
    labels = []
    paths = []
    for seed in (3, 17):
        image, truth = make_grid(seed)
        path = tmp_path / f'generated-{seed}.jpg'
        image.save(path, 'JPEG', quality=97)
        paths.append(path)
        labels.append({'image': path.name, **truth})
    label_path = tmp_path / 'labels.json'
    label_path.write_text(json.dumps(labels))
    cases = replay.load_cases(paths, labels=label_path)
    report = replay.run(cases, runtime=Path(os.environ['TT_STATIC_SITE']) / 'pyodide')
    assert report['source_unchanged_during_run']
    assert len(report['cases']) == 2
    for case, expected in zip(report['cases'], cases):
        assert 'error_type' not in case
        assert case['original']['sha256'] == expected['sha256']
        assert case['normalized']['sha256'] != expected['sha256']
        assert case['network_api_requests'] == 0
        assert set(case['reads']) == {'original_native', 'original_worker', 'normalized_native', 'normalized_worker'}
        for result in case['reads'].values():
            assert result['trusted'] and result['layout'] == 'full_deal'
            assert result['accuracy']['correct'] >= 30 and result['accuracy']['wrong'] == 0
    # Distinct known decks plus fresh contexts/awaited bridge responses catch
    # accidental reuse of the preceding photo's result, even at identical size.
    assert report['cases'][0]['original']['sha256'] != report['cases'][1]['original']['sha256']
    serialized = json.dumps(report)
    assert all(path.name not in serialized for path in paths)


def test_browser_evaluation_deadline_preserves_values_and_rejects_stalls():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed to exercise browser Promise deadlines')
    succeeds = replay.bounded('async value => value', timeout_ms=30)
    stalls = replay.bounded('async () => new Promise(() => {})', timeout_ms=30)
    script = f"""(async()=>{{
      if(await ({succeeds})(37)!==37)throw new Error('wrong result');
      try{{await ({stalls})(null);throw new Error('stall succeeded')}}
      catch(error){{if(error.message!=='replay_deadline')throw error}}
    }})().catch(error=>{{console.error(error);process.exitCode=1}})"""
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
