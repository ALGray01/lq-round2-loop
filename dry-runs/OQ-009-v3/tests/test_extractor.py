from legal_memory.extractor import extract, split_sentences
from legal_memory.scenario import Session, build_sessions


class TestSplitSentences:
    def test_splits_on_sentence_boundaries(self):
        sentences = split_sentences(
            "This is the first sentence right here. This is a second sentence that follows."
        )
        assert sentences == [
            "This is the first sentence right here.",
            "This is a second sentence that follows.",
        ]

    def test_drops_short_fragments(self):
        # "Ok." is below MIN_SENTENCE_WORDS and should be dropped.
        sentences = split_sentences("This is a real sentence with enough words. Ok.")
        assert len(sentences) == 1

    def test_citation_abbreviation_breaks_sentence_splitting(self):
        # Documented, real limitation (see README): "v." in a case citation
        # is indistinguishable from a sentence-ending period to this regex.
        # (Both fragments here are deliberately >=4 words so MIN_SENTENCE_WORDS
        # doesn't also filter one out, which would mask the real finding.)
        sentences = split_sentences(
            "The appellate court decided Park v. Summit Carriers today in a written opinion."
        )
        assert len(sentences) == 2
        assert sentences[0].endswith("Park v.")


class TestMatterIsolation:
    def test_untagged_session_sentences_are_rejected_not_misfiled(self):
        sessions = [
            Session("s1", 1, None, "This untagged sentence should never be filed anywhere."),
        ]
        result = extract(sessions)
        assert result.candidates == []
        assert len(result.rejected_no_matter) == 1
        assert result.rejected_no_matter[0][0] == "s1"

    def test_whitespace_only_matter_id_is_rejected_not_accepted(self):
        # Second-audit-round finding: `if not session.matter_id` alone lets
        # a whitespace-only string through, the same bug class already
        # fixed in graph_store.py/compartment_store.py via require_matter_id().
        sessions = [
            Session("s1", 1, "   ", "This sentence has a whitespace-only matter_id tag on it."),
        ]
        result = extract(sessions)
        assert result.candidates == []
        assert len(result.rejected_no_matter) == 1

    def test_str_subclass_matter_id_is_rejected_not_accepted(self):
        # Third-audit-round finding: a str subclass passes `isinstance`
        # checks but can carry a lying __eq__ that would defeat the
        # `c.matter_id == session.matter_id` filter in extract() -- must be
        # rejected the same way graph_store.py/compartment_store.py reject it.
        class TaggedStr(str):
            pass

        sessions = [
            Session("s1", 1, TaggedStr("m1"), "This sentence has a str-subclass matter_id tag."),
        ]
        result = extract(sessions)
        assert result.candidates == []
        assert len(result.rejected_no_matter) == 1

    def test_tagged_session_sentences_are_accepted(self):
        sessions = [
            Session("s1", 1, "m1", "This tagged sentence should be filed under matter m1."),
        ]
        result = extract(sessions)
        assert len(result.candidates) == 1
        assert result.candidates[0].matter_id == "m1"
        assert result.rejected_no_matter == []

    def test_real_scenario_rejects_exactly_the_untagged_session(self):
        result = extract(build_sessions())
        rejected_sessions = {sid for sid, _ in result.rejected_no_matter}
        assert rejected_sessions == {"s06"}
        assert all(c.matter_id for c in result.candidates)


class TestSupersessionDetection:
    def test_dissimilar_sentences_are_not_linked(self):
        sessions = [
            Session("s1", 1, "m1", "The weather today is unusually warm for this time of year."),
            Session("s2", 2, "m1", "Quarterly revenue exceeded projections by twelve percent."),
        ]
        result = extract(sessions)
        assert all(c.supersedes is None for c in result.candidates)

    def test_near_identical_sentences_are_linked(self):
        sessions = [
            Session("s1", 1, "m1", "The statute of limitations for this claim is four years."),
            Session("s2", 2, "m1", "The statute of limitations for this claim is now three years."),
        ]
        result = extract(sessions)
        assert result.candidates[1].supersedes == result.candidates[0].candidate_id

    def test_supersession_never_crosses_matters(self):
        sessions = [
            Session("s1", 1, "m1", "The statute of limitations for this claim is four years."),
            Session("s2", 2, "m2", "The statute of limitations for this claim is now three years."),
        ]
        result = extract(sessions)
        assert all(c.supersedes is None for c in result.candidates)
