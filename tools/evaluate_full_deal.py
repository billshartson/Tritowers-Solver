r"""Evaluate automatic full-deal intake against separately transcribed labels.

    python tools/evaluate_full_deal.py --labels private/full-deal-labels.json
    python tools/evaluate_full_deal.py --labels private/full-deal-labels.json \
        --variants original,jpeg1600,jpeg1200,rotate2,perspective

Labels contain a ``photos`` list with ``image``, ``board`` (28 ranks),
``waste`` and ``stock`` (23 ranks in draw order, excluding the final joker).
Board and stock may be space-separated strings or lists. Each photographed
deal must contain exactly four of each normal rank. Labels only score results;
they never provide templates, geometry, rank corrections or decoder hints.

JSON output contains counts, mapping checks and timing, never card ranks or
image data. Cases are numbered unless --include-filenames is requested.
Derived variants test perturbations of the same captures, not independent
field performance. The first read includes cold caches; subsequent reads do not.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RANKS = tuple("A 2 3 4 5 6 7 8 9 10 J Q K".split())
BOARD_SLOTS = tuple(f"tableau-{i:02d}" for i in range(1, 29))
STOCK_SLOTS = tuple(f"stock-{i:02d}" for i in range(1, 25))
NORMAL_SLOTS = BOARD_SLOTS + ("waste",) + STOCK_SLOTS[:-1]
ALL_SLOTS = NORMAL_SLOTS + STOCK_SLOTS[-1:]
VARIANTS = ("original", "jpeg1600", "jpeg1200", "rotate2", "perspective")


def tokens(value):
    return value.split() if isinstance(value, str) else list(value)


def load_labels(path, image_dir=None):
    """Validate labels before any recognition to prevent misleading metrics."""
    path = Path(path)
    root = Path(image_dir) if image_dir else path.parent
    document = json.loads(path.read_text())
    photos = document["photos"] if isinstance(document, dict) else document
    if not photos:
        raise ValueError("Labels need at least one photo")
    result = []
    for index, photo in enumerate(photos, 1):
        board, stock = tokens(photo["board"]), tokens(photo["stock"])
        waste = photo["waste"]
        if len(board) != 28 or len(stock) != 23:
            raise ValueError(f"Case {index}: expected 28 board and 23 normal stock ranks")
        truth = board + [waste] + stock
        if Counter(truth) != Counter({rank: 4 for rank in RANKS}):
            raise ValueError(f"Case {index}: expected four of each normal rank")
        if photo.get("visible_rank_uncertainties"):
            raise ValueError(f"Case {index}: resolve uncertain labels before scoring")
        result.append({"path": root / photo["image"], "truth": dict(zip(NORMAL_SLOTS, truth)),
                       "stock": stock + ["*"]})
    return result


def variant_image(data, variant):
    """Create generic browser-size and mild geometry variants without labels."""
    if variant == "original":
        return data
    from PIL import Image
    from tritowers_vision.image import normalize_image

    image = normalize_image(data)
    if variant == "jpeg1200":
        image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    elif variant == "rotate2":
        image = image.rotate(2, Image.Resampling.BICUBIC, expand=True, fillcolor=(20, 20, 20))
    elif variant == "perspective":
        import cv2
        import numpy as np
        width, height = image.size
        source = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
        target = np.float32([[width * .02, height * .01], [width * .97, height * .04],
                             [width * .99, height * .96], [width * .01, height * .99]])
        matrix = cv2.getPerspectiveTransform(source, target)
        image = Image.fromarray(cv2.warpPerspective(np.asarray(image), matrix, image.size,
                                                    borderValue=(20, 20, 20)))
    elif variant != "jpeg1600":
        raise ValueError(f"Unknown variant: {variant}")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def count_ranks(cards, truth, slots):
    counts = {"correct": 0, "wrong": 0, "abstain": 0}
    for slot in slots:
        predicted = cards.get(slot, {}).get("rank")
        if predicted == truth[slot]:
            counts["correct"] += 1
        elif predicted not in (None, "?", ""):
            counts["wrong"] += 1
        else:
            counts["abstain"] += 1
    return counts


def score_draft(draft, labelled):
    """Separate rank, state, classification and app-facing mapping outcomes."""
    cards = draft.get("cards", {})
    truth = labelled["truth"]
    states = Counter(cards.get(slot, {}).get("state", "unknown") for slot in ALL_SLOTS)
    stock = draft.get("stock", [])
    slot_stock = [cards.get(slot, {}).get("rank") or "?" for slot in STOCK_SLOTS]
    kind = draft.get("photo_kind", "tableau")
    board_exact = all(cards.get(slot, {}).get("rank") == truth[slot] for slot in BOARD_SLOTS)
    waste_exact = cards.get("waste", {}).get("rank") == truth["waste"]
    return {
        "classification": kind,
        "classified_full_deal": kind == "full_deal",
        "trusted": bool(draft.get("registration", {}).get("trusted")),
        "rank_counts": count_ranks(cards, truth, NORMAL_SLOTS),
        "by_zone": {"board": count_ranks(cards, truth, BOARD_SLOTS),
                    "waste": count_ranks(cards, truth, ("waste",)),
                    "stock": count_ranks(cards, truth, STOCK_SLOTS[:-1])},
        "state_counts": {"correct_face_up": states["face_up"],
                         "unknown": states["unknown"],
                         "wrong": len(ALL_SLOTS) - states["face_up"] - states["unknown"]},
        "mapping": {"all_53_slots_present": all(slot in cards for slot in ALL_SLOTS),
                    "board_exact": board_exact,
                    "waste_exact": waste_exact,
                    "stock_order_exact": stock == labelled["stock"],
                    "stock_matches_card_slots": len(stock) == 24 and stock == slot_stock,
                    "joker_tail": len(stock) == 24 and stock[-1] == "*" and
                                  cards.get(STOCK_SLOTS[-1], {}).get("rank") == "*"},
        "review_count": len(draft.get("needs_human_review", [])),
        "complete": bool(draft.get("complete")),
        "joker_source": cards.get(STOCK_SLOTS[-1], {}).get("tier", "missing"),
        "joker_inferred": bool(cards.get(STOCK_SLOTS[-1], {}).get("inferred")),
    }


def summarize(cases):
    ranks = Counter()
    states = Counter()
    classifications = Counter()
    for case in cases:
        ranks.update(case["rank_counts"])
        states.update(case["state_counts"])
        classifications[case["classification"]] += 1
    return {"cases": len(cases), "classification_counts": dict(classifications),
            "trusted": sum(case["trusted"] for case in cases),
            "rank_counts": dict(ranks), "state_counts": dict(states),
            "complete_exact_deals": sum(case["classified_full_deal"] and case["trusted"] and
                                        case["rank_counts"]["correct"] == 52 and
                                        all(case["mapping"].values()) and
                                        case["state_counts"]["correct_face_up"] == 53
                                        for case in cases),
            "errors": sum("error_type" in case for case in cases),
            "seconds_total": round(sum(case["seconds"] for case in cases), 3)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--variants", default="original", help="Comma separated: " + ",".join(VARIANTS))
    parser.add_argument("--include-filenames", action="store_true", help="Include image filenames in local output")
    args = parser.parse_args(argv)
    variants = args.variants.split(",")
    if not variants or any(variant not in VARIANTS for variant in variants):
        parser.error("Unknown variant; choose from " + ", ".join(VARIANTS))
    try:
        labelled = load_labels(args.labels, args.image_dir)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
    from tritowers_vision.intake import read_photo
    from tritowers_vision import full_deal, glyphs, image, intake
    source_sha256 = {Path(module.__file__).name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                     for module in (intake, full_deal, glyphs, image)}

    cases = []
    for index, photo in enumerate(labelled, 1):
        data = photo["path"].read_bytes()
        for variant in variants:
            source = variant_image(data, variant)
            started = time.perf_counter()
            error_type = None
            try:
                draft = read_photo(source).draft
            except Exception as error:
                # Errors remain visible in aggregate metrics; omit exception text,
                # which can contain local paths or implementation-specific data.
                draft = {"photo_kind": "error"}
                error_type = type(error).__name__
            elapsed = time.perf_counter() - started
            result = {"case": index, "variant": variant, **score_draft(draft, photo),
                      "seconds": round(elapsed, 3)}
            if error_type:
                result["error_type"] = error_type
            if args.include_filenames:
                result["image"] = photo["path"].name
            cases.append(result)
    output = {"schema_version": 1, "labelled_photos": len(labelled),
              "variants": variants,
              "source_sha256": source_sha256,
              "state_scope": "53 slot states, including the machine-rule joker; this is not a crop-quality score.",
              "timing_scope": "Recognition only; variant encoding excluded. First call has cold caches.",
              "summary": summarize(cases),
              "by_variant": {variant: summarize([case for case in cases if case["variant"] == variant])
                             for variant in variants},
              "cases": cases}
    print(json.dumps(output, indent=2))
    return 1 if output["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
