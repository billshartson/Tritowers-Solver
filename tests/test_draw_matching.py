import unittest,numpy as np
from tritowers_vision.draw_matching import propose
class TestDraftBoundary(unittest.TestCase):
 def glyph(self):
  a=np.zeros((32,24),np.float32);a[5:27,10:14]=1;return a
 def test_identical_is_unaccepted(self):
  g=self.glyph();p=propose((g,g),[('J',(g,g))]);self.assertEqual(p['candidate'],'J');self.assertIsNone(p['rank']);self.assertFalse(p['accepted']);self.assertTrue(p['needs_visual_review'])
 def test_empty_bank(self):self.assertIsNone(propose((self.glyph(),self.glyph()),[])['candidate'])
 def test_blank_abstains(self):
  g=np.zeros((32,24));self.assertIsNone(propose((g,g),[])['candidate'])
 def test_nonfinite_abstains(self):
  g=self.glyph();g[0,0]=np.nan;self.assertIsNone(propose((g,g),[])['candidate'])
 def test_constant_abstains(self):
  g=np.ones((32,24));self.assertIsNone(propose((g,g),[])['candidate'])
 def test_invalid_bank(self):
  g=self.glyph()
  with self.assertRaises(ValueError):propose((g,g),[('X',(g,g))])
 def test_wrong_shape_bank(self):
  g=self.glyph()
  with self.assertRaises(ValueError):propose((g,g),[('J',(np.zeros((24,32)),g))])
if __name__=='__main__':unittest.main()
