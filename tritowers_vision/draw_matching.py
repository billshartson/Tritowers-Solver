"""Paired normalization NCC proposals, never accepted solver ranks."""
import cv2,numpy as np
RANKS='A 2 3 4 5 6 7 8 9 10 J Q K'.split()

def _valid(g):
 a=np.asarray(g)
 return a.shape==(32,24) and np.isfinite(a).all() and np.ptp(a)>1e-6

def _nv(arr):
 a=np.asarray(arr,dtype=float).reshape(len(arr),-1);a-=a.mean(1,keepdims=True)
 return a/(np.linalg.norm(a,axis=1,keepdims=True)+1e-6)

def propose(views,templates):
 """templates=[(rank,(baseline,component))]. Caller owns private curation."""
 if len(views)!=2:raise ValueError('Two query views required')
 bank=list(templates)
 if any(r not in RANKS or len(v)!=2 or not all(_valid(g) for g in v) for r,v in bank):raise ValueError('Invalid template bank')
 result={'rank':None,'accepted':False,'needs_visual_review':True,'candidate':None,'score':None}
 if not all(_valid(g) for g in views) or not bank:return result
 scores=[]
 for mode in range(2):
  Q=_nv([views[mode]])[0];S=[]
  for rank,pair in bank:
   variants=[cv2.warpAffine(np.asarray(pair[mode],dtype=np.float32),np.float32([[1,0,dx],[0,1,dy]]),(24,32)) for dx in range(-1,2) for dy in range(-1,2)]
   S.append(float((Q@_nv(variants).T).max()))
  scores.append({r:max(S[i] for i,(rr,v) in enumerate(bank) if rr==r) for r in RANKS if any(rr==r for rr,v in bank)})
 mean={r:(scores[0][r]+scores[1][r])/2 for r in scores[0]};candidate=max(mean,key=mean.get)
 result.update(candidate=candidate,score=float(mean[candidate]));return result
