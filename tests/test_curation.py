import unittest,copy,numpy as np
from tritowers_vision.curation import digest,validate,bank
from tritowers_vision.curation_review import queue,apply_review
class Tests(unittest.TestCase):
 def setUp(self):
  self.data={'synthetic-a':[(np.eye(3,dtype=np.float32),'Ac'),(np.zeros((3,3),np.float32),'2d')],'synthetic-b':[(np.ones((3,3),np.float32),'3h')]}
  self.m={'schema_version':1,'samples':[{'photo_id':h,'slot_index':i,'card_label':l,'crop_sha256':digest(g),'reason':'blank' if not g.any() else 'clean','decision':'reject' if not g.any() else 'approve'}for h,items in self.data.items() for i,(g,l) in enumerate(items)]}
 def test_production_all_photos(self):self.assertEqual({s[2]for s in bank(self.data,self.m,'production')},set(self.data))
 def test_offline_separation(self):self.assertEqual({s[2]for s in bank(self.data,self.m,'offline_logo','synthetic-a')},{'synthetic-b'})
 def test_reject_filter(self):self.assertEqual(len(bank(self.data,self.m,'production')),2)
 def test_production_no_holdout(self):
  with self.assertRaises(ValueError):bank(self.data,self.m,'production','synthetic-a')
 def test_offline_requires_holdout(self):
  with self.assertRaises(ValueError):bank(self.data,self.m,'offline_logo')
 def test_stale(self):
  self.m['samples'][0]['crop_sha256']='bad'
  with self.assertRaises(ValueError):validate(self.data,self.m)
 def test_missing(self):
  self.m['samples'].pop()
  with self.assertRaises(ValueError):validate(self.data,self.m)
 def test_duplicate(self):
  self.m['samples'].append(self.m['samples'][0])
  with self.assertRaises(ValueError):validate(self.data,self.m)
 def test_changed_label(self):
  self.m['samples'][0]['card_label']='Kd'
  with self.assertRaises(ValueError):validate(self.data,self.m)
 def test_bad_reason(self):
  self.m['samples'][0]['reason']='high_confidence'
  with self.assertRaises(ValueError):validate(self.data,self.m)
 def test_all_queries_need_review(self):self.assertEqual({s['query_status'] for s in queue(self.data,self.m)},{'needs_visual_review'})
 def test_review_immutable(self):
  n=apply_review(self.data,self.m,'synthetic-a',0,self.m['samples'][0]['crop_sha256'],'partial');self.assertEqual(n['samples'][0]['decision'],'reject');self.assertEqual(self.m['samples'][0]['decision'],'approve')
 def test_stale_review(self):
  with self.assertRaises(ValueError):apply_review(self.data,self.m,'synthetic-a',0,'bad','clean')
if __name__=='__main__':unittest.main()
