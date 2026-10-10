"""Private data supplied by caller; geometric checks only reject, never accept."""
import cv2,numpy as np
from tritowers_vision.draw_objects import detect
from tritowers_vision.geometry_rejection import irregular,endpoint_missing

def crop(im,b):
 x,y,w,h=b;c=im[max(0,y-3):y+h+3,max(0,x-3):x+w+3];a=c.min(2).astype(np.float32)
 paper=cv2.dilate(a,np.ones((31,31),np.uint8));v=np.clip(1-a/(paper+1),0,1)
 # Trim the detector dilation, retaining glyph's own bounding box.
 yy,xx=np.where(v>.25)
 if not len(xx):return np.zeros((32,24),np.float32)
 v=v[yy.min():yy.max()+1,xx.min():xx.max()+1];hh,ww=v.shape;f=min(20/ww,28/hh);t=cv2.resize(v,(max(1,round(ww*f)),max(1,round(hh*f))))
 o=np.zeros((32,24),np.float32);y=(32-t.shape[0])//2;x=(24-t.shape[1])//2;o[y:y+t.shape[0],x:x+t.shape[1]]=t;return o

def component(im,b,thr=.30,pad=5):
 x,y,w,h=b;c=im[max(0,y-5):y+h+5,max(0,x-pad):x+w+pad];a=c.min(2).astype(np.float32);paper=cv2.dilate(a,np.ones((31,31),np.uint8));v=np.clip(1-a/(paper+1),0,1)
 m=(v>thr).astype(np.uint8);nc,L,st,cen=cv2.connectedComponentsWithStats(m)
 candidates=[i for i in range(1,nc) if st[i,3]>h*.4 and st[i,4]>15]
 if not candidates:return crop(im,b)
 i=min(candidates,key=lambda i:abs(cen[i,0]-(w/2+pad)));q=st[i];keep=[i]
 for j in range(1,nc):
  z=st[j];gap=max(z[0]-q[0]-q[2],q[0]-z[0]-z[2],0)
  if j!=i and z[4]>10 and gap<4 and abs(z[1]-q[1])<h*.6:keep.append(j)
 yy,xx=np.where(np.isin(L,keep));v=v[yy.min():yy.max()+1,xx.min():xx.max()+1];hh,ww=v.shape;f=min(20/ww,28/hh);t=cv2.resize(v,(max(1,round(ww*f)),max(1,round(hh*f))));o=np.zeros((32,24),np.float32);y=(32-t.shape[0])//2;x=(24-t.shape[1])//2;o[y:y+t.shape[0],x:x+t.shape[1]]=t;return o

def extract(image,row_guides,expected_counts,mask_fn=None):
 im,rows=detect(image,row_guides,mask_fn=mask_fn)
 counts=np.asarray(expected_counts)
 if counts.shape!=(len(rows),) or not np.issubdtype(counts.dtype,np.integer) or np.any(counts<5):raise ValueError('Invalid expected counts')
 views=[];meta=[]
 for r,row in enumerate(rows):
  n=int(counts[r]);p0,p1=[np.asarray(p,dtype=float) for p in row_guides[r]];u=p1-p0;u/=np.linalg.norm(u);normal=np.array([-u[1],u[0]])
  # Assign ordered objects using geometry, joining bounded short fragments.
  # Count matching cannot establish crop validity; every result needs visual review.
  from .draw_assignment import select
  row=select(row,n,row_guides[r])
  if len(row)!=n:raise ValueError('Row count mismatch')
  # Estimate full glyph vertical extent from intact tall objects, not fragment centres.
  centres=np.array([[b[0]+b[2]/2,b[1]+b[3]/2,b[3]] for t,b in row],float)
  xx=centres[:,0];hh=centres[:,2];trend=np.polyfit(xx,hh,1)
  intact=hh>np.polyval(trend,xx)*.85
  hfit=np.polyfit(xx[intact],hh[intact],1);yfit=np.polyfit(xx[intact],centres[intact,1],1)
  if irregular([b for t,b in row]) or endpoint_missing([b for t,b in row],row_guides[r]):raise ValueError('Inconsistent row geometry')
  for k,(t,b) in enumerate(row):
   x,y,w,bh=b;cx=x+w/2;H=np.polyval(hfit,cx);cy=np.polyval(yfit,cx)
   if bh<H*.72:
    W=max(w,H*.80);b=[int(cx-W/2),int(cy-H*.55),int(W),int(H*1.10)]
   views.append((crop(im,b),component(im,b)));meta.append({'row':r,'index':k,'box':b})
 return views,meta
