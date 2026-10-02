"""Browser end-to-end tests for web_app.py (real Chromium via Playwright, local server)."""
import os, socket, subprocess, sys, time
from pathlib import Path
import pytest
pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get("TT_CHROME") or ("/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None)
PHOTO = os.environ.get("TT_TEST_PHOTO")          # optional private photo, never committed
TEMPLATES = os.environ.get("TT_TEMPLATES")

@pytest.fixture(scope="module")
def server():
    if os.environ.get("TT_BASE_URL"):          # post-deploy run against a live URL
        yield os.environ["TT_BASE_URL"].rstrip("/"); return
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    p = subprocess.Popen([sys.executable, "web_app.py"], cwd=ROOT, env={**os.environ, "PORT": str(port)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    import urllib.request
    for _ in range(60):
        try: urllib.request.urlopen(url + "/health", timeout=1); break
        except Exception: time.sleep(0.25)
    else: p.kill(); raise RuntimeError("server did not start")
    yield url
    p.kill()

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME) if CHROME else pw.chromium.launch()
        yield b; b.close()

VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 760}}

def start_game(page, url, waste="K"):
    page.goto(url); page.wait_for_selector("#editBoard .c")
    page.click("#wasteBtn"); page.click(f'#keys button[data-k="{waste}"]')
    page.click("#startBtn"); page.wait_for_selector("#board .c")

def reveal_all(page, ranks="2 A 3 7 9 J 5 3 9 3".split()):
    for r in ranks:
        n = page.locator("#board .c.ask").count()
        page.click("#board .c.ask >> nth=0"); page.click(f'#keys button[data-k="{r}"]')
        page.wait_for_function(f"document.querySelectorAll('#board .c.ask').length<{n}", timeout=30000)

@pytest.mark.parametrize("vp", VIEWPORTS)
def test_full_flow(server, browser, vp):
    ctx = browser.new_context(viewport=VIEWPORTS[vp]); page = ctx.new_page()
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    start_game(page, server)
    assert page.locator("#board .c.ask").count() == 10          # bottom row asks for ranks
    assert page.locator("#recBtn").is_disabled()
    reveal_all(page)
    page.wait_for_function("document.querySelectorAll('#board .c.ask').length==0")
    assert "Stock left" in page.inner_text("main") and page.inner_text("#stk") == "23"
    # board fits the viewport: every card inside the page width
    width = page.evaluate("document.documentElement.clientWidth")
    for box in page.locator("#board .c").evaluate_all("els=>els.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.right]})"):
        assert box[0] >= 0 and box[1] <= width + 1
    page.click("#recBtn"); page.wait_for_selector("#adv:not([hidden])", timeout=40000)
    assert "estimate" in page.inner_text("#adv") or "Proven" in page.inner_text("#adv")
    assert page.locator("#board .c.rec").count() == 1
    page.click("#board .c.rec"); page.wait_for_function("document.getElementById('rem').textContent==='27'")
    page.click("#drawBtn"); page.click('#keys button[data-k="4"]'); page.wait_for_function("document.getElementById('stk').textContent==='22'")
    page.click("#undoBtn"); page.wait_for_function("document.getElementById('stk').textContent==='23'")
    assert not errors and "Error" not in page.inner_text("main")
    ctx.close()

def test_input_errors_are_inline_not_toasts(server, browser):
    page = browser.new_page(viewport=VIEWPORTS["phone"]); page.goto(server); page.wait_for_selector("#editBoard .c")
    page.click("#startBtn"); assert "waste card" in page.inner_text("#msg").lower()
    assert page.locator("#msg.err").count() == 1
    start_game(page, server); page.click("#board .c.ask >> nth=0"); page.click('#sheetX')
    page.click("#board .c.back >> nth=0"); assert "face-down" in page.inner_text("#msg")

def test_refresh_resumes_game(server, browser):
    page = browser.new_page(viewport=VIEWPORTS["desktop"]); start_game(page, server); reveal_all(page)
    page.reload(); page.wait_for_selector("#board .c"); assert page.inner_text("#wst") == "K" and page.locator("#play").is_visible() and page.locator("#setup").is_hidden()

def test_survives_dropped_requests(server, browser):
    page = browser.new_page(viewport=VIEWPORTS["phone"]); start_game(page, server); reveal_all(page)
    fails = {"n": 0}
    def flaky(route):
        if fails["n"] < 2: fails["n"] += 1; route.abort()
        else: route.continue_()
    page.route("**/api/act", flaky)
    page.click("#drawBtn"); page.click('#keys button[data-k="4"]')
    page.wait_for_function("document.getElementById('stk').textContent==='22'", timeout=20000)
    assert fails["n"] == 2 and page.inner_text("#stk") == "22"      # retried, applied exactly once

@pytest.mark.skipif(not (PHOTO and TEMPLATES and os.path.exists(PHOTO)), reason="private photo/templates not provided")
def test_photo_full_frame_default(server, browser):
    page = browser.new_page(viewport=VIEWPORTS["phone"]); page.goto(server); page.wait_for_selector("#editBoard .c")
    page.set_input_files("#photo", PHOTO); page.wait_for_function("document.getElementById('photoNote').textContent.length>0", timeout=60000)
    assert "prototype" in page.inner_text("#photoNote")
