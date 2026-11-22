import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from detect import detections
from prepare import read_split,write_split
from evaluate import match
from uec_regions import boxes_from_mask
import numpy as np

class MultiFoodTests(unittest.TestCase):
    def test_semantic_regions_keep_distant_same_class_foods(self):
        mask=np.zeros((100,160),dtype=np.uint8)
        mask[10:40,10:40]=1
        mask[10:40,100:130]=1
        self.assertEqual(boxes_from_mask(mask),[[10,10,40,40],[100,10,130,40]])

    def test_mask_speckle_not_a_food_box(self):
        mask=np.zeros((100,100),dtype=np.uint8)
        mask[10,10]=1
        self.assertEqual(boxes_from_mask(mask),[])

    def test_evaluation_does_not_count_same_target_twice(self):
        foods=[{'bbox_xyxy':[0,0,10,10],'class_id':0,'confidence':.9}]*2
        self.assertEqual(match(foods,[{'box':[0,0,10,10],'class_id':0}]),1)
        self.assertEqual(match(foods,[{'box':[0,0,10,10],'class_id':1}]),0)
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

    def test_coco_remapping_and_grid_boxes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            images=[]
            annotations=[]
            for i in range(4):
                Image.new('RGB',(100,50),(i*60,0,0)).save(root/f'{i}.png')
                images.append({'id':i,'file_name':f'{i}.png','width':100,'height':50})
                annotations.append({'id':i,'image_id':i,'category_id':19,'bbox':[10,5,20,10]})
            annotation=root/'labels.json'
            annotation.write_text(json.dumps({'images':images,'annotations':annotations,'categories':[{'id':19,'name':'b'}]}))
            records=read_split(annotation,root,['a','b'])
            self.assertEqual(records[0]['objects'][0]['category_id'],2)
            output=root/'out'
            output.mkdir()
            report=write_split(records,output,'train',['a','b'],grids=1)
            self.assertEqual(report['multi_object_images'],1)
            data=json.loads((output/'train.json').read_text())
            boxes=[x['bbox'] for x in data['annotations'] if x['image_id']==5]
            self.assertEqual(len(boxes),4)
            # No upscaling: 100x50 source centered in each 512 tile.
            self.assertEqual(boxes[0],[216,236,20,10])

    def test_unknown_labels_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'labels.json'
            p.write_text(json.dumps({'images':[],'annotations':[],'categories':[{'id':1,'name':'typo'}]}))
            with self.assertRaises(ValueError):
                read_split(p,td,['a'])

if __name__=='__main__':
    unittest.main()
