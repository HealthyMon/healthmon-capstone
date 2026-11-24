import csv
import tempfile
import unittest
from pathlib import Path
from fpb_weight import attach
from food2k import FoodTable, DEFAULT_CSV


def prediction(boxes, grams=100):
    return {'image_size':{'width':100,'height':100},'foods':[
        {'id':i,'bbox_xyxy':box,'weight_g':grams,'class_id':0,'name':'FPB food','confidence':.8}
        for i,box in enumerate(boxes)]}


class WeightContracts(unittest.TestCase):
    def test_exact_matches_keep_food_names(self):
        boxes = [[0,0,40,40],[60,60,100,100]]
        payload = prediction(boxes)
        payload['foods'][0]['name'] = 'Food2K name'
        attach(payload,prediction(boxes,125))
        self.assertEqual([f['weight_g'] for f in payload['foods']],[125,125])
        self.assertEqual(payload['foods'][0]['name'],'Food2K name')

    def test_one_weight_cannot_cover_two_foods(self):
        payload = prediction([[0,0,50,100],[50,0,100,100]])
        attach(payload,prediction([[0,0,100,100]],300))
        self.assertTrue(all(f['weight_g'] is None for f in payload['foods']))
        self.assertTrue(all(f['weight_status']=='ambiguous_weight_match' for f in payload['foods']))

    def test_ambiguous_multiple_weights(self):
        payload = prediction([[0,0,100,100]])
        attach(payload,prediction([[0,0,100,100],[5,5,100,100]]))
        self.assertIsNone(payload['foods'][0]['weight_g'])

    def test_empty_invalid_and_misaligned(self):
        payload = prediction([[0,0,40,40]])
        attach(payload,prediction([]))
        self.assertIsNone(payload['foods'][0]['weight_g'])
        attach(payload,prediction([[0,0,40,40]],-10))
        self.assertEqual(payload['foods'][0]['weight_status'],'invalid_weight_prediction')
        bad = prediction([])
        bad['image_size']['width'] = 200
        with self.assertRaises(ValueError):attach(payload,bad)
        attach(prediction([]),prediction([]))

    def test_csv_explicit_indices_override_row_order(self):
        with DEFAULT_CSV.open(encoding='utf-8-sig',newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows[0]['noisyvit_prediction_index'],rows[1]['noisyvit_prediction_index'] = '1','0'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mapping.csv'
            with path.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=rows[0].keys())
                writer.writeheader();writer.writerows(reversed(rows))
            table = FoodTable(path)
            self.assertEqual(table.candidate(0,.9)['class_id'],1)
            self.assertEqual(table.candidate(1,.9)['class_id'],0)
            with self.assertRaises(ValueError):FoodTable(path,order='numeric')


if __name__=='__main__':unittest.main()
