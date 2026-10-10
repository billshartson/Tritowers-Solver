"""Experimental multi-threshold geometry; never accepted ranks."""
import numpy as np
from .draw_extraction_consensus import extract,crop,component
from tritowers_vision.geometry_rejection import irregular,endpoint_missing

def consensus(image,guides,counts):
 proposals=[]
 for threshold in [90,95,110]:
  def mask(bgr):
   b,g,r=[bgr[...,i].astype(float) for i in range(3)];gray=.3*r+.59*g+.11*b
   return ((gray<threshold)|((r>110)&(g<85)&(b<95)&(r-g>60))).astype(np.uint8)
  try:
   views,meta=extract(image,guides,counts,mask_fn=mask);proposals.append(np.array([m['box'] for m in meta]))
  except ValueError:pass
 if len(proposals)<2:raise ValueError('Insufficient geometry consensus')
 a=np.asarray(proposals);left=a[:,:,0].min(0);top=a[:,:,1].min(0);right=(a[:,:,0]+a[:,:,2]).max(0);bottom=(a[:,:,1]+a[:,:,3]).max(0)
 boxes=np.stack([left,top,right-left,bottom-top],axis=1).astype(int)
 # Reject non-overlapping threshold objects, rather than join separate neighbours.
 for i in range(a.shape[1]):
  for j in range(len(a)):
   for k in range(j+1,len(a)):
    p=a[j,i];q=a[k,i]
    if min(p[0]+p[2],q[0]+q[2])<=max(p[0],q[0]) or min(p[1]+p[3],q[1]+q[3])<=max(p[1],q[1]):raise ValueError('Disjoint threshold ownership')
 offset=0
 for guide,n in zip(guides,counts):
  row=boxes[offset:offset+n];offset+=n
  if irregular(row) or endpoint_missing(row,guide):raise ValueError('Inconsistent aggregate geometry')
 return [(crop(image,b),component(image,b)) for b in boxes],boxes
