import unittest
from tritowers_vision.geometry_rejection import irregular,endpoint_missing
class TestGeometryRejection(unittest.TestCase):
 def setUp(self):
  self.boxes=[[i*100-10,-20,20,40] for i in range(14)];self.endpoints=[[0,0],[1300,0]]
 def test_regular_passes(self):
  self.assertFalse(irregular(self.boxes));self.assertFalse(endpoint_missing(self.boxes,self.endpoints))
 def test_internal_missing(self):self.assertTrue(irregular(self.boxes[:6]+self.boxes[7:]))
 def test_endpoint_missing(self):self.assertTrue(endpoint_missing(self.boxes[:-1],self.endpoints))
 def test_first_missing(self):self.assertTrue(endpoint_missing(self.boxes[1:],self.endpoints))
 def test_extra_duplicate(self):self.assertTrue(irregular(self.boxes[:6]+[self.boxes[5]]+self.boxes[6:]))
 def test_empty(self):self.assertTrue(endpoint_missing([],self.endpoints))
 def test_invalid_dimensions(self):self.assertTrue(endpoint_missing([[0,0,1,1]]*5,[[0,0]]))
 def test_nonfinite(self):
  b=[x[:] for x in self.boxes];b[1][0]=float('nan');self.assertTrue(endpoint_missing(b,self.endpoints))
 def test_bad_size(self):
  b=[x[:] for x in self.boxes];b[1][2]=0;self.assertTrue(endpoint_missing(b,self.endpoints))
 def test_guide_jitter(self):self.assertFalse(endpoint_missing(self.boxes,[[20,15],[1320,15]]))
if __name__=='__main__':unittest.main()
