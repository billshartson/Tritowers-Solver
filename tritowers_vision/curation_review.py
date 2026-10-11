"""Private review workflow; never substitutes match confidence for crop review."""
import copy,json
from .curation import validate,bank

def queue(data,manifest):
 validate(data,manifest)
 # Every query needs visual review. Approving a training sample is not query acceptance.
 return [{'photo_id':s['photo_id'],'slot_index':s['slot_index'],'card_label':s['card_label'],'crop_sha256':s['crop_sha256'],'template_decision':s['decision'],'reason':s['reason'],'query_status':'needs_visual_review'} for s in manifest['samples']]

def apply_review(data,manifest,photo_id,slot_index,crop_sha256,reason):
 validate(data,manifest);m=copy.deepcopy(manifest)
 found=[s for s in m['samples'] if s['photo_id']==photo_id and s['slot_index']==slot_index]
 if len(found)!=1:raise ValueError('Unknown review target')
 s=found[0]
 if s['crop_sha256']!=crop_sha256:raise ValueError('Stale review target')
 s['reason']=reason;s['decision']='approve' if reason=='clean' else 'reject'
 validate(data,m);return m


def diagnostics(data, manifest, predictions):
    """Separate reviewed localisation from candidate rank matching, without accepting queries.

    predictions maps (photo_id, slot_index) to a proposed rank or None. Every
    reviewed query must be included, including rejected training crops. These
    totals do not establish independent validation or automatic acceptance.
    """
    from .curation import REASONS, RANKS, card_rank
    validate(data, manifest)
    expected = {(s['photo_id'], s['slot_index']) for s in manifest['samples']}
    if set(predictions) != expected:
        raise ValueError('Predictions must cover every reviewed query exactly once')
    crop_counts = {reason: 0 for reason in sorted(REASONS)}
    matching = {group: {'correct': 0, 'wrong': 0, 'abstain': 0}
                for group in ('all_crops', 'clean_crops', 'visually_bad_crops')}
    for sample in manifest['samples']:
        key = sample['photo_id'], sample['slot_index']
        candidate = predictions[key]
        if candidate is not None and (not isinstance(candidate, str) or candidate not in RANKS):
            raise ValueError('Prediction must be a rank or None')
        crop_counts[sample['reason']] += 1
        outcome = ('abstain' if candidate is None else
                   'correct' if candidate == card_rank(sample['card_label']) else 'wrong')
        group = 'clean_crops' if sample['reason'] == 'clean' else 'visually_bad_crops'
        matching['all_crops'][outcome] += 1
        matching[group][outcome] += 1
    return {'samples': len(expected), 'localization': crop_counts, 'matching': matching,
            'correct_on_bad_crops': matching['visually_bad_crops']['correct'],
            'query_status': 'needs_visual_review',
            'scope': 'crop_review_diagnostic_not_independent_validation'}
