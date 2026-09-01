import unittest

from router.taxonomy import TASK_TYPE_WEIGHTS


class TestTaxonomyWeights(unittest.TestCase):
    def test_weights_sum_to_one_per_task_type(self):
        for task_type, weights in TASK_TYPE_WEIGHTS.items():
            with self.subTest(task_type=task_type):
                self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
