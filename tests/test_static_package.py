from pathlib import Path
from zipfile import ZipFile
import subprocess
import sys
from tools.prepare_static import stage


def test_static_bundle_has_only_public_runtime_and_imports(tmp_path):
    dest=stage(tmp_path/'site')
    with ZipFile(dest/'app.zip') as archive:
        names=archive.namelist()
        assert 'web_core.py' in names and 'web_shared.py' in names
        assert 'tritowers_vision/automatic.py' in names
        assert 'tritowers_vision/full_deal.py' in names
        assert 'tritowers_vision/data/font_glyphs.npz' in names
        assert not any('local/' in n or n.endswith(('.jpg','.HEIC','.json')) for n in names)
        archive.extractall(tmp_path/'app')
    # Import from the archive extraction, outside the checkout, catches missed dependencies.
    result=subprocess.run([sys.executable,'-c','import web_core; from tritowers_vision.intake import read_photo; assert web_core.api_geo()["geo"]'],cwd=tmp_path/'app',capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    html=(dest/'index.html').read_text()
    assert '/tt-bridge.js' in html and '/web/photo-input.js' in html
    assert (dest/'pw.js').exists() and (dest/'web/heic-worker.js').exists()
