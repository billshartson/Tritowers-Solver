import unittest,numpy as np
from tritowers_vision.draw_assignment import join_fragments,select
from tritowers_vision.geometry_rejection import irregular,endpoint_missing

def row():return [(float(x),[x,20,20,40]) for x in range(0,500,100)]
class JoinTests(unittest.TestCase):
 def fragment(self,p=None,q=None):
  a=row();a[2:3]=[(200.,p or [190,20,12,20]),(220.,q or [209,21,12,20])];return a
 def test_overlapping_short_halves_join(self):
  b=join_fragments(self.fragment(),5);self.assertEqual(len(b),5);self.assertEqual(b[2][1],[190,20,31,21])
 def test_gap_excludes_neighbour(self):self.assertEqual(len(join_fragments(self.fragment(q=[245,21,12,20]),5)),6)
 def test_tall_objects_not_joined(self):self.assertEqual(len(join_fragments(self.fragment(p=[190,20,12,40]),5)),6)
 def test_vertical_mismatch_not_joined(self):self.assertEqual(len(join_fragments(self.fragment(q=[209,50,12,20]),5)),6)
 def test_oversized_union_not_joined(self):self.assertEqual(len(join_fragments(self.fragment(p=[175,20,32,20],q=[209,20,30,20]),5)),6)
 def test_no_surplus_not_joined(self):
  a=self.fragment()[:-1];self.assertEqual(join_fragments(a,5),a)
 def test_union_preserves_row_order(self):
  b=join_fragments(self.fragment(),5);self.assertFalse(irregular([x[1] for x in b]));self.assertFalse(endpoint_missing([x[1] for x in b],[[10,40],[410,40]]))
 def test_missing_slot_with_surplus_ink_rejects(self):
  a=row();a.pop(2);a.insert(2,(150.,[145,70,10,15]));a.insert(3,(160.,[158,70,10,15]));
  with self.assertRaises(ValueError):select(a,5,[[10,40],[410,40]])
 def test_unbounded_surplus_rejects(self):
  a=row()+[(500.+j*100,[500+j*100,20,20,40]) for j in range(5)]
  with self.assertRaises(ValueError):select(a,5,[[10,40],[410,40]])
class CentreTests(unittest.TestCase):
 def test_recovered_centre_stays_between_measured_neighbours(self):
  for a,c in [(10,210),(30,180),(70,170)]:self.assertTrue(a<(a+c)/2<c)
 def test_no_label_dependence(self):
  from tritowers_vision.draw_ownership import owned
  im=np.full((140,600,3),240,np.uint8);boxes=np.array([[50+j*100,45,22,40] for j in range(5)]);boxes[2]=[260,55,12,20]
  import cv2
  for x,y,w,h in boxes:cv2.rectangle(im,(x,y),(x+w-1,y+h-1),(20,20,20),-1)
  v,m=owned(im,boxes,[5]);self.assertEqual(len(v),5);self.assertTrue(m[2]['bounds'][0]<250<m[2]['bounds'][2]);self.assertTrue(all(x.shape==(32,24) for x in v))
class ValidationTests(unittest.TestCase):
 def test_bad_count(self):
  for n in [True,5.5,4]:
   with self.assertRaises(ValueError):select(row(),n,[[10,40],[410,40]])
 def test_unordered_row(self):
  with self.assertRaises(ValueError):select(list(reversed(row())),5,[[10,40],[410,40]])
 def test_nonfinite_object(self):
  a=row();a[0]=(0.,[0,float('nan'),20,40])
  with self.assertRaises(ValueError):select(a,5,[[10,40],[410,40]])
 def test_short_guide(self):
  with self.assertRaises(ValueError):select(row(),5,[[10,40],[40,40]])
 def test_ownership_invalid_boxes(self):
  from tritowers_vision.draw_ownership import owned
  im=np.full((100,600,3),230,np.uint8)
  for b in [np.ones((4,4)),np.array([[-1,20,20,40]]*5),np.array([[590,20,20,40]]*5)]:
   with self.assertRaises(ValueError):owned(im,b,[5])
 def test_soft_hard_views_and_review_boundary(self):
  import cv2
  from tritowers_vision.draw_consensus import consensus
  from tritowers_vision.draw_ownership import paired
  from tritowers_vision.draw_matching import propose
  im=np.full((220,900,3),230,np.uint8)
  for x in range(100,801,100):cv2.putText(im,'8',(x-15,120),cv2.FONT_HERSHEY_SIMPLEX,1.4,(20,20,20),3)
  _,boxes=consensus(im,[[(100,100),(800,100)]],[8]);views=paired(im,boxes,[8]);self.assertEqual(len(views),8)
  result=propose(views[0],[('8',views[1])]);self.assertIsNone(result['rank']);self.assertFalse(result['accepted']);self.assertTrue(result['needs_visual_review'])
class ConsensusIsolationTests(unittest.TestCase):
 def test_mask_function_not_mutated_across_concurrent_reads(self):
  import cv2
  from concurrent.futures import ThreadPoolExecutor
  from tritowers_vision import draw_objects
  from tritowers_vision.draw_consensus import consensus
  original=draw_objects.ink_mask;im=np.full((220,900,3),230,np.uint8)
  for x in range(100,801,100):cv2.putText(im,'8',(x-15,120),cv2.FONT_HERSHEY_SIMPLEX,1.4,(20,20,20),3)
  def run(i):return consensus(im,[[(100,100),(800,100)]],[8])[1]
  with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,range(6)))
  self.assertIs(draw_objects.ink_mask,original)
  for boxes in results:self.assertTrue(np.array_equal(boxes,results[0]))
if __name__=='__main__':unittest.main()
