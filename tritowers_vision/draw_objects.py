"""Object-first rank detector for a manually guided draw screen.
Source-only experimental path, not the tableau reader or automatic solver input.
"""
import cv2,numpy as np

def ink_mask(bgr):
    b,g,r=[bgr[...,i].astype(int) for i in range(3)]
    gray=(0.3*r+0.59*g+0.11*b)
    dark=gray<95
    red=(r>110)&(g<85)&(b<95)&(r-g>60)
    return (dark|red).astype(np.uint8)

def detect(image, row_guides):
 im=np.asarray(image)
 if im.ndim!=3 or im.shape[2]!=3 or im.dtype!=np.uint8 or not np.isfinite(im).all():raise ValueError('Expected uint8 BGR image')
 guides=np.asarray(row_guides,dtype=float)
 if guides.ndim!=3 or guides.shape[1:]!=(2,2) or not np.isfinite(guides).all():raise ValueError('Expected finite row guides')
 if np.any(np.linalg.norm(guides[:,1]-guides[:,0],axis=1)<100):raise ValueError('Row guide too short')
 m=ink_mask(im);gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
 bright=cv2.morphologyEx((gray>135).astype(np.uint8),cv2.MORPH_CLOSE,np.ones((25,25),np.uint8))
 m=m;m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((2,2),np.uint8));m=cv2.dilate(m,np.ones((3,9),np.uint8))
 nc,lab,st,cen=cv2.connectedComponentsWithStats(m);rows=[]
 for r,(p0,p1) in enumerate(guides):
  p0,p1=np.array(p0),np.array(p1);u=p1-p0;L=np.linalg.norm(u);u/=L;n=np.array([-u[1],u[0]])
  # Broad seed corridor; recover actual row line from tall rank objects.
  seed=[]
  for i in range(1,nc):
   x,y,w,hh,ar=st[i];c=np.array([x+w/2,y+hh/2]);t=(c-p0)@u;d=(c-p0)@n
   if 28<=hh<=90 and 8<=w<=100 and ar>120 and -30<t<L+30 and abs(d)<55 and w/hh>.3:seed.append(c)
  if len(seed)>=6:
   C=np.array(seed);best=None
   for a in range(len(C)):
    for b in range(a+1,len(C)):
     if abs(C[b,0]-C[a,0])<L*.4:continue
     slope=(C[b,1]-C[a,1])/(C[b,0]-C[a,0]);intercept=C[a,1]-slope*C[a,0]
     d=np.abs(C[:,1]-(slope*C[:,0]+intercept));mask=d<10;score=int(mask.sum())
     if best is None or score>best[0]:best=(score,mask)
   if best and best[0]>=6:
    slope,intercept=np.polyfit(C[best[1],0],C[best[1],1],1)
    p0=np.array([p0[0],slope*p0[0]+intercept]);p1=np.array([p1[0],slope*p1[0]+intercept]);u=p1-p0;L=np.linalg.norm(u);u/=L;n=np.array([-u[1],u[0]])
  row=[]
  for i in range(1,nc):
   x,y,w,hh,ar=st[i];c=np.array([x+w/2,y+hh/2]);t=(c-p0)@u;d=(c-p0)@n
   if 12<=hh<=90 and 8<=w<=100 and ar>85 and -30<t<L+30 and -22<d<22 and w/hh>.22:
    row.append((float(t),[int(x),int(y),int(w),int(hh)]))
  row.sort(); merged=[]
  for t,b in row:
   if merged:
    tq,q=merged[-1]
    overlap=min(q[0]+q[2],b[0]+b[2])-max(q[0],b[0])
    if (overlap>min(q[2],b[2])*.45 and abs((q[1]+q[3]/2)-(b[1]+b[3]/2))<45) or (0<=b[0]-q[0]-q[2]<=5 and max(q[3],b[3])<30 and abs(q[1]-b[1])<10):
     x=min(q[0],b[0]);y=min(q[1],b[1]);xx=max(q[0]+q[2],b[0]+b[2]);yy=max(q[1]+q[3],b[1]+b[3]);merged[-1]=((t+tq)/2,[x,y,xx-x,yy-y]);continue
   merged.append((t,b))
  rows.append(merged)
 return im,rows
