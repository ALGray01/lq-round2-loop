import unittest

from memory_lab.retrieval import TfidfIndex


class TestTfidfIndex(unittest.TestCase):
    def test_ranks_relevant_doc_above_irrelevant(self):
        index = TfidfIndex([
            ("d1", "the statute of limitations for breach of contract is four years"),
            ("d2", "the client prefers morning meetings and drinks black coffee"),
        ])
        ranked = index.search("what is the statute of limitations", top_k=2)
        self.assertEqual(ranked[0][0], "d1")
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_empty_query_or_no_overlap_scores_zero(self):
        index = TfidfIndex([("d1", "hearing date is march first")])
        ranked = index.search("unrelated gibberish zzz", top_k=1)
        self.assertEqual(ranked[0][1], 0.0)


if __name__ == "__main__":
    unittest.main()
