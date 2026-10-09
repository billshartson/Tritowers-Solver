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
