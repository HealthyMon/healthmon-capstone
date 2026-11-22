import unittest
from crop_weight_selection import select_weight
from fpb_weight import attach_crops


class CropWeightContracts(unittest.TestCase):
    def test_low_score_still_returns_regression(self):
        r=select_weight([[50,50,100,100,123,.001,.002]],[0,0,100,100])
        self.assertEqual(r['weight_g'],123)
        self.assertTrue(r['needs_weight_confirmation'])

    def test_whole_crop_preferred_over_small_fragment(self):
        r=select_weight([[50,50,100,100,200,.8,.1],[50,50,5,5,10,.99,.01]],[0,0,100,100])
        self.assertEqual(r['weight_g'],200)

    def test_invalid_regressions_not_invented(self):
        with self.assertRaises(RuntimeError):
            select_weight([[50,50,100,100,float('nan'),.9]],[0,0,100,100])

    def test_ids_not_position(self):
        p={'foods':[{'id':9,'name':'same food'},{'id':2,'name':'same food'}]}
        rows=[dict(id=i,weight_g=g,weight_status='estimated_fpb_crop',needs_weight_confirmation=False)
              for i,g in [(2,50),(9,100)]]
        attach_crops(p,{'foods':rows})
        self.assertEqual([r['weight_g'] for r in p['foods']],[100,50])
        with self.assertRaises(ValueError):attach_crops(p,{'foods':rows[:1]})
        attach_crops({'foods':[]},{'foods':[]})


if __name__=='__main__':unittest.main()
