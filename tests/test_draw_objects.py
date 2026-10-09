import unittest
import numpy as np,cv2
from tritowers_vision.draw_objects import detect
class TestDrawObjects(unittest.TestCase):
 def test_blank(self):
  _,rows=detect(np.full((200,800,3),220,np.uint8),[[(100,100),(700,100)]])
  self.assertEqual(rows,[[]])
 def test_synthetic_objects_and_seed_shift(self):
  im=np.full((220,900,3),230,np.uint8)
  for x in range(100,801,100):cv2.putText(im,'8',(x-15,120),cv2.FONT_HERSHEY_SIMPLEX,1.4,(20,20,20),3)
  _,a=detect(im,[[(100,100),(800,100)]]);_,b=detect(im,[[(100,130),(800,130)]])
  self.assertEqual(len(a[0]),8);self.assertEqual(a,b)
 def test_bad_image(self):
  with self.assertRaises(ValueError):detect(np.zeros((100,100)),[[(0,0),(200,0)]])
 def test_bad_guides(self):
  with self.assertRaises(ValueError):detect(np.zeros((200,800,3),np.uint8),[[(0,0),(float('nan'),100)]])
 def test_short_guide(self):
  with self.assertRaises(ValueError):detect(np.zeros((200,800,3),np.uint8),[[(0,0),(10,0)]])
if __name__=='__main__':unittest.main()
