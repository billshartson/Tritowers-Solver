"""Ordered object assignment for guided rank proposals. Geometry can reject, never authorize rank."""
import itertools,numpy as np
from tritowers_vision.geometry_rejection import irregular,endpoint_missing

def select(row,n,guide):
 row=list(row)
 if not isinstance(n,(int,np.integer)) or isinstance(n,(bool,np.bool_)) or n<5:raise ValueError('Invalid target count')
 if len(row)<n or len(row)>n+4:raise ValueError('Unbounded row assignment')
 try:
  a=np.asarray([b for t,b in row],dtype=float);t=np.asarray([t for t,b in row],dtype=float);g=np.asarray(guide,dtype=float)
 except (TypeError,ValueError):raise ValueError('Invalid row objects') from None
 if a.shape!=(len(row),4) or not np.isfinite(a).all() or np.any(a[:,2:]<=0) or not np.isfinite(t).all() or np.any(np.diff(t)<=0) or np.any(np.diff(a[:,0]+a[:,2]/2)<=0):raise ValueError('Invalid ordered objects')
 if g.shape!=(2,2) or not np.isfinite(g).all() or np.linalg.norm(g[1]-g[0])<100:raise ValueError('Invalid row guide')
 row=join_fragments(row,n)
 if len(row)==n:
  boxes=[b for t,b in row]
  if irregular(boxes) or endpoint_missing(boxes,guide):raise ValueError('Inconsistent row geometry')
  return row
 if len(row)<n or len(row)>n+4:raise ValueError('Unbounded row assignment')
 candidates=[]
 for ids in itertools.combinations(range(len(row)),n):
  selected=[row[j] for j in ids];boxes=np.array([b for t,b in selected],float)
  if irregular(boxes) or endpoint_missing(boxes,guide):continue
  x=boxes[:,0]+boxes[:,2]/2;y=boxes[:,1]+boxes[:,3]/2;h=boxes[:,3]
  ht=np.polyfit(x,h,1);intact=h>np.polyval(ht,x)*.85
  if intact.sum()<5:continue
  line=np.polyfit(x[intact],y[intact],1);residual=np.abs(y-np.polyval(line,x))/np.maximum(h,1)
  gap=np.diff(x);k=np.arange(len(gap));trend=np.exp(np.polyval(np.polyfit(k,np.log(gap),2),k))
  score=float(np.mean(residual)+np.mean(np.abs(np.log(gap/trend))))
  candidates.append((score,ids,selected))
 if not candidates:raise ValueError('No geometrically consistent assignment')
 candidates.sort(key=lambda v:v[0])
 # Don't hide near-tied assignments behind rank matching.
 if len(candidates)>1 and candidates[1][0]-candidates[0][0]<.015:raise ValueError('Ambiguous geometric assignment')
 return candidates[0][2]

def join_fragments(row,n):
 # Join vertically overlapping short fragments only when their combined
 # width is bounded by the median object height. Rank-independent.
 if len(row)>n:
  typical=float(np.median([b[3] for t,b in row]));merged=[];j=0
  while j<len(row):
   t,p=row[j]
   if j+1<len(row):
    u,q=row[j+1];gap=q[0]-p[0]-p[2];overlap=min(p[1]+p[3],q[1]+q[3])-max(p[1],q[1]);width=q[0]+q[2]-p[0]
    if 0<=gap<=typical*.25 and max(p[3],q[3])<typical*.75 and overlap>=min(p[3],q[3])*.5 and width<typical*1.3:
     left=min(p[0],q[0]);top=min(p[1],q[1]);right=max(p[0]+p[2],q[0]+q[2]);bottom=max(p[1]+p[3],q[1]+q[3]);merged.append(((t+u)/2,[left,top,right-left,bottom-top]));j+=2;continue
   merged.append((t,p));j+=1
  row=merged
 return row
