"""Run the actual Pyodide worker, with public synthetic photos and no API server.

Set TT_STATIC_SITE to a prepare_static.py --download-runtime build directory.
"""
from io import BytesIO
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
import urllib.request
import pytest
from PIL import Image
from test_web_e2e import browser

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.getenv('TT_STATIC_SITE'),reason='static runtime build not supplied')]


@pytest.fixture(scope='module')
def static_site():
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    proc=subprocess.Popen([sys.executable,'-m','http.server',str(port),'--bind','127.0.0.1','--directory',os.environ['TT_STATIC_SITE']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(60):
            try:urllib.request.urlopen(url,timeout=1);break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Static test server did not start')
        yield url
    finally:proc.terminate();proc.wait(timeout=10)


def test_real_worker_named_photo_and_bulk_start(static_site,browser):
    from test_reader import _shot
    data,deal,_=_shot(11)
    page=browser.new_page(viewport={'width':390,'height':760});requests=[];errors=[]
    page.on('request',lambda r:requests.append(r.url));page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(static_site);page.wait_for_selector('#editBoard .c',timeout=90000)
    page.set_input_files('#photo',{'name':'screen.png','mimeType':'image/png','buffer':data})
    page.wait_for_function("document.querySelector('#photoNote').textContent.includes('Read in')",timeout=90000)
    assert 'Board ready' in page.inner_text('#msg')
    tokens=page.evaluate('setup.board')
    named=[(got,want) for got,want in zip(tokens,deal.tableau) if got not in ('?', '--')]
    assert named and all(got==want for got,want in named)
    assert all((got=='--')==(want=='--') for got,want in zip(tokens,deal.tableau))
    assert page.locator('#editBoard .back').count()>=18
    # One confirmation starts the existing unknown-stock session; missing ranks remain reveals.
    if page.inner_text('#wasteBtn')=='?':
        page.click('#wasteBtn');page.click(f'#keys [data-k="{deal.waste}"]')
    page.click('#startBtn');page.wait_for_selector('#board .c',timeout=30000)
    assert not [r for r in requests if '/api/' in r]
    assert not errors
    page.close()


def test_real_worker_refresh_and_undo(static_site,browser):
    page=browser.new_page();page.goto(static_site);page.wait_for_selector('#editBoard .c',timeout=90000)
    page.click('summary:has-text("Paste the board")');page.fill('#paste',' '.join(['2']+['--']*27));page.click('#pasteBtn')
    page.click('#wasteBtn');page.click('#keys [data-k="A"]');page.click('#startBtn');page.wait_for_selector('#board .c')
    page.click('#drawBtn');page.click('#keys [data-k="3"]');page.wait_for_function("document.querySelector('#stk').textContent==='23'")
    page.reload();page.wait_for_selector('#board .c',timeout=90000)
    assert page.inner_text('#stk')=='23' and page.inner_text('#wst')=='3'
    page.click('#undoBtn');page.wait_for_function("document.querySelector('#stk').textContent==='24'")
    page.reload();page.wait_for_selector('#board .c',timeout=90000)
    assert page.inner_text('#stk')=='24' and page.inner_text('#wst')=='A'
    page.close()


def test_real_browser_heic_decode(static_site,browser):
    import pillow_heif
    out=BytesIO();pillow_heif.from_pillow(Image.new('RGB',(320,240),'beige')).save(out,quality=90)
    page=browser.new_page();page.goto(static_site);page.wait_for_selector('#editBoard .c',timeout=90000)
    page.set_input_files('#photo',{'name':'phone.HEIC','mimeType':'image/heic','buffer':out.getvalue()})
    page.wait_for_function("document.querySelector('#photoNote').textContent.includes('Read in')",timeout=90000)
    assert 'Layout uncertain' in page.inner_text('#msg')
    page.close()
