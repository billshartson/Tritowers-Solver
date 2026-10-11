"""Public, image-local card anchors for automatic tableau registration.

These are only initial hypotheses. A white rectangle is not evidence of a game:
register.py tests its extrapolated layout against the screen and every slot.
No owner image, crop, label or learned private template is loaded here.
"""
import cv2
import numpy as np

from . import scene
from .layout import STOCK_BOX


def _ordered(quad):
    points = np.asarray(quad, np.float32).reshape(4, 2)
    sums, differences = points.sum(axis=1), points[:, 1] - points[:, 0]
    order = [int(sums.argmin()), int(differences.argmin()), int(sums.argmax()), int(differences.argmax())]
    return points[order] if len(set(order)) == 4 else None


def _edge_corners(contour, quad):
    """Intersect fitted straight edges, avoiding bias from rounded card corners."""
    points = contour.reshape(-1, 2).astype(np.float64)
    lines = []
    for p, q in zip(quad, np.roll(quad, -1, axis=0)):
        v = q - p
        length = np.linalg.norm(v)
        t = (points - p) @ v / (length * length)
        distance = np.abs(v[0] * (points[:, 1] - p[1]) - v[1] * (points[:, 0] - p[0])) / length
        kept = points[(t > .15) & (t < .85) & (distance < max(2.5, length * .04))]
        if len(kept) < 4:
            return quad
        vx, vy, x, y = cv2.fitLine(kept.astype(np.float32), cv2.DIST_L2, 0, .01, .01).ravel()
        lines.append(np.array([vy, -vx, vx * y - vy * x], np.float64))
    out = []
    for a, b in zip(np.roll(lines, 1, axis=0), lines):
        point = np.cross(a, b)
        if abs(point[2]) < 1e-8:
            return quad
        out.append(point[:2] / point[2])
    out = np.asarray(out, np.float32)
    return out if np.max(np.linalg.norm(out - quad, axis=1)) < 6 else quad


def card_quads(work):
    """Complete card-sized quadrilaterals in working-image pixels, with face/back shares."""
    from .register import cardness
    mask = (cardness(work.face, work.back) * 255).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    area = work.size[0] * work.size[1]
    out = []
    for contour in contours:
        if not .002 * area < cv2.contourArea(contour) < .08 * area:
            continue
        polygon = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        quad = _ordered(polygon)
        if quad is None:
            continue
        quad = _edge_corners(contour, quad)
        sides = np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)
        if min(sides) < 10 or not .35 < (sides[0] + sides[2]) / (sides[1] + sides[3]) < 1.1:
            continue
        inside = np.zeros(mask.shape, np.uint8)
        cv2.fillConvexPoly(inside, quad.astype(np.int32), 1)
        inside = cv2.erode(inside, np.ones((5, 5), np.uint8)) > 0
        if not inside.any():
            continue
        face, back = float(work.face[inside].mean()), float(work.back[inside].mean())
        if max(face, back) < .3:
            continue
        out.append((quad, face, back))
    return out


def _rect(box):
    x0, y0, x1, y1 = box
    return np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def candidates(work):
    """Stock/waste pairs and single-waste fallbacks; never trust the anchor alone."""
    from .register import _sane
    quads = card_quads(work)
    out = []
    for waste, face, back in quads:
        if face < .4 or face < back:
            continue
        # A single card determines perspective but can extrapolate poorly; screen
        # and upper-tableau evidence must independently support it downstream.
        for dy in (-26, -14, -2):
            H = cv2.getPerspectiveTransform(_rect(scene.waste_rect(dy)), waste)
            if _sane(H, work.size):
                out.append(("waste_anchor", H))
        for stock, sf, sb in quads:
            if sb < .35 or stock.mean(axis=0)[0] >= waste.mean(axis=0)[0]:
                continue
            ratio = cv2.contourArea(stock) / max(cv2.contourArea(waste), 1)
            if not .65 < ratio < 1.7:
                continue
            for dy in (-26, -14, -2):
                for sy in (0, 8):
                    source = np.concatenate([_rect(scene.waste_rect(dy)), _rect(np.array(STOCK_BOX) + [0, sy, 0, sy])])
                    H, _ = cv2.findHomography(source, np.concatenate([waste, stock]))
                    if H is not None and _sane(H, work.size):
                        out.append(("stock_waste_anchors", H))
    return out


def photographic_candidates(image, work):
    """Edge anchors also survive warm lighting that defeats global white balance.

    Each candidate carries its own card-face reference. The reference is derived
    from that image's waste card, never from a calibration photo or private bank.
    """
    from .register import _Work, _sane
    scale = min(1., 1000 / max(image.size))
    rgb = np.asarray(image.resize((round(image.width * scale), round(image.height * scale))))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    masks = [cv2.Canny(gray, 50, 140), cv2.morphologyEx((gray > 150).astype(np.uint8) * 255,
                                                    cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))]
    quads = []
    height, width = gray.shape
    for mask in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            polygon = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
            area = abs(cv2.contourArea(polygon))
            if len(polygon) != 4 or not cv2.isContourConvex(polygon) or not .001 < area / (height * width) < .045:
                continue
            quad = _ordered(polygon)
            if quad is None:
                continue
            quad = _edge_corners(contour, quad)
            cw, ch = np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[3] - quad[0])
            if not .35 < cw / ch < .9 or quad.mean(axis=0)[1] < .60 * height:
                continue
            duplicate = next((i for i, old in enumerate(quads) if np.linalg.norm(quad.mean(axis=0) - old.mean(axis=0)) < .015 * width), None)
            if duplicate is None:
                quads.append(quad)
            elif cv2.contourArea(quad) > cv2.contourArea(quads[duplicate]):
                quads[duplicate] = quad
    guesses = []
    for waste in quads:
        # A face has a bright interior, a back a dark/red one. Local quantiles
        # identify a reference but the full scene must still validate ownership.
        target = _rect((0, 0, 120, 180))
        local = cv2.warpPerspective(rgb, cv2.getPerspectiveTransform(waste, target), (120, 180))
        central = local[12:-12, 12:-12]
        vals = central.max(axis=2)
        ref = np.median(central[vals >= np.percentile(vals, 70)], axis=0)
        saturation = (ref.max() - ref.min()) / max(1., ref.max())
        if ref.min() < 75 or saturation > .6:
            continue
        for stock in quads:
            if stock is waste or stock.mean(axis=0)[0] >= waste.mean(axis=0)[0]:
                continue
            sh, wh = np.linalg.norm(stock[3] - stock[0]), np.linalg.norm(waste[3] - waste[0])
            gap = np.linalg.norm(waste.mean(axis=0) - stock.mean(axis=0))
            if not .08 * width < gap < .32 * width or not .65 < sh / wh < 1.5:
                continue
            if abs(waste.mean(axis=0)[1] - stock.mean(axis=0)[1]) > .45 * max(sh, wh):
                continue
            H, _ = cv2.findHomography(np.concatenate([_rect(STOCK_BOX), _rect(scene.waste_rect())]), np.concatenate([stock, waste]))
            if H is not None:
                guesses.append(("card_edge_pair", H, ref))
        # Single-waste fallback stays available when stock is exhausted. Its
        # extrapolation must pass the same full-scene tests as every other guess.
        H = cv2.getPerspectiveTransform(_rect(scene.waste_rect()), waste)
        guesses.append(("card_edge_single", H, ref))
    out = []
    for method, H, ref in guesses:
        H = np.diag([work.f / scale, work.f / scale, 1.]) @ H
        if _sane(H, work.size):
            out.append((method, H, _Work(image, reference=ref)))
    return out


def align(image):
    """Automatic registration using scene-validated screen and card anchors."""
    from .register import register
    return register(image)
