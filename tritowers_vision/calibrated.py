"""Calibrated single-skin pass (v2): occupancy + gated rank reading -> solver-input draft.

Superseded by reader.read_photo (v3), which the apps use; kept so tools/vision_eval.py can compare against it.

Rank/suit output is only for face-up cards read above the acceptance gate. Everything else is
None (unknown). Hidden cards are never inferred. Stock counter is NOT read yet.
"""
from PIL import Image
from .layout import tableau_boxes, WASTE_BOX
from .occupancy import occupancy
from .rank import corner_box
from . import rank2
from .schema import SlotState

def read(rectified: Image.Image, templates):
    occ, boxes = occupancy(rectified), tableau_boxes(); cards = {}
    for slot in [*boxes, "waste"]:
        state, conf = occ[slot]; rank = None; score = margin = 0.0
        if state is SlotState.FACE_UP:
            if slot == "waste":
                box, scale = rank2.waste_corner_box(rectified), 1.5
            else:
                box, scale = corner_box(boxes[slot]), 1.0
            if box is not None:
                p, score, margin, _tier = rank2.match(rank2.glyph(rectified.crop(box), scale), templates)
                if p is not None: rank = p
        cards[slot] = {"state": state.value, "rank": rank, "score": round(score, 2), "margin": round(margin, 2)}
    unresolved = [s for s, c in cards.items() if c["state"] in ("unknown",) or (c["state"] == "face_up" and c["rank"] is None)]
    return {"cards": cards, "needs_human_review": unresolved, "complete": not unresolved and occ["stock"][0] is not SlotState.UNKNOWN,
            "stock_counter": None, "note": "Draft only. Suit not read. Stock counter not read. Human must confirm before solving."}
