import unittest,numpy as np,cv2
from tritowers_vision.draw_extraction import extract
class TestExtraction(unittest.TestCase):
 def test_blank_stops(self):
  with self.assertRaises(ValueError):extract(np.full((220,900,3),230,np.uint8),[[(100,100),(800,100)]],[8])
 def test_synthetic_views(self):
  im=np.full((220,900,3),230,np.uint8)
  for x in range(100,801,100):cv2.putText(im,'8',(x-15,120),cv2.FONT_HERSHEY_SIMPLEX,1.4,(20,20,20),3)
  views,meta=extract(im,[[(100,100),(800,100)]],[8]);self.assertEqual(len(views),8)
  for a,b in views:self.assertEqual(a.shape,(32,24));self.assertEqual(b.shape,(32,24))
 def test_count_type(self):
  with self.assertRaises(ValueError):extract(np.full((220,900,3),230,np.uint8),[[(100,100),(800,100)]],[8.5])
