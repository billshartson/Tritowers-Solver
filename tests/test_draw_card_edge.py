"""Synthetic crop ownership cases, not photo accuracy claims."""
import unittest
import cv2
import numpy as np
from tritowers_vision.draw_ownership import owned as guarded,paired

class EdgeGuardTests(unittest.TestCase):
 def scene(self, rect):
  im=np.full((140,600,3),240,np.uint8)
  boxes=np.array([[50+j*100,45,22,40] for j in range(5)])
  for x,y,w,h in boxes:
   cv2.rectangle(im,(x,y),(x+8,y+h-1),(20,20,20),-1)
  if rect:
   x,y,w,h=rect;cv2.rectangle(im,(x,y),(x+w-1,y+h-1),(20,20,20),-1)
  return im,boxes
 def compare(self,rect):
  im,b=self.scene(None);a,ma=guarded(im,b,[5]);im,b=self.scene(rect);c,mc=guarded(im,b,[5]);return a,c,ma,mc
 def test_thin_edge_extending_below_band_removed(self):
  a,c,ma,mc=self.compare((71,48,5,43))
  self.assertEqual(len(mc[0]['kept']),1)
  self.assertTrue(np.array_equal(a[0],c[0]))
 def test_detached_horizontal_crossbar_preserved(self):
  a,c,ma,mc=self.compare((68,65,12,4))
  self.assertEqual(len(mc[0]['kept']),2);self.assertFalse(np.array_equal(a[0],c[0]))
 def test_rooted_thin_vertical_stroke_preserved(self):
  a,c,ma,mc=self.compare((68,48,5,43))
  self.assertEqual(len(mc[0]['kept']),2);self.assertFalse(np.array_equal(a[0],c[0]))
 def test_short_thin_vertical_stroke_preserved(self):
  a,c,ma,mc=self.compare((71,48,5,40))
  self.assertEqual(len(mc[0]['kept']),2);self.assertFalse(np.array_equal(a[0],c[0]))
 def test_wide_detached_component_preserved(self):
  a,c,ma,mc=self.compare((70,48,10,43))
  self.assertEqual(len(mc[0]['kept']),2);self.assertFalse(np.array_equal(a[0],c[0]))
 def test_clean_main_strokes_unchanged(self):
  a,c,ma,mc=self.compare(None)
  self.assertTrue(all(np.array_equal(x,y) for x,y in zip(a,c)))
 def test_neighbor_owned_ink_unchanged(self):
  a,c,ma,mc=self.compare((71,48,5,43))
  self.assertTrue(all(np.array_equal(x,y) for x,y in zip(a[1:],c[1:])))
 def test_blank_image_empty(self):
  im,b=self.scene(None);im[:]=240
  c,m=guarded(im,b,[5]);self.assertTrue(all(not np.any(v) for v in c))
 def test_soft_hard_edge_removal_matches_clean(self):
  clean,b=self.scene(None);edge,_=self.scene((71,48,5,43))
  a=paired(clean,b,[5]);c=paired(edge,b,[5])
  self.assertTrue(all(np.array_equal(x,y) for u,v in zip(a,c) for x,y in zip(u,v)))
 def test_no_rank_or_acceptance_output(self):
  im,b=self.scene((71,48,5,43));_,m=guarded(im,b,[5])
  self.assertTrue(all(set(v)=={'bounds','kept','box'} for v in m))
 def test_detected_thin_rank_not_removed(self):
  im,b=self.scene(None);b[:,2]=5
  im[:]=240
  for x,y,w,h in b:cv2.rectangle(im,(x,y),(x+w-1,y+h-1),(20,20,20),-1)
  c,m=guarded(im,b,[5]);self.assertTrue(all(np.any(v) for v in c))
if __name__=='__main__':unittest.main()
