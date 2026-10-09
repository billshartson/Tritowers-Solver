"""Private prototype. No image data in manifests; runtime data never committed."""
import hashlib,numpy as np
REASONS={'wrong_neighbour','blank','partial','clean'}
def digest(g):return hashlib.sha256(np.ascontiguousarray(g).tobytes()).hexdigest()
def validate(data,manifest):
 expected={(h,i) for h,items in data.items() for i in range(len(items))};seen=set()
 for sample in manifest['samples']:
  key=(sample['photo_id'],sample['slot_index']);h,i=key
  if key in seen:raise ValueError('Duplicate sample')
  if key not in expected:raise ValueError('Unknown sample')
  seen.add(key);g,l=data[h][i]
  if sample['crop_sha256']!=digest(g):raise ValueError('Stale crop review')
  if sample['card_label']!=l:raise ValueError('Changed label')
  if sample['reason'] not in REASONS:raise ValueError('Unknown reason')
  if sample['decision']!=('approve' if sample['reason']=='clean' else 'reject'):raise ValueError('Inconsistent review')
 if seen!=expected:raise ValueError('Missing review')
def bank(data,manifest,mode,held_out=None):
 validate(data,manifest)
 if mode not in {'production','offline_logo'}:raise ValueError('Unknown mode')
 if mode=='offline_logo' and held_out not in data:raise ValueError('Held-out photo required')
 if mode=='production' and held_out is not None:raise ValueError('Production must not exclude a photo')
 return [(data[s['photo_id']][s['slot_index']][0],s['card_label'][:-1],s['photo_id'],s['slot_index']) for s in manifest['samples'] if s['decision']=='approve' and (mode=='production' or s['photo_id']!=held_out)]
