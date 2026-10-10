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
 def test_hash_shape_matters(self):
  a=np.arange(768,dtype=np.float32);self.assertNotEqual(digest(a.reshape(32,24)),digest(a.reshape(24,32)))
 def test_hash_dtype_matters(self):
  a=np.arange(4,dtype=np.float32).reshape(2,2);self.assertNotEqual(digest(a),digest(a.view(np.int32)))
 def test_hash_contiguous_layout_invariant(self):
  a=np.arange(12,dtype=np.float32).reshape(3,4).T;self.assertEqual(digest(a),digest(np.ascontiguousarray(a)))
 def test_hash_nonfinite_rejected(self):
  with self.assertRaises(ValueError):digest(np.array([[np.nan]]))
if __name__=='__main__':unittest.main()


def test_lucky_rank_match_never_counts_as_clean_localization():
    from tritowers_vision.curation_review import diagnostics
    data = {'synthetic-query': [(np.eye(3, dtype=np.float32), 'Ac'),
                                (np.fliplr(np.eye(3, dtype=np.float32)), '7h'),
                                (np.zeros((3, 3), np.float32), '2d')]}
    reasons = ['clean', 'wrong_neighbour', 'blank']
    manifest = {'schema_version': 1, 'samples': [
        {'photo_id': 'synthetic-query', 'slot_index': i, 'card_label': label,
         'crop_sha256': digest(glyph), 'reason': reasons[i],
         'decision': 'approve' if reasons[i] == 'clean' else 'reject'}
        for i, (glyph, label) in enumerate(data['synthetic-query'])]}
    predictions = {('synthetic-query', 0): 'K', ('synthetic-query', 1): '7', ('synthetic-query', 2): None}
    result = diagnostics(data, manifest, predictions)
    assert result['localization'] == {'clean': 1, 'wrong_neighbour': 1, 'blank': 1, 'partial': 0}
    assert result['matching']['clean_crops'] == {'correct': 0, 'wrong': 1, 'abstain': 0}
    assert result['matching']['visually_bad_crops'] == {'correct': 1, 'wrong': 0, 'abstain': 1}
    assert result['correct_on_bad_crops'] == 1 and result['query_status'] == 'needs_visual_review'
    assert all(sample['query_status'] == 'needs_visual_review' for sample in queue(data, manifest))
    assert len(bank(data, manifest, 'production')) == 1


def test_diagnostics_rejects_silent_omission_of_bad_queries():
    import pytest
    from tritowers_vision.curation_review import diagnostics
    fixture = Tests(); fixture.setUp()
    with pytest.raises(ValueError, match='every reviewed query'):
        diagnostics(fixture.data, fixture.m, {('synthetic-a', 0): 'A'})


def test_holdout_excludes_every_sample_from_query_photo():
    fixture = Tests(); fixture.setUp()
    fixture.m['samples'][1].update(reason='clean', decision='approve')
    approved = bank(fixture.data, fixture.m, 'production')
    training = bank(fixture.data, fixture.m, 'offline_logo', 'synthetic-a')
    assert len(approved) == 3 and len(training) == 1
    assert all(sample[2] != 'synthetic-a' for sample in training)


def test_manifest_identity_schema_and_labels_are_validated():
    import pytest
    for change in ({'slot_index': False}, {'slot_index': -1}, {'photo_id': []}, {'reason': []}):
        fixture = Tests(); fixture.setUp(); fixture.m['samples'][0].update(change)
        with pytest.raises(ValueError): validate(fixture.data, fixture.m)
    fixture = Tests(); fixture.setUp(); fixture.m['schema_version'] = 999
    with pytest.raises(ValueError, match='schema'): validate(fixture.data, fixture.m)
    fixture = Tests(); fixture.setUp()
    fixture.data['synthetic-a'][0] = (fixture.data['synthetic-a'][0][0], 'Xc')
    fixture.m['samples'][0]['card_label'] = 'Xc'
    with pytest.raises(ValueError, match='card label'): validate(fixture.data, fixture.m)
