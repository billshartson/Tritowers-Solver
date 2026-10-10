"""Private crop-review contracts. Manifests contain provenance, never image data."""
import hashlib
import json
import numpy as np

REASONS = {"wrong_neighbour", "blank", "partial", "clean"}
RANKS = {"A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"}


def digest(glyph):
    array = np.asarray(glyph)
    if array.dtype.hasobject or array.ndim != 2 or not array.size:
        raise ValueError("Invalid crop")
    if not np.isfinite(array).all(): raise ValueError("Nonfinite crop")
    metadata = json.dumps({"shape": list(array.shape), "dtype": array.dtype.str,
                           "schema": "rank-crop-v2"}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(metadata + b"\0" + np.ascontiguousarray(array).tobytes()).hexdigest()


def card_rank(label):
    """Private draw labels include a suit suffix; matching metrics remain rank-only."""
    if not isinstance(label, str) or len(label) < 2 or label[:-1] not in RANKS or label[-1].lower() not in "cdhs":
        raise ValueError("Invalid card label")
    return label[:-1]


def validate(data, manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported review schema")
    if not isinstance(manifest.get("samples"), list): raise ValueError("Review samples must be a list")
    expected = {(photo, index) for photo, items in data.items() for index in range(len(items))}
    seen = set()
    for sample in manifest["samples"]:
        if not isinstance(sample, dict): raise ValueError("Invalid review sample")
        photo, index = sample.get("photo_id"), sample.get("slot_index")
        if not isinstance(photo, str) or type(index) is not int: raise ValueError("Invalid sample identity")
        key = (photo, index)
        if key in seen: raise ValueError("Duplicate sample")
        if key not in expected: raise ValueError("Unknown sample")
        seen.add(key)
        glyph, label = data[photo][index]
        card_rank(label)
        if sample.get("crop_sha256") != digest(glyph): raise ValueError("Stale crop review")
        if sample.get("card_label") != label: raise ValueError("Changed label")
        reason = sample.get("reason")
        if not isinstance(reason, str) or reason not in REASONS: raise ValueError("Unknown reason")
        if sample.get("decision") != ("approve" if reason == "clean" else "reject"):
            raise ValueError("Inconsistent review")
    if seen != expected: raise ValueError("Missing review")


def bank(data, manifest, mode, held_out=None):
    validate(data, manifest)
    if mode not in {"production", "offline_logo"}: raise ValueError("Unknown mode")
    if mode == "offline_logo" and held_out not in data: raise ValueError("Held-out photo required")
    if mode == "production" and held_out is not None: raise ValueError("Production must not exclude a photo")
    return [(data[s["photo_id"]][s["slot_index"]][0], card_rank(s["card_label"]), s["photo_id"], s["slot_index"])
            for s in manifest["samples"] if s["decision"] == "approve"
            and (mode == "production" or s["photo_id"] != held_out)]
