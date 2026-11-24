import unittest
from detect import detections

class RegionContractTests(unittest.TestCase):
    def test_same_food_on_two_plates_is_not_merged(self):
        result=detections([[[0,0,40,40,.9],[60,0,100,40,.8]]],['밥'],(100,100))
        self.assertEqual(len(result),2)
        self.assertEqual([r['id'] for r in result],[0,1])
        self.assertEqual(result[1]['bbox_normalized_xyxy'],[.6,0,1,.4])

    def test_competing_labels_at_same_location(self):
        raw=[[[0,0,40,40,.9]],[[0,0,40,40,.8]]]
        self.assertEqual(len(detections(raw,['a','b'],(100,100))),1)
        self.assertEqual(len(detections(raw,['a','b'],(100,100),duplicate_iou=1)),2)

    def test_invalid_and_empty_detections(self):
        self.assertEqual(detections([[]],['a'],(100,100)),[])
        self.assertEqual(detections([[[0,0,0,10,.9],[0,0,10,10,float('nan')]]],['a'],(100,100)),[])
