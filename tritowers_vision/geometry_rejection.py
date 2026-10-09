"""Geometric inconsistency only; passing this is not safe acceptance."""
import numpy as np

def irregular(boxes,threshold=.35):
 a=np.asarray(boxes,dtype=float)
 if a.ndim!=2 or a.shape[1]!=4 or not np.isfinite(a).all() or np.any(a[:,2:]<=0):return True
 x=a[:,0]+a[:,2]/2;gap=np.diff(x)
 if len(x)<5 or np.any(gap<=0):return True
 # Projective spacing changes smoothly. Isolated doubled/missing gaps violate this.
 k=np.arange(len(gap));trend=np.exp(np.polyval(np.polyfit(k,np.log(gap),2),k))
 return bool(np.max(np.abs(np.log(gap/trend)))>threshold)

def endpoint_missing(boxes,endpoints,tolerance=.75):
 """Reject absent end coverage; does not authenticate a selected rank."""
 a=np.asarray(boxes,dtype=float);p=np.asarray(endpoints,dtype=float)
 if a.ndim!=2 or a.shape[0]<5 or a.shape[1]!=4 or p.shape!=(2,2):return True
 if not np.isfinite(a).all() or not np.isfinite(p).all() or np.any(a[:,2:]<=0):return True
 axis=p[1]-p[0];length=np.linalg.norm(axis)
 if length<=0:return True
 axis/=length;centres=a[:,:2]+a[:,2:]/2;t=(centres-p[0])@axis;g=np.diff(t)
 if np.any(g<=0):return True
 return bool(abs(t[0])>tolerance*g[0] or abs(length-t[-1])>tolerance*g[-1])
