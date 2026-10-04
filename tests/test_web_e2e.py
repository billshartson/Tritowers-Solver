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
    assert "Stock left" in page.inner_text("main") and page.inner_text("#stk") == "24"
    # board fits the viewport: every card inside the page width
    width = page.evaluate("document.documentElement.clientWidth")
    for box in page.locator("#board .c").evaluate_all("els=>els.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.right]})"):
        assert box[0] >= 0 and box[1] <= width + 1
    page.click("#recBtn"); page.wait_for_selector("#adv:not([hidden])", timeout=40000)
    assert "estimate" in page.inner_text("#adv") or "Proven" in page.inner_text("#adv")
    assert page.locator("#board .c.rec").count() == 1
    page.click("#board .c.rec"); page.wait_for_function("document.getElementById('rem').textContent==='27'")
    page.click("#drawBtn"); page.click('#keys button[data-k="4"]'); page.wait_for_function("document.getElementById('stk').textContent==='23'")
    page.click("#undoBtn"); page.wait_for_function("document.getElementById('stk').textContent==='24'")
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
    page.wait_for_function("document.getElementById('stk').textContent==='23'", timeout=20000)
    assert fails["n"] == 2 and page.inner_text("#stk") == "23"      # retried, applied exactly once

@pytest.mark.skipif(not (PHOTO and TEMPLATES and os.path.exists(PHOTO)), reason="private photo/templates not provided")
def test_photo_full_frame_default(server, browser):
    page = browser.new_page(viewport=VIEWPORTS["phone"]); page.goto(server); page.wait_for_selector("#editBoard .c")
    page.set_input_files("#photo", PHOTO); page.wait_for_function("document.getElementById('photoNote').textContent.length>0", timeout=60000)
    assert "prototype" in page.inner_text("#photoNote")


@pytest.mark.parametrize("vp", VIEWPORTS)
def test_complete_deal_mode_never_guesses(server, browser, vp):
    page = browser.new_page(viewport=VIEWPORTS[vp]); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(server); page.wait_for_selector("#editBoard .c")
    page.click("#modeDeal"); assert page.is_visible("#solveBtn") and not page.is_visible("#startBtn")
    page.click("#solveBtn"); page.wait_for_selector("#solBanner")
    page.wait_for_function("document.getElementById('solBanner').textContent.includes('not complete')", timeout=15000)
    assert "will not guess" in page.inner_text("#solBanner") and not page.is_visible("#solBody")
    page.click("#solEdit"); page.click("#soAdd"); page.click('#keys button[data-k="7"]')
    assert page.locator("#soChips .chip").count() == 1 and not errs
    page.close()


@pytest.mark.parametrize("vp", ["desktop", "phone"])
def test_impossible_deck_is_flagged_before_start(server, browser, vp):
    """Seven 8s and five Qs must be caught on the setup screen, with a clear message, and Start must not run."""
    ctx = browser.new_context(viewport=VIEWPORTS[vp]); page = ctx.new_page()
    posts = []; page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/api/new" in r.url else None)
    page.goto(server); page.wait_for_selector("#editBoard .c")
    page.click("summary:has-text('Paste the board')")
    page.fill("#paste", "2 7 10 Q Q Q 8 9 9 2 K J 8 Q 3 Q 8 8 6 5 8 A 7 8 8 5 7 7")
    page.click("#pasteBtn")
    page.click("#wasteBtn"); page.click('#keys button[data-k="A"]')
    warn = page.locator("#deckWarn"); warn.wait_for(state="visible")
    assert "8 x7" in warn.inner_text() and "Q x5" in warn.inner_text()
    page.click("#startBtn")
    assert "Impossible deck" in page.locator("#msg").inner_text()
    page.wait_for_timeout(300); assert posts == [] and page.locator("#board .c").count() == 0
    page.fill("#paste", " ".join(["?"] * 28)); page.click("#pasteBtn")
    page.wait_for_selector("#deckWarn", state="hidden")
    ctx.close()


def test_start_survives_a_40_second_outage(server, browser):
    """Start must keep retrying through a ~40 s full outage (530s) and then work, with honest progress text."""
    ctx = browser.new_context(viewport=VIEWPORTS["phone"]); page = ctx.new_page()
    t0 = time.time(); seen = []
    def handler(route):
        if time.time() - t0 < 40:
            seen.append(1); route.fulfill(status=530, body="error code: 1033")
        else: route.continue_()
    page.goto(server); page.wait_for_selector("#editBoard .c")
    page.click("#wasteBtn"); page.click('#keys button[data-k="K"]')
    t0 = time.time(); page.route("**/api/new", handler)
    page.click("#startBtn")
    page.wait_for_function("document.querySelector('#msg').textContent.includes('still trying')", timeout=15000)
    assert page.locator("#startBtn").inner_text().startswith("Starting")
    page.wait_for_selector("#board .c", timeout=90000)
    assert len(seen) >= 5 and "Could not reach" not in page.locator("#msg").inner_text()
    ctx.close()
