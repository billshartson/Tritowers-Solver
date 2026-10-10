"""Photo UI intake, confirmation and race regressions without private fixtures."""
from io import BytesIO
import json
from PIL import Image
import pytest
from test_web_e2e import server, browser, VIEWPORTS

pytestmark=pytest.mark.browser


def photo():
    out=BytesIO();Image.new('RGB',(320,240),'beige').save(out,'JPEG')
    return {'name':'photo.jpg','mimeType':'image/jpeg','buffer':out.getvalue()}


def draft(rank='A'):
    return {'ok':True,'board':['?']*18+[rank]+['?']*9,'waste':'K','trusted':True,'review':['20'],'note':'Check the stock counter.'}


def open_page(browser,server):
    page=browser.new_page(viewport=VIEWPORTS['phone']);page.goto(server);page.wait_for_selector('#editBoard .c');return page


def test_photo_bulk_confirm_keeps_unknowns_and_corrections(server,browser):
    page=open_page(browser,server)
    page.route('**/api/photo',lambda route:route.fulfill(json=draft()))
    page.click('#modeDeal');page.set_input_files('#photo',photo())
    page.wait_for_function("document.querySelector('#startBtn').textContent.includes('Confirm')")
    assert page.is_visible('#startBtn') and page.is_hidden('#solveBtn')
    assert page.locator('#editBoard .back').count()==27
    assert page.locator('#editBoard .review').count()==1
    page.click('#editBoard [data-p="20"]');page.click('#keys [data-k="2"]')
    assert page.locator('#editBoard .review').count()==0
    page.click('#startBtn');page.wait_for_selector('#board .c')
    assert page.locator('#board .back').count()==18
    assert page.locator('#board .ask').count()==8
    assert page.inner_text('#wst')=='K' and page.inner_text('#stk')=='24'
    page.close()


def test_stale_photo_does_not_replace_new_selection_or_edits(server,browser):
    page=open_page(browser,server);requests=[]
    page.route('**/api/photo',lambda route:requests.append(route))
    page.set_input_files('#photo',photo());page.wait_for_function("document.querySelector('#msg').textContent==='Reading the cards…'")
    page.wait_for_timeout(100)
    page.set_input_files('#photo',photo());page.wait_for_timeout(200)
    assert len(requests)==2
    requests[1].fulfill(json=draft('2'));page.wait_for_function("document.querySelector('#startBtn').textContent.includes('Confirm')")
    requests[0].fulfill(json=draft('A'));page.wait_for_timeout(100)
    assert page.locator('#editBoard [data-p="19"]').inner_text().endswith('2')
    page.set_input_files('#photo',photo());page.wait_for_timeout(200)
    page.click('#editBoard [data-p="19"]');page.click('#keys [data-k="3"]')
    requests[2].fulfill(json=draft('A'));page.wait_for_timeout(100)
    assert page.locator('#editBoard [data-p="19"]').inner_text().endswith('3')
    page.close()


def test_bad_photo_preserves_board_and_reselection_works(server,browser):
    page=open_page(browser,server)
    page.click('#wasteBtn');page.click('#keys [data-k="Q"]')
    page.set_input_files('#photo',{'name':'bad.jpg','mimeType':'image/jpeg','buffer':b'bad image'})
    page.wait_for_selector('#msg.err');assert 'JPEG' in page.inner_text('#msg')
    assert page.inner_text('#wasteBtn')=='Q'
    calls=[]
    def response(route):calls.append(1);route.fulfill(json=draft())
    page.route('**/api/photo',response)
    for i in range(2):
        page.set_input_files('#photo',photo());page.wait_for_function("document.querySelector('#photoNote').textContent.includes('Read in')")
        page.wait_for_timeout(100)
    assert len(calls)==2
    page.close()


def test_pasted_markup_never_enters_board(server,browser):
    page=open_page(browser,server);page.click('summary:has-text("Paste the board")')
    page.fill('#paste',' '.join(['?']*27+['<IMG/SRC/ONERROR=alert(1)>']));page.click('#pasteBtn')
    assert 'Use only' in page.inner_text('#msg')
    assert page.locator('#editBoard img').count()==0
    page.close()


def test_bitmap_decode_falls_back_to_image_element(server,browser):
    page=open_page(browser,server)
    page.evaluate("() => { window.createImageBitmap=async()=>{throw new Error('unsupported')}; }")
    page.route('**/api/photo',lambda route:route.fulfill(json=draft()))
    page.set_input_files('#photo',photo());page.wait_for_function("document.querySelector('#photoNote').textContent.includes('Read in')")
    assert page.locator('#msg.err').count()==0
    page.close()
