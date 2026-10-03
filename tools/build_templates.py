"""Build private photo templates (the TT_TEMPLATES file) from labelled screenshots or photos of one skin.

    python tools/build_templates.py private/labels.json private/templates.json

labels.json lists images next to it, in the board notation the solver uses (one entry per image):
    [{"image": "IMG_0001.jpg", "board": "? ? ? ... 2 A 3 7 9 J 5 3 9 3", "waste": "K"}, ...]
board has 28 tokens for positions 1-28: a rank for a face-up card, ? for a covered card, -- for an empty slot.

Glyphs are cut by the same reader that uses them (tritowers_vision.reader), so templates and reads always match.
Images whose card layout is not found reliably are skipped. The output stays private: never commit it.
Measure before deploying: python tools/vision_eval.py --labels private/labels.json --captures 4
"""
from collections import Counter
from pathlib import Path
import argparse, json, sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tritowers_vision.rank import save_templates          # noqa: E402
from tritowers_vision.reader import labelled_glyphs, read_photo   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", type=Path); ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    if a.out.exists(): ap.error(f"{a.out} exists; choose a new path")
    templates = []
    for e in json.loads(a.labels.read_text()):
        board = e["board"].split() if isinstance(e["board"], str) else list(e["board"])
        if len(board) != 28: ap.error(f"{e['image']}: board needs 28 tokens, got {len(board)}")
        path = a.labels.parent / e["image"]
        reg = read_photo(path).registration
        if not reg.trusted:
            print(f"skip {e['image']}: layout not found reliably (quality {reg.quality:.2f})"); continue
        got = labelled_glyphs(path, board, e["waste"])
        print(f"{e['image']}: {len(got)} glyphs"); templates += got
    if not templates: sys.exit("No templates built.")
    save_templates(a.out, templates)
    counts = Counter(r for r, _ in templates)
    print(f"Wrote {len(templates)} templates to {a.out}: " + ", ".join(f"{r}x{n}" for r, n in sorted(counts.items(), key=lambda kv: kv[0])))
    missing = [r for r in ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K") if r not in counts]
    if missing: print("No template yet for: " + " ".join(missing) + " (the bundled font tier covers them)")


if __name__ == "__main__":
    main()
