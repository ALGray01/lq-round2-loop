import unittest

from memory_lab.facts import Fact, FactStore


class TestFactStore(unittest.TestCase):
    def test_current_as_of_before_and_after_supersession(self):
        store = FactStore()
        f1 = Fact(
            fact_id="f1", matter_id="doe-v-roe", subject="hearing_date",
            predicate="is", object="2026-03-01", source="clerk email 1",
            valid_from="2026-01-01",
        )
        store.add(f1)

        # Before the correction, the original date is current.
        self.assertEqual(
            [f.object for f in store.current_as_of("doe-v-roe", "2026-01-15")],
            ["2026-03-01"],
        )

        f2 = Fact(
            fact_id="f2", matter_id="doe-v-roe", subject="hearing_date",
            predicate="is", object="2026-03-15", source="clerk email 2",
            valid_from="2026-01-20",
        )
        store.supersede("f1", f2, at_date="2026-01-20")

        # After the correction, only the new date is current...
        current = store.current_as_of("doe-v-roe", "2026-02-01")
        self.assertEqual([f.object for f in current], ["2026-03-15"])

        # ...but the old one is still true for a query dated before the fix,
        # which is the bitemporal property the whole design depends on.
        past = store.current_as_of("doe-v-roe", "2026-01-15")
        self.assertEqual([f.object for f in past], ["2026-03-01"])

    def test_compartments_never_mix(self):
        store = FactStore()
        store.add(Fact(
            fact_id="a1", matter_id="matter-a", subject="client_ssn_last4",
            predicate="is", object="1234", source="intake form",
            valid_from="2026-01-01",
        ))
        store.add(Fact(
            fact_id="b1", matter_id="matter-b", subject="client_ssn_last4",
            predicate="is", object="5678", source="intake form",
            valid_from="2026-01-01",
        ))
        self.assertEqual(len(store.current_as_of("matter-a", "2026-06-01")), 1)
        self.assertEqual(store.current_as_of("matter-a", "2026-06-01")[0].object, "1234")
        self.assertEqual(store.current_as_of("matter-b", "2026-06-01")[0].object, "5678")

    def test_supersede_rejects_cross_matter(self):
        store = FactStore()
        store.add(Fact(
            fact_id="a1", matter_id="matter-a", subject="x", predicate="is",
            object="1", source="s", valid_from="2026-01-01",
        ))
        bad = Fact(
            fact_id="b1", matter_id="matter-b", subject="x", predicate="is",
            object="2", source="s", valid_from="2026-01-02",
        )
        with self.assertRaises(ValueError):
            store.supersede("a1", bad, at_date="2026-01-02")


if __name__ == "__main__":
    unittest.main()
