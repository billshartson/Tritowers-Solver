"""Row-geometry foreground ownership. No ranks, scores or labels used."""
import cv2,numpy as np

def normalize(v):
 yy,xx=np.where(v>.25)
 if not len(xx):return np.zeros((32,24),np.float32)
 v=v[yy.min():yy.max()+1,xx.min():xx.max()+1];h,w=v.shape;f=min(20/w,28/h);t=cv2.resize(v,(max(1,round(w*f)),max(1,round(h*f))))
 out=np.zeros((32,24),np.float32);y=(32-t.shape[0])//2;x=(24-t.shape[1])//2;out[y:y+t.shape[0],x:x+t.shape[1]]=t;return out

def owned(image,boxes,counts,soft=False):
 image=np.asarray(image);boxes=np.asarray(boxes,dtype=float);counts=np.asarray(counts)
 if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:raise ValueError('Expected uint8 BGR image')
 if counts.ndim!=1 or not np.issubdtype(counts.dtype,np.integer) or np.any(counts<5):raise ValueError('Invalid row counts')
 if boxes.shape!=(int(counts.sum()),4) or not np.isfinite(boxes).all() or np.any(boxes[:,2:]<=0):raise ValueError('Invalid boxes')
 if np.any(boxes[:,:2]<0) or np.any(boxes[:,0]+boxes[:,2]>image.shape[1]) or np.any(boxes[:,1]+boxes[:,3]>image.shape[0]):raise ValueError('Boxes outside image')
 result=[];meta=[];offset=0
 for count in counts:
  row=np.asarray(boxes[offset:offset+count],float);offset+=count
  if np.any(np.diff(row[:,0]+row[:,2]/2)<=0):raise ValueError('Unordered row')
  cx=row[:,0]+row[:,2]/2;heights=row[:,3];trend=np.polyfit(cx,heights,1);intact=heights>np.polyval(trend,cx)*.85
  if intact.sum()<3:raise ValueError('Insufficient intact geometry')
  # Fragment centres are biased toward surviving ink. Recover their centre
  # from adjacent slot spacing, never from a rank or matching score.
  measured=cx.copy()
  for j in range(1,count-1):
   if not intact[j] and intact[j-1] and intact[j+1]:cx[j]=(measured[j-1]+measured[j+1])/2
  topfit=np.polyfit(cx[intact],row[intact,1],1);bottomfit=np.polyfit(cx[intact],(row[:,1]+heights)[intact],1)
  for j,(x,y,w,h) in enumerate(row):
   top=np.polyval(topfit,cx[j]);bottom=np.polyval(bottomfit,cx[j]);height=bottom-top
   # Neighbour halfway planes plus a tighter rank-width corridor prevent card text ownership.
   left=max((cx[j-1]+cx[j])/2 if j else 0,cx[j]-height*.65)
   right=min((cx[j]+cx[j+1])/2 if j+1<count else image.shape[1],cx[j]+height*.65)
   if height<=0:raise ValueError('Invalid fitted height')
   bounds=[int(max(0,left)),int(max(0,top-height*.12)),int(min(image.shape[1],right)),int(min(image.shape[0],bottom+height*.15))]
   l,t,r,b=bounds
   if r<=l or b<=t:raise ValueError('Empty ownership bounds')
   roi=image[t:b,l:r];a=roi.min(2).astype(np.float32)
   # Background estimate is bounded inside this slot, not influenced by the next card.
   paper=cv2.dilate(a,np.ones((31,31),np.uint8));v=np.clip(1-a/(paper+1),0,1)
   smooth=cv2.GaussianBlur(a,(31,31),0)
   foreground=((v>.25)&(a<smooth-20)).astype(np.uint8)
   n,L,st,cen=cv2.connectedComponentsWithStats(foreground)
   chosen=[]
   for k in range(1,n):
    sx,sy,sw,sh,area=st[k];gx=sx+l;gy=sy+t
    overlap=max(0,min(gx+sw,x+w)-max(gx,x))*max(0,min(gy+sh,y+h)-max(gy,y))
    # Only components rooted inside the geometric rank band; not a suit below it.
    if area>=4 and overlap>=min(area*.3,12) and gy+sh*.5<=bottom+height*.02:chosen.append(k)
   if chosen:
    largest=max(st[k,4] for k in chosen);chosen=[k for k in chosen if st[k,4]>=largest*.08]
   selected=np.isin(L,chosen)
   if soft:selected=cv2.dilate(selected.astype(np.uint8),np.ones((3,3),np.uint8))
   result.append(normalize(v*selected));meta.append({'bounds':bounds,'kept':chosen,'box':list(map(int,[x,y,w,h]))})
 return result,meta


def paired(image,boxes,counts):
 """Return soft/hard views of the same owned components, not accepted ranks."""
 hard,_=owned(image,boxes,counts)
 soft,_=owned(image,boxes,counts,soft=True)
 return list(zip(soft,hard))
