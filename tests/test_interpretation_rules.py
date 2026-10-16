"""Rule-table tests for somaweave.interpretation (synthetic records, no network)."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from somaweave.domain import (
    AnalyticalReliability,
    Case,
    DiseaseMatch,
    EvidenceRecord,
    MatchSpecificity,
    SourceQuery,
    SourceQueryResult,
    SourceStatus,
)
from somaweave.domain.io import load_case
from somaweave.evidence import reconcile
from somaweave.interpretation import actionability_tier_for, interpret
from somaweave.interpretation.interpret import assess_analytical
from somaweave.normalization import normalize_case
from somaweave.retrieval import RetrievalResult, build_query_plan
from somaweave.technical import assess_alteration

ROOT = Path(__file__).resolve().parents[1]
RULES = json.loads((ROOT / "tests" / "fixtures" / "interpretation" / "rule_records.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _luad_case() -> Case:
    """Synthetic lung adenocarcinoma case built from the example: EGFR G719S (A2) in LUAD, erlotinib given before the biopsy."""
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    data = case.model_dump(mode="json", exclude_none=True)
    data["diagnosis"].update({"name": "Lung Adenocarcinoma", "oncotree_code": "LUAD", "icd_o_morphology": "8140/3", "primary_site": "lung"})
    data["disease_hypotheses"] = []
    data["treatments"] = [{"treatment_id": "TX1", "name": "Erlotinib", "agents": ["Erlotinib"], "start_date": "2025-01-10", "end_date": "2025-06-01"}]
    data["alterations"] = [a for a in data["alterations"] if a["alteration_id"] == "A2"]
    return Case.model_validate(data)


def _records(*names, **overrides):
    out = []
    for n in names:
        payload = dict(RULES[n])
        payload.update(overrides.get(n, {}))
        out.append(EvidenceRecord.model_validate(payload))
    return out


def _retrieval(case, alt, records, statuses=None):
    """RetrievalResult with one query result per (source, tier) in ``statuses`` (default: all OK/NO_RECORDS)."""
    statuses = statuses or {("civic", "exact_variant"): SourceStatus.OK, ("clinvar", "exact_variant"): SourceStatus.OK,
                            ("europepmc", "exact_variant"): SourceStatus.NO_RECORDS}
    qrs = []
    for (src, tier), st in statuses.items():
        ids = [r.evidence_id for r in records if r.source_name == src and r.query_tier.value == tier]
        qrs.append(SourceQueryResult(query=SourceQuery(source_name=src, tier=MatchSpecificity(tier)), status=st, retrieved_at=NOW,
                                     record_count=len(ids), evidence_ids=ids))
    return RetrievalResult(case_id=case.case_id, alteration_id=alt.alteration_id, started_at=NOW, finished_at=NOW,
                           plan=build_query_plan(case, alt), query_results=qrs, evidence=records)


def _interpret(records, statuses=None):
    case = _luad_case()
    alt = case.alterations[0]
    nc = normalize_case(case)
    es = reconcile(nc, alt, _retrieval(case, alt, records, statuses))
    return interpret(nc, alt, assess_alteration(case, alt), es), es


class TierTableTests(unittest.TestCase):
    def test_tier_function(self):
        E = MatchSpecificity.EXACT_VARIANT
        self.assertEqual(actionability_tier_for(DiseaseMatch.SAME, "A", E)[0], "I")
        self.assertEqual(actionability_tier_for(DiseaseMatch.SAME, "B", E)[0], "I")
        self.assertEqual(actionability_tier_for(DiseaseMatch.SAME, "C", E)[0], "II")
        self.assertEqual(actionability_tier_for(DiseaseMatch.SAME, "D", E)[0], "III")
        self.assertEqual(actionability_tier_for(DiseaseMatch.PARENT, "A", E)[0], "II")
        self.assertEqual(actionability_tier_for(DiseaseMatch.PARENT, "C", E)[:2], ("III", True))
        self.assertEqual(actionability_tier_for(DiseaseMatch.DIFFERENT, "A", E)[:2], ("III", True))
        self.assertEqual(actionability_tier_for(DiseaseMatch.PAN_CANCER, "A", E)[:2], ("III", True))
        self.assertEqual(actionability_tier_for(DiseaseMatch.UNKNOWN, "A", E)[:2], ("III", False))
        self.assertEqual(actionability_tier_for(DiseaseMatch.SAME, "A", MatchSpecificity.GENE)[0], "III")


class ActionabilityTests(unittest.TestCase):
    def test_tier_one_same_disease_level_a(self):
        fa, _ = _interpret(_records("same_disease_level_A_sensitivity"))
        self.assertEqual(fa.actionability.tier, "I")
        self.assertEqual(fa.actionability.level, "A")
        self.assertEqual(fa.actionability.disease_match, DiseaseMatch.SAME)
        self.assertFalse(fa.actionability.cross_cancer_extrapolation)
        self.assertTrue(any(t.startswith("Afatinib") for t in fa.actionability.therapies))
        self.assertEqual(fa.relevance.level, "high")
        self.assertTrue(all(r.rstrip().endswith("]") for r in fa.actionability.rationale))

    def test_resistance_listed_separately(self):
        fa, _ = _interpret(_records("same_disease_level_B_resistance"))
        self.assertEqual(fa.actionability.tier, "I")
        self.assertEqual(fa.actionability.therapies, [])
        self.assertTrue(fa.actionability.resistance_to[0].startswith("Erlotinib"))
        # erlotinib was given before the biopsy: chronology linked
        self.assertTrue(fa.relevance.treatment_context)
        self.assertIn("days after the end of Erlotinib", fa.relevance.treatment_context[0])

    def test_parent_disease_tiers(self):
        fa, _ = _interpret(_records("parent_disease_level_B"))
        self.assertEqual(fa.actionability.tier, "II")
        fa, _ = _interpret(_records("parent_disease_level_C"))
        self.assertEqual(fa.actionability.tier, "III")
        self.assertTrue(fa.actionability.cross_cancer_extrapolation)

    def test_different_disease_is_tier_three_extrapolation(self):
        fa, _ = _interpret(_records("different_disease_level_A"))
        self.assertEqual(fa.actionability.tier, "III")
        self.assertTrue(fa.actionability.cross_cancer_extrapolation)
        self.assertIn("best actionability evidence is a cross-cancer extrapolation", fa.review_flags)
        self.assertEqual(fa.relevance.level, "low")

    def test_same_disease_lower_levels(self):
        self.assertEqual(_interpret(_records("same_disease_level_C"))[0].actionability.tier, "II")
        self.assertEqual(_interpret(_records("same_disease_level_D"))[0].actionability.tier, "III")

    def test_submitted_evidence_is_hypothesis_not_tier(self):
        fa, _ = _interpret(_records("submitted_level_A"))
        self.assertEqual(fa.actionability.tier, "IV")
        self.assertEqual(fa.established_claims, [])
        self.assertTrue(fa.hypotheses and fa.hypotheses[0].endswith("[hypothesis]"))

    def test_conflict_detected_and_flagged(self):
        fa, es = _interpret(_records("same_disease_level_A_sensitivity", "same_disease_level_A_resistance_conflict"))
        self.assertEqual(len(es.conflicts), 1)
        self.assertTrue(any("conflict" in f for f in fa.review_flags))

    def test_gene_level_only_capped(self):
        fa, _ = _interpret(_records("gene_level_same_disease"))
        self.assertEqual(fa.actionability.tier, "III")
        self.assertEqual(fa.relevance.level, "moderate")

    def test_nothing_accepted_is_tier_four_when_queried(self):
        fa, _ = _interpret(_records("literature_hit"))
        self.assertEqual(fa.actionability.tier, "IV")
        self.assertEqual(fa.relevance.level, "none")


class OncogenicityTests(unittest.TestCase):
    def test_two_sources_exact_is_oncogenic(self):
        fa, _ = _interpret(_records("same_disease_level_A_sensitivity", "clinvar_oncogenic_exact"))
        self.assertEqual(fa.oncogenicity.classification, "oncogenic")
        self.assertIn("OS1", fa.oncogenicity.criteria_met)
        self.assertIn("OM3", fa.oncogenicity.criteria_met)

    def test_single_source_exact_is_likely(self):
        fa, _ = _interpret(_records("same_disease_level_A_sensitivity"))
        self.assertEqual(fa.oncogenicity.classification, "likely_oncogenic")

    def test_three_items_single_source_is_oncogenic_with_os3(self):
        fa, _ = _interpret(_records("same_disease_level_A_sensitivity", "same_disease_level_B_resistance", "same_disease_level_C"))
        self.assertEqual(fa.oncogenicity.classification, "oncogenic")
        self.assertIn("OS3", fa.oncogenicity.criteria_met)

    def test_codon_only_is_likely(self):
        fa, _ = _interpret(_records("codon_level_oncogenic"))
        self.assertEqual(fa.oncogenicity.classification, "likely_oncogenic")

    def test_benign_only_with_explicit_evidence(self):
        fa, _ = _interpret(_records("clinvar_benign_exact"))
        self.assertEqual(fa.oncogenicity.classification, "likely_benign")
        fa, _ = _interpret(_records("clinvar_benign_exact", "clinvar_oncogenic_exact"))
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")

    def test_no_criteria_clinvar_is_not_evidence(self):
        fa, _ = _interpret(_records("clinvar_no_criteria"))
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")

    def test_upstream_annotation_quoted_not_used(self):
        fa, _ = _interpret(_records("literature_hit"))
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")
        self.assertTrue(any("computational" in r for r in fa.oncogenicity.rationale))


class MissingSourceTests(unittest.TestCase):
    def test_all_missing_is_not_assessed_never_negative(self):
        statuses = {("civic", "exact_variant"): SourceStatus.UNAVAILABLE, ("clinvar", "exact_variant"): SourceStatus.NOT_QUERIED,
                    ("europepmc", "exact_variant"): SourceStatus.ERROR}
        fa, es = _interpret([], statuses)
        self.assertEqual(fa.oncogenicity.classification, "not_assessed")
        self.assertEqual(fa.actionability.tier, "not_assessed")
        self.assertEqual(fa.relevance.level, "not_assessable")
        text = " ".join(fa.established_claims + fa.hypotheses + fa.limitations + fa.oncogenicity.rationale + fa.actionability.rationale)
        self.assertNotIn("no evidence", text.lower())
        guard_free = text.lower().replace("must not be read as negative", "").replace("not negative", "")
        self.assertNotIn("negative", guard_free)
        self.assertNotIn("absent", guard_free)
        self.assertTrue(any(l.startswith("CIViC: missing evidence") for l in fa.limitations))
        self.assertTrue(any(l.startswith("ClinVar: missing evidence") for l in fa.limitations))
        self.assertTrue(any("missing" in f for f in fa.review_flags))

    def test_partial_missing_listed(self):
        statuses = {("civic", "exact_variant"): SourceStatus.OK, ("clinvar", "exact_variant"): SourceStatus.NO_CREDENTIALS,
                    ("europepmc", "exact_variant"): SourceStatus.NO_RECORDS}
        fa, _ = _interpret(_records("same_disease_level_A_sensitivity"), statuses)
        self.assertEqual(fa.actionability.tier, "I")
        self.assertTrue(any(l.startswith("ClinVar: missing evidence (no_credentials x1)") for l in fa.limitations))


class AnalyticalTests(unittest.TestCase):
    def test_worst_across_specimens(self):
        case = _luad_case()
        a = AnalyticalReliability(level="high", specimen_id="T1")
        b = AnalyticalReliability(level="low", specimen_id="T2", flags=["low_alt_reads"])
        worst = assess_analytical(case.alterations[0], [a, b])
        self.assertEqual(worst.level, "low")
        self.assertTrue(any("worst of 2" in r for r in worst.rationale))
        self.assertEqual(assess_analytical(case.alterations[0], []).level, "not_assessable")

    def test_claims_are_cited(self):
        fa, _ = _interpret(_records("same_disease_level_A_sensitivity", "clinvar_oncogenic_exact", "submitted_level_A"))
        self.assertTrue(fa.established_claims)
        for c in fa.established_claims:
            self.assertRegex(c, r"\[[^\[\]]+\]$")
        for h in fa.hypotheses:
            self.assertTrue(h.endswith("[hypothesis]"))


if __name__ == "__main__":
    unittest.main()
