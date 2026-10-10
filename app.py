import os
import logging
import gradio as gr
import solver_ui as ui
from tritowers_vision.image import ImageInputError, MAX_BYTES, order_corners
from web_shared import solve_deal
from tritowers_vision.rank import load_templates
from tritowers_vision.reader import board_tokens
from tritowers_vision.intake import read_photo
TEMPLATES = load_templates(os.environ["TT_TEMPLATES"]) if os.environ.get("TT_TEMPLATES") and os.path.exists(os.environ["TT_TEMPLATES"]) else []
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

def parse_corners(text):
    if not text or not text.strip(): return None
    nums = [float(x) for x in text.replace(";", ",").replace("\n", ",").split(",") if x.strip()]
    if len(nums) != 8: raise gr.Error("Corners: 8 numbers, x,y for 4 corners")
    return order_corners([(nums[i], nums[i + 1]) for i in range(0, 8, 2)]).tolist()

def draft_to_board_text(draft):
    """Unknowns stay '?'; nothing is guessed. Empty slots become '--'."""
    tokens, waste = board_tokens(draft)
    return " ".join(tokens), waste

def inspect_image(path, corners_text):
    if not path: return None, None, {"unsupported_reason": "no_image"}, {}, "", "", "Upload an image first.", ""
    try: manual = parse_corners(corners_text)
    except (ValueError, TypeError): raise gr.Error("Corners need four distinct, finite x,y points around the screen.")
    try:
        r = read_photo(path, TEMPLATES, manual)
    except ImageInputError as error:
        raise gr.Error(f"Could not read that image: {error}") from None
    except Exception:
        logging.getLogger(__name__).exception("Photo recognition failed")
        raise gr.Error("Could not read that image. Try a clear JPEG, PNG or HEIC photo of the whole screen.") from None
    d = r.draft; board, waste = draft_to_board_text(d); reg = d["registration"]
    review = d["needs_human_review"]
    if not reg["trusted"]:
        msg = "The card layout was not found reliably, so every card needs checking. Try a straighter photo with the whole screen in view, or enter the four screen corners."
    else:
        msg = ("Check the yellow slots: " + ", ".join(s.replace("tableau-", "") for s in review) + "." if review else "Every card was read; still check the picture.")
    stock_order = " ".join(d.get("stock", []))
    if d.get("photo_kind") == "full_deal":
        msg += " Full-deal grid: review the 28 board cards, waste and stock, then copy to Known deal. Stock is read right to left from the bottom row, with the joker last; check that draw order before solving."
    else:
        msg += " Suit and the stock counter are not read: set the stock count yourself, including the joker."
    return r.overlay, r.rectified, reg, d, board, waste, msg, stock_order

def start(board, waste, stock, joker=False):
    if not (waste or "").strip(): raise gr.Error("Choose the waste card before starting.")
    try: s = ui.new_session(board, waste.strip(), stock, joker=joker)
    except Exception as e: raise gr.Error(str(e))
    return s, ui.render_board(s), ui.status(s), "", ""

def act(fn):
    def run(s, *args):
        if s is None: raise gr.Error("Start a game first.")
        try: out = fn(s, *args)
        except Exception as e: raise gr.Error(str(e))
        return s, ui.render_board(s), ui.status(s), out or "", "\n".join(s.log[-8:])
    return run
def recommendation(session, simulations, seed):
    text, position, _, _, _ = ui.recommend_detail(session, simulations, seed)
    foresight = ui.foresight_line(session, position, seed) if position else None
    return text + ("\n\n" + foresight if foresight else "")


def complete_deal(board, waste, stock_text):
    try:
        if not isinstance(stock_text, str): raise ValueError("Enter stock ranks in draw order.")
        stock = stock_text.replace(",", " ").split()
        result = solve_deal({"board": board, "waste": waste or "", "stock": stock, "stock_count": len(stock)})
    except ValueError as error: raise gr.Error(str(error)) from None
    return result.get("message", ""), "\n".join(f"{i}. {step}" for i, step in enumerate(result.get("steps", []), 1))

rec = act(recommendation); play = act(lambda s, p: ui.do_play(s, p)); reveal = act(lambda s, p, r: ui.do_reveal(s, p, r))
draw = act(lambda s, r: ui.do_draw(s, r)); undo = act(lambda s: s.undo())

with gr.Blocks(title="TriTowers") as demo:
    gr.Markdown("# TriTowers\nRank-only solver with a photo reader. Recognition is calibrated on one skin: always check its draft. Sampled percentages are estimates, never proofs.")
    session = gr.State(None)
    with gr.Tab("Solver"):
        with gr.Row():
            with gr.Column(scale=1):
                board = gr.Textbox(label="Board, positions 1-28 (A 2-10 J Q K, ? covered, -- empty)", lines=3, value="? " * 18 + "2 A 3 7 9 J 5 3 9 3")
                with gr.Row(): waste = gr.Dropdown(RANKS, label="Waste card (required)", value=None, allow_custom_value=True); stock = gr.Number(label="Stock cards left (engine count)", value=23, precision=0)
                joker = gr.Checkbox(label="Fixed joker is the last stock card (included in stock count)", value=False)
                begin = gr.Button("Start game", variant="primary")
            with gr.Column(scale=2):
                view = gr.HTML(); state_line = gr.Markdown(); advice = gr.Markdown()
                with gr.Row(): sims = gr.Slider(100, ui.MAX_SIMULATIONS, value=1200, step=100, label="Simulations"); seed = gr.Textbox(label="Seed (optional)")
                ask = gr.Button("Recommend a move", variant="primary")
                with gr.Row(): pos = gr.Number(label="Position", precision=0); do_play_btn = gr.Button("Play it"); undo_btn = gr.Button("Undo")
                with gr.Row(): rpos = gr.Number(label="Reveal position", precision=0); rrank = gr.Dropdown(RANKS, label="Rank", allow_custom_value=True); rbtn = gr.Button("Reveal")
                with gr.Row(): drank = gr.Dropdown(RANKS + ["*"], label="Card drawn from stock", allow_custom_value=True); dbtn = gr.Button("Draw")
                history = gr.Textbox(label="Log", lines=4, interactive=False)
        outs = [session, view, state_line, advice, history]
        begin.click(start, [board, waste, stock, joker], outs); ask.click(rec, [session, sims, seed], outs); do_play_btn.click(play, [session, pos], outs)
        rbtn.click(reveal, [session, rpos, rrank], outs); dbtn.click(draw, [session, drank], outs); undo_btn.click(undo, [session], outs)
    with gr.Tab("Photo to board"):
        upload = gr.Image(type="filepath", label="Quiz-machine photo or screenshot")
        corners = gr.Textbox(label="Optional manual screen corners (x,y x4). Usually leave blank: the card layout is found automatically in screenshots, crops and photos")
        go = gr.Button("Read photo", variant="primary"); note = gr.Markdown()
        with gr.Row(): overlay = gr.Image(label="What was read (green read, yellow check, red covered, grey empty)"); rectified = gr.Image(label="Rectified screen")
        pboard = gr.Textbox(label="Draft board (edit before use)", lines=3); pwaste = gr.Textbox(label="Draft waste")
        pstock = gr.Textbox(label="Draft stock order from a full-deal grid, next draw first (edit ? entries before solving)")
        with gr.Accordion("Raw recognition output", open=False): result = gr.JSON(label="Layout alignment"); draft = gr.JSON(label="Draft")
        go.click(inspect_image, [upload, corners], [overlay, rectified, result, draft, pboard, pwaste, note, pstock])
        send = gr.Button("Copy draft to Solver tab"); send.click(lambda b, w: (b, w), [pboard, pwaste], [board, waste])
        send_known = gr.Button("Copy reviewed draft to Known deal tab")
    with gr.Tab("Known deal"):
        gr.Markdown("Enter every remaining tableau rank and the complete remaining stock order. Cleared positions use --. Covered unknown ranks cannot be solved exactly.")
        known_board = gr.Textbox(label="28 tableau positions", lines=3)
        known_waste = gr.Dropdown(RANKS + ["*"], label="Waste", allow_custom_value=True)
        known_stock = gr.Textbox(label="Remaining stock, next draw first (empty when exhausted)")
        solve_button = gr.Button("Find a verified line")
        solve_message = gr.Markdown()
        solve_steps = gr.Textbox(label="Verified steps", lines=12, interactive=False)
        solve_button.click(complete_deal, [known_board, known_waste, known_stock], [solve_message, solve_steps])
    send_known.click(lambda b, w, s: (b, w, s), [pboard, pwaste, pstock], [known_board, known_waste, known_stock])

demo.queue(max_size=32, default_concurrency_limit=1)

# One runtime serves the mobile UI/API and the alternate Gradio interface.
from web_app import app as web_application
app = gr.mount_gradio_app(web_application, demo, path="/gradio", max_file_size=MAX_BYTES)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "7860")))
