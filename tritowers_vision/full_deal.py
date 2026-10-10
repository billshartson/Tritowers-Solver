"""Automatic reader for the machine's 14 / 14 / 25 all-cards display.

Only public font templates and evidence from this photograph are used. A grid
is an editable draft; unidentified ranks stay unknown, including clipped tens.
"""
from dataclasses import dataclass
from itertools import combinations
from collections import Counter
import cv2
import numpy as np
from PIL import Image, ImageDraw
from . import glyphs
from .image import normalize_image


@dataclass
class FullDealRead:
    draft: dict
    overlay: Image.Image
    rectified: Image.Image


def _ink(rgb):
    a = rgb.astype(np.float32)
    paper = cv2.dilate(a, np.ones((45, 45), np.uint8))
    return (((a / (paper + 1)).mean(axis=2) < .68) & (paper.max(axis=2) > 110)).astype(np.uint8)


def _objects(rgb):
    mask = _ink(rgb)
    joined = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    joined = cv2.dilate(joined, np.ones((1, 3), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    scale = max(rgb.shape[:2]) / 1600
    boxes, scores = [], []
    candidates = [tuple(v) for v in stats[1:] if 20*scale < v[3] < 105*scale and 4*scale < v[2] < 105*scale
                  and .13 < v[2]/v[3] < 2.1 and v[4] > max(v[3]*v[2]*.17,80*scale*scale)]
    if len(candidates) < 35 or len(candidates) > 240:
        return np.empty((0,4)), np.empty(0), mask
    for x, y, w, h, area in candidates:
        if not (20 * scale < h < 105 * scale and 4 * scale < w < 105 * scale
                and .13 < w / h < 2.1 and area > max(h * w * .17, 80 * scale * scale)):
            continue
        g = glyphs.normalize(mask[y:y+h, x:x+w])
        ranked = glyphs._ranked(g, glyphs.font_bank())
        boxes.append((x, y, w, h))
        scores.append(ranked[0][1] if ranked else 0)
    return np.asarray(boxes, float).reshape(-1, 4), np.asarray(scores), mask


def _lines(boxes, scores, width):
    centres = boxes[:, :2] + boxes[:, 2:] / 2
    ids = np.where((boxes[:, 3] > width * .015) & (boxes[:, 3] < width * .045) & (scores > .57))[0]
    c, b = centres[ids], boxes[ids]
    lines = []
    for i, p in enumerate(c):
        for q in c[i+1:]:
            if abs(q[0] - p[0]) < width * .36:
                continue
            slope = (q[1] - p[1]) / (q[0] - p[0])
            if abs(slope) > .45:
                continue
            fit = np.array([slope, p[1] - slope * p[0]])
            good = np.abs(c[:, 1] - np.polyval(fit, c[:, 0])) < b[:, 3] * .28
            if good.sum() < 10:
                continue
            fit = np.polyfit(c[good, 0], c[good, 1], 1)
            good = np.abs(c[:, 1] - np.polyval(fit, c[:, 0])) < b[:, 3] * .28
            if good.sum() < 10 or np.ptp(c[good, 0]) < width * .50:
                continue
            mid = float(np.polyval(fit, width / 2))
            line = {"count": int(good.sum()), "mid": mid, "fit": fit, "ids": ids[good]}
            near = next((j for j, other in enumerate(lines) if abs(other["mid"] - mid) < width * .012), None)
            if near is None:
                lines.append(line)
            elif line["count"] > lines[near]["count"]:
                lines[near] = line
    return sorted(sorted(lines, key=lambda line: -line["count"])[:12], key=lambda line: line["mid"])


def _row_boxes(line, boxes, width, count=None):
    seeds = boxes[line["ids"]]
    height_fit = np.polyfit(seeds[:, 0], seeds[:, 3], 1)
    heights = np.polyval(height_fit, boxes[:, 0])
    centres = boxes[:, :2] + boxes[:, 2:] / 2
    good = ((abs(centres[:, 1] - np.polyval(line["fit"], centres[:, 0])) < heights * .38)
            & (boxes[:, 3] > heights * .68) & (boxes[:, 3] < heights * 1.45))
    selected = boxes[good]
    selected = selected[np.argsort(selected[:, 0])]
    # A small decoration or the lower fragment of a rank is not a new card.
    heights = np.polyfit(selected[:, 0], selected[:, 3], 1)
    selected = selected[selected[:, 3] > .72 * np.polyval(heights, selected[:, 0])]
    merged = []
    pitch = np.ptp(selected[:,0]+selected[:,2]/2) / ((count or len(selected))-1)
    typical_height = np.median(selected[:,3])
    for b in selected:
        x, y, w, h = b
        if merged:
            q = merged[-1]
            close = (x+w/2-q[0]-q[2]/2) < .58*pitch*(h+q[3])/(2*typical_height)
            if (x < q[0] + q[2] - 1 or close) and abs(y + h/2 - q[1] - q[3]/2) < min(h, q[3]) * .3:
                left, top = min(x, q[0]), min(y, q[1])
                right, bottom = max(x + w, q[0] + q[2]), max(y + h, q[1] + q[3])
                if right - left < 1.9 * max(h, q[3]):
                    merged[-1] = np.array([left, top, right-left, bottom-top])
                    continue
        merged.append(b.copy())
    return np.asarray(merged)


def _projective(indices, x, count):
    """Fit a perspective-spaced row. Normalising avoids ill-conditioned pixels."""
    centre, span = float(np.mean(x)), float(np.ptp(x))
    v = (x - centre) / span
    A = np.column_stack((np.ones(len(x)), indices, -indices * v))
    a, b, c = np.linalg.lstsq(A, v, rcond=None)[0]
    k = np.arange(count)
    if np.any(1 + c * k < .4):
        return None
    predicted = centre + span * (a + b * k) / (1 + c * k)
    gaps = np.diff(predicted)
    if min(gaps) <= 0 or max(gaps) / min(gaps) > 3.3:
        return None
    residual = np.abs(predicted[indices] - x) / np.interp(indices, k[:-1] + .5, gaps)
    if max(residual) > .30:
        return None
    return predicted, float(np.mean(residual ** 2))


def _assign(row, count, expected_left, expected_right):
    # At most three missed rank objects; never fill a layout made mostly of guesses.
    pitch = (expected_right-expected_left)/(count-1)
    centres = row[:,0]+row[:,2]/2
    row = row[(centres >= expected_left-.65*pitch) & (centres <= expected_right+.65*pitch)]
    n = len(row)
    if n < count - 3 or n > count + 2:
        return None
    proposals = []
    subsets = combinations(range(n), count) if n > count else [tuple(range(n))]
    for subset in subsets:
        observed = row[list(subset)]
        x = observed[:, 0] + observed[:, 2] / 2
        for positions in combinations(range(count), len(observed)):
            fitted = _projective(np.asarray(positions), x, count)
            if fitted is None:
                continue
            predicted, score = fitted
            pitch = np.median(np.diff(predicted))
            endpoint = ((predicted[0] - expected_left) / pitch) ** 2 + ((predicted[-1] - expected_right) / pitch) ** 2
            if endpoint > 2.5:
                continue
            proposals.append((score + .08 * endpoint, predicted, observed, positions))
    if not proposals:
        return None
    proposals.sort(key=lambda value: value[0])
    pitch = float(np.median(np.diff(proposals[0][1])))
    if len(proposals)>1 and proposals[1][0]-proposals[0][0] < .015:
        if np.max(abs(proposals[1][1]-proposals[0][1])) > pitch*.3:
            return None
    _, x, observed, positions = proposals[0]
    centres = observed[:, :2] + observed[:, 2:] / 2
    yfit = np.polyfit(centres[:, 0], centres[:, 1], 1)
    hfit = np.polyfit(centres[:, 0], observed[:, 3], 1)
    return {"x": x, "y": np.polyval(yfit, x), "h": np.polyval(hfit, x), "fit": yfit,
            "objects": {k: b for k, b in zip(positions, observed)}, "score": proposals[0][0]}


def _geometry(rgb):
    boxes, scores, mask = _objects(rgb)
    if len(boxes) < 35:
        return None
    lines = _lines(boxes, scores, rgb.shape[1])
    choices = []
    for triple in combinations(lines, 3):
        a, b, c = triple
        gaps = np.diff([line["mid"] for line in triple])
        if min(gaps) < rgb.shape[1] * .065 or max(gaps) / min(gaps) > 1.40 or c["count"] < 19:
            continue
        if max(abs(b["fit"][0] - a["fit"][0]), abs(c["fit"][0] - b["fit"][0])) > .20:
            continue
        rows = [_row_boxes(line, boxes, rgb.shape[1], count) for line,count in zip(triple,(14,14,24))]
        if not all(count-3 <= len(row) <= count+2 for row, count in zip(rows, (14,14,24))):
            continue
        # The rank columns share the screen's left and right edges. A missed
        # endpoint is recovered from the other two rows, never from deck counts.
        starts = [r[0,0] + r[0,2]/2 for r in rows]
        ends = [r[-1,0] + r[-1,2]/2 for r in rows]
        left, right = float(np.median(starts)), float(np.median(ends))
        assigned = [_assign(row, 14, left, right) for row in rows[:2]]
        if any(row is None for row in assigned):
            continue
        middle = assigned[1]
        deck_left = middle["x"][0] + .4 * middle["h"][0]
        deck_right = middle["x"][-1] + middle["h"][-1]
        assigned.append(_assign(rows[2], 24, deck_left, deck_right))
        if any(row is None for row in assigned):
            continue
        choices.append((sum(row["score"] for row in assigned), assigned))
    if not choices:
        return None
    choices.sort(key=lambda value: value[0])
    return choices[0][1], mask



def _inclusive_ink(patch):
    """A second mask can reveal faint strokes; it can only veto a read."""
    a=patch.astype(np.float32)
    v=a.max(axis=2); chroma=(v-a.min(axis=2))/(v+1)
    bright=(v>=np.percentile(v,60))&(chroma<.35)
    face=np.median(a[bright],axis=0) if bright.sum()>20 else np.percentile(a.reshape(-1,3),90,axis=0)
    distance=cv2.GaussianBlur(np.linalg.norm(a-face,axis=2),(0,0),.8)
    otsu,_=cv2.threshold(np.clip(distance,0,255).astype(np.uint8),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    threshold=max(45.,min(float(otsu),.45*float(np.linalg.norm(face))))
    return (distance>threshold*.65).astype(np.uint8)

def _extract(rgb, row, i, shear):
    x, y, h = row['x'][i], row['y'][i], row['h'][i]
    observed = row['objects'].get(i)
    if observed is not None:
        x = observed[0] + observed[2] / 2
    # Ownership boundaries halfway to adjacent rank centres stop a neighbour
    # entering a damaged/blank slot. The tight deck may crop a ten; abstain.
    left = (row['x'][i-1] + row['x'][i])/2 if i else x - h
    right = (row['x'][i+1] + row['x'][i])/2 if i+1 < len(row['x']) else x + h
    lo, hi = max(left-x, -.90*h), min(right-x, .90*h)
    top, bottom = -.67*h, .66*h
    scale = 2
    W, H = max(8, round((hi-lo)*scale)), max(8, round((bottom-top)*scale))
    M = np.float32([[1/scale, shear/scale, x+lo+shear*top],
                    [row['fit'][0]/scale, 1/scale, y+top+row['fit'][0]*lo]])
    patch = cv2.warpAffine(rgb, M, (W,H), flags=cv2.INTER_LINEAR|cv2.WARP_INVERSE_MAP,
                           borderMode=cv2.BORDER_REPLICATE)
    ink = glyphs.ink_mask(patch)
    _, lab, stats, centres = cv2.connectedComponentsWithStats(ink)
    unit = h*scale
    keep = []
    clipped = False
    for j, (bx,by,bw,bh,area) in enumerate(stats[1:],1):
        if area < .015*unit*unit or bh < .30*unit:
            continue
        if bx == 0 or by == 0 or bx+bw >= W or by+bh >= H:
            if bh > .45*unit and bw > .12*unit and abs((by+bh/2)-H/2) < .28*unit:
                clipped = True
            continue
        if abs((by+bh/2)-H/2) > .25*unit:
            continue
        keep.append(j)
    result = np.isin(lab,keep)
    yy,xx = np.where(result)
    if not len(xx):
        return None, (x+lo, y+top, x+hi, y+bottom), False
    full_height = yy.max()-yy.min()+1
    valid = bool(not clipped and .70*unit <= full_height <= 1.25*unit and xx.min()>1 and xx.max()<W-2)
    g = glyphs.normalize(result[yy.min():yy.max()+1,xx.min():xx.max()+1]) if valid else None
    # Two tall strokes with an open right-hand digit are a clipped ten, not
    # a K. The overlapped stock cards can hide the zero's closing stroke.
    tall = [j for j in keep if stats[j,3] > .65*unit]
    if g is not None and len(tall) > 1 and glyphs.holes(g) == 0:
        g, valid = None, False
    if g is not None:
        inclusive=_inclusive_ink(patch)
        _,soft_labels,soft_stats,_=cv2.connectedComponentsWithStats(inclusive)
        soft_keep=[]
        for j,(bx,by,bw,bh,area) in enumerate(soft_stats[1:],1):
            if (area>.015*unit*unit and bh>.3*unit and bx>0 and by>0
                    and bx+bw<W and by+bh<H and abs(by+bh/2-H/2)<.25*unit):
                soft_keep.append(j)
        soft=np.isin(soft_labels,soft_keep); sy,sx=np.where(soft)
        if len(sx):
            soft_glyph=glyphs.normalize(soft[sy.min():sy.max()+1,sx.min():sx.max()+1])
            # Losing the faint diagonal of a four leaves a J-like stem. Such
            # a threshold-dependent counter cannot support a confident rank.
            if glyphs.holes(soft_glyph)!=glyphs.holes(g):
                g,valid=None,False
    return g, (x+lo, y+top, x+hi, y+bottom), valid



def _joker_face_present(rgb, row, shear):
    """Check that the exposed leftmost card exists; its identity is a rule.

    Sampling the full exposed stripe also rejects crops that removed the joker
    while leaving all 24 normal deck ranks visible.
    """
    x,y,h = row['x'][0],row['y'][0],row['h'][0]
    pitch = row['x'][1]-x
    xx,yy = np.meshgrid(np.linspace(-1.60*pitch,-.90*pitch,15),np.linspace(-.20*h,2.4*h,30))
    xs=x+xx+shear*yy; ys=y+yy+row['fit'][0]*xx
    if xs.min()<1 or ys.min()<1 or xs.max()>=rgb.shape[1]-1 or ys.max()>=rgb.shape[0]-1:
        return False
    pixels=rgb[np.rint(ys).astype(int),np.rint(xs).astype(int)].astype(float)
    v=pixels.max(axis=2); chroma=(v-pixels.min(axis=2))/(v+1)
    return bool(np.mean((v>135)&(chroma<.65))>.60)

def read_full_deal(source):
    """Return an editable 53-card draft, or None for unsupported geometry.

    Tableau slots follow display rows left-to-right. Stock slots follow draw
    order from the rightmost deck card toward the leftmost machine joker.
    """
    image = normalize_image(source)
    rgb = np.asarray(image)
    geometry = _geometry(rgb)
    if geometry is None:
        return None
    rows, _ = geometry
    # Vertical card edges share the drift between the two equally sized rows.
    shear = float(np.median((rows[1]['x']-rows[0]['x'])/(rows[1]['y']-rows[0]['y'])))
    shear = float(np.clip(shear, -.35, .35))
    if not _joker_face_present(rgb,rows[2],shear):
        return None
    found, boxes, valid = {}, {}, {}
    for r,row in enumerate(rows):
        for i in range(len(row['x'])):
            slot = f'tableau-{r*14+i+1:02d}' if r<2 else ('waste' if i==23 else f'stock-{23-i:02d}')
            found[slot], boxes[slot], valid[slot] = _extract(rgb,row,i,shear)
    reads, fit = glyphs.read_ranks(found)
    if fit < glyphs.FONT_FIT:
        return None
    cards = {slot:{'state':'face_up','rank':rank,'score':round(score,3),'margin':round(margin,3),'tier':tier,
                   'crop':{'valid':valid[slot]}} for slot,(rank,score,margin,tier) in reads.items()}
    counts=Counter(card['rank'] for card in cards.values() if card['rank'])
    for rank,count in counts.items():
        if count>4:
            for slot in sorted((s for s in cards if cards[s]['rank']==rank),key=lambda s:cards[s]['score'])[:count-4]:
                cards[slot].update(rank=None,tier='deck_conflict')
    cards['stock-24']={'state':'face_up','rank':'*','score':0.0,'margin':0.0,'tier':'machine_rule','inferred':True}
    review=[s for s,c in cards.items() if c['rank'] is None]
    stock=[cards[f'stock-{i:02d}']['rank'] or '?' for i in range(1,25)]
    draft={'photo_kind':'full_deal','cards':cards,'stock':stock,'needs_human_review':review,'complete':not review,
           'stock_counter':24,'stock_counter_source':'full_deal_layout','font_fit':round(fit,3),'registration':{'method':'automatic_full_deal','trusted':True,
           'quality':round(max(0.,1.-sum(row['score'] for row in rows)),3),'checks':{'rows':[14,14,25],'joker_card_present':True}},
           'note':'Full-deal draft. Check every card and confirm the stock order before solving. The machine joker is last.'}
    overlay=image.copy(); draw=ImageDraw.Draw(overlay)
    for slot,box in boxes.items():
        color=(255,190,0) if slot in review else (20,220,80)
        draw.rectangle(box,outline=color,width=2)
        label = 'W' if slot == 'waste' else ('S'+str(int(slot[6:])) if slot.startswith('stock-') else str(int(slot[8:])))
        draw.text((box[0],box[1]-12),label+':'+(cards[slot]['rank'] or '?'),fill=color,stroke_width=1,stroke_fill=(0,0,0))
    return FullDealRead(draft,overlay,image.copy())
