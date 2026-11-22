import unittest
from fastapi.testclient import TestClient
from unity_api import app, nutrients, catalog


class UnityApiContracts(unittest.TestCase):
    def test_missing_not_zero(self):
        n=nutrients({'energy_kcal_100g':'0','fat_g_100g':''})
        self.assertTrue(n['has_calories']);self.assertEqual(n['calories'],0)
        self.assertFalse(n['has_fat'])
    def test_catalog(self):
        rows=catalog()
        self.assertEqual(len(rows),2000)
        self.assertEqual(len({r['class_id'] for r in rows}),2000)
        rice=next(r for r in rows if r['class_id']==108)
        self.assertEqual(rice['name'],'White rice')
    def test_http_validation(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').json()['schema_version'],1)
            self.assertTrue(client.get('/vision/catalog?q=White%20rice').json()['items'])
            self.assertEqual(client.post('/vision/analyze',files={'image':('bad.jpg',b'bad','image/jpeg')}).status_code,400)
            self.assertEqual(client.post('/vision/analyze',files={'image':('empty.jpg',b'','image/jpeg')}).status_code,400)


if __name__=='__main__':unittest.main()
