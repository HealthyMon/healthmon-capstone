import unittest
from food2k import FoodTable, number, add_portions


class Food2KContracts(unittest.TestCase):
    def test_class_order_not_csv_row_position(self):
        table = FoodTable()
        self.assertEqual(table.ids[:5], [0, 1, 10, 100, 1000])
        candidate = table.candidate(table.ids.index(108), .9)
        self.assertEqual(candidate['class_id'], 108)
        self.assertEqual(candidate['name'], 'White rice')
        self.assertEqual(table.order, 'csv')
        with self.assertRaises(ValueError):
            FoodTable(order='numeric')

    def test_missing_is_not_zero(self):
        for value in ('', 'nan', 'inf', '-3', None):
            self.assertIsNone(number(value))
        self.assertEqual(number('0'), 0)

    def test_reference_review_and_units(self):
        table = FoodTable()
        self.assertTrue(table.nutrition(1)['review_required'])
        reference = table.nutrition(0)
        self.assertEqual(reference['basis_g'], 100)
        self.assertEqual(reference['per_100g']['energy_kcal_100g'], 212.8)
        self.assertTrue(reference['source'].endswith('noisyvit_food2k_nutrition_all2000.csv'))
        self.assertIsNotNone(reference['reference_confidence'])
        self.assertIsNone(reference['portion'])

    def test_weight_scaling_and_absent_weight(self):
        nutrition = FoodTable().nutrition(0)
        food = {'weight_g': None, 'nutrition': nutrition}
        payload = {'foods': [food]}
        add_portions(payload)
        self.assertIsNone(nutrition['portion'])
        food['weight_g'] = 50
        add_portions(payload)
        self.assertEqual(nutrition['portion']['values']['energy_kcal'], 106.4)
        self.assertEqual(nutrition['per_100g']['energy_kcal_100g'], 212.8)
        food['weight_g'] = None
        add_portions(payload)
        self.assertIsNone(nutrition['portion'])
        add_portions({'foods': []})


if __name__ == '__main__':
    unittest.main()
