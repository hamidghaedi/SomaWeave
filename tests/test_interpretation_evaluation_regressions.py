"""Regression tests for interpretation defects found in the real-case evaluation.

Synthetic records only; genes and profile shapes mirror the evaluation."""

import unittest
from datetime import datetime, timezone

from somaweave.domain import (
    Case, DiseaseReference, EvidenceCategory, EvidenceDirection, EvidenceRecord, MatchSpecificity, SourceQuery,
    SourceQueryResult, SourceStatus,
)
from somaweave.domain.io import load_case
from somaweave.evidence import reconcile
from somaweave.interpretation import interpret
from somaweave.interpretation.rules import amp_level_for
from somaweave.normalization import normalize_case
from somaweave.retrieval import RetrievalResult, build_query_plan
from somaweave.technical import assess_alteration
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _case(gene, hgvs_p, consequence, oncotree="LUAD", name="Lung Adenocarcinoma", hypotheses=None, atype="SNV"):
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    data = case.model_dump(mode="json", exclude_none=True)
    data["diagnosis"].update({"name": name, "oncotree_code": oncotree, "icd_o_morphology": "8140/3", "primary_site": "lung"})
    if oncotree is None:
        data["diagnosis"].pop("oncotree_code", None)
    data["disease_hypotheses"] = hypotheses or []
    alt = [a for a in data["alterations"] if a["alteration_id"] == "A1"][0]
    alt.update({"gene_symbol": gene, "hgvs_p": hgvs_p, "consequence": consequence, "alteration_type": atype})
    alt.pop("hgvs_c", None); alt.pop("position", None); alt.pop("annotations", None)
    data["alterations"] = [alt]
    return Case.model_validate(data)


def _rec(eid, source, desc, gene, cat, *, vm=MatchSpecificity.GENE, level=None, disease=None, drugs=(), direction=EvidenceDirection.SUPPORTS,
         status="accepted; significance=SENSITIVITYRESPONSE", conditions=None, limitations=(), tier=MatchSpecificity.GENE):
    return EvidenceRecord(evidence_id=eid, source_name=source, source_native_id=eid, retrieved_at=NOW, query_tier=tier, variant_match=vm,
                          gene_symbol=gene, variant_description=desc, evidence_category=cat, assertion=f"{desc} assertion", direction=direction,
                          drugs=list(drugs), source_native_level=level, source_native_status=status,
                          disease=DiseaseReference(name=disease) if disease else None, conditions=list(conditions or []), limitations=list(limitations))


def _run(case, records, extra_status=None):
    alt = case.alterations[0]
    statuses = {("civic", "exact_variant"): SourceStatus.OK, ("civic", "gene"): SourceStatus.OK, ("clinvar", "exact_variant"): SourceStatus.OK,
                ("oncokb", "exact_variant"): SourceStatus.OK, ("europepmc", "exact_variant"): SourceStatus.NO_RECORDS}
    statuses.update(extra_status or {})
    qrs = []
    for (src, tier), st in statuses.items():
        ids = [r.evidence_id for r in records if r.source_name == src and r.query_tier.value == tier]
        qrs.append(SourceQueryResult(query=SourceQuery(source_name=src, tier=MatchSpecificity(tier)), status=st, retrieved_at=NOW,
                                     record_count=len(ids), evidence_ids=ids))
    rr = RetrievalResult(case_id=case.case_id, alteration_id=alt.alteration_id, started_at=NOW, finished_at=NOW,
                         plan=build_query_plan(case, alt), query_results=qrs, evidence=records)
    nc = normalize_case(case)
    es = reconcile(nc, alt, rr)
    return interpret(nc, alt, assess_alteration(case, alt), es), es


class EvaluationRegressionTests(unittest.TestCase):
    def test_setd2_truncating_class_level_oncokb_gives_ovs1_likely_oncogenic(self):
        case = _case("SETD2", "p.Thr305AsnfsTer4", "frameshift_variant", atype="insertion")
        rec = _rec("oncokb:SETD2:T305Nfs*4:oncogenic:0", "oncokb", "SETD2 Truncating Mutations (class-level annotation for T305Nfs*4)", "SETD2",
                   EvidenceCategory.ONCOGENIC, vm=MatchSpecificity.GENE_ALTERATION_CLASS, status="Likely Oncogenic",
                   limitations=["oncokb_variant_not_curated (variantExist=false)", "oncokb_class_level_annotation"], tier=MatchSpecificity.EXACT_VARIANT)
        fa, es = _run(case, [rec])
        self.assertIn(rec.evidence_id, es.accepted_ids)
        self.assertEqual(fa.oncogenicity.classification, "likely_oncogenic")
        self.assertIn("OVS1", fa.oncogenicity.criteria_met)

    def test_truncating_class_evidence_does_not_apply_to_missense(self):
        case = _case("SETD2", "p.Arg123Cys", "missense_variant")
        rec = _rec("oncokb:SETD2:R123C:oncogenic:0", "oncokb", "SETD2 Truncating Mutations (class-level annotation for R123C)", "SETD2",
                   EvidenceCategory.ONCOGENIC, vm=MatchSpecificity.GENE_ALTERATION_CLASS, status="Likely Oncogenic", tier=MatchSpecificity.EXACT_VARIANT)
        fa, es = _run(case, [rec])
        self.assertNotIn(rec.evidence_id, es.accepted_ids)
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")

    def test_vus_with_many_gene_level_other_cancer_therapies_gets_no_therapies(self):
        case = _case("EGFR", "p.Pro1033Leu", "missense_variant", oncotree="PAAD", name="Pancreatic Adenocarcinoma")
        records = []
        for i in range(70):
            desc = ["EGFR L858R", "EGFR T790M", "EGFR Exon 19 Deletion", "EGFR Mutation", "EGFR Amplification"][i % 5]
            records.append(_rec(f"civic:eid:{1000+i}", "civic", desc, "EGFR", EvidenceCategory.PREDICTIVE, level="A", disease="Lung Non-small Cell Carcinoma",
                                drugs=[f"drug{i % 9}"]))
        fa, es = _run(case, records)
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")
        self.assertEqual(fa.actionability.therapies, [])
        self.assertEqual(fa.actionability.resistance_to, [])
        # gene-wide ('EGFR Mutation') and region ('Exon 19 Deletion') records remain as gene-level context -> tier III cap
        self.assertEqual(fa.actionability.tier, "III")
        self.assertTrue(any("gene-level clinical context" in r for r in fa.actionability.rationale))
        self.assertTrue(es.excluded_by_class.get("other_variant", 0) >= 28)
        self.assertTrue(es.excluded_by_class.get("copy_number", 0) >= 14)
        # rationale is summarised, not one line per record
        self.assertLess(len(fa.actionability.rationale), 12)

    def test_fusion_and_expression_records_do_not_tier_small_variants(self):
        case = _case("MAML3", "p.Arg123Cys", "missense_variant", oncotree="BRCA", name="Breast Carcinoma")
        records = [
            _rec("civic:eid:11590", "civic", "BCOR::CCNB3 Fusion OR BCOR::MAML3 Fusion", "MAML3", EvidenceCategory.DIAGNOSTIC, level="B", disease="Sarcoma",
                 status="accepted; significance=POSITIVE"),
            _rec("civic:eid:2972", "civic", "MAML3 EXPRESSION", "MAML3", EvidenceCategory.PROGNOSTIC, level="B", disease="Colorectal Cancer",
                 status="accepted; significance=POOR_OUTCOME"),
        ]
        fa, es = _run(case, records)
        self.assertEqual(fa.actionability.tier, "IV")
        self.assertIn("not a benign or negative classification", fa.actionability.rationale[0])
        self.assertEqual(sorted(es.excluded_by_class), ["expression", "fusion"])
        self.assertTrue(any("not applicable to this alteration" in h for h in fa.hypotheses))

    def test_oncokb_levels_map_to_amp_levels_and_tiers(self):
        self.assertEqual(amp_level_for("LEVEL_1"), "A")
        self.assertEqual(amp_level_for("LEVEL_3A"), "C")
        self.assertEqual(amp_level_for("LEVEL_4"), "D")
        self.assertEqual(amp_level_for("LEVEL_R1"), "A")
        case = _case("EGFR", "p.Leu858Arg", "missense_variant", oncotree="LUAD")
        rec = _rec("oncokb:EGFR:L858R:treatment:0", "oncokb", "EGFR L858R", "EGFR", EvidenceCategory.PREDICTIVE, vm=MatchSpecificity.EXACT_VARIANT,
                   level="LEVEL_1", drugs=["Osimertinib"], status="LEVEL_1", tier=MatchSpecificity.EXACT_VARIANT)
        rec = rec.model_copy(update={"disease": DiseaseReference(name="Lung Adenocarcinoma", oncotree_code="LUAD")})
        fa, _ = _run(case, [rec])
        self.assertEqual(fa.actionability.tier, "I")
        self.assertEqual(fa.actionability.level, "A")
        self.assertTrue(any(t.startswith("Osimertinib") for t in fa.actionability.therapies))

    def test_multi_condition_record_matches_non_first_condition_and_hypothesis_summary(self):
        hyp = [{"name": "Solid pseudopapillary neoplasm of the pancreas", "oncotree_code": "SPN",
                "rationale": "morphology 8453/3 recorded vs 8452/3 expected for SPN; pathology reconciliation required", "proposed_by": "record review"}]
        case = _case("CTNNB1", "p.Asp32Asn", "missense_variant", oncotree=None, name="Pancreatic tumour, morphology 8453/3", hypotheses=hyp)
        rec = _rec("clinvar:VCV1:clinical", "clinvar", "NM_001904.4(CTNNB1):c.94G>A (p.Asp32Asn)", "CTNNB1", EvidenceCategory.OTHER,
                   vm=MatchSpecificity.EXACT_VARIANT, level="criteria provided, single submitter", status="Tier I - Strong",
                   direction=EvidenceDirection.NOT_APPLICABLE, disease="Adamantinous craniopharyngioma",
                   conditions=[DiseaseReference(name="Adamantinous craniopharyngioma"), DiseaseReference(name="Hepatoblastoma"),
                               DiseaseReference(name="Solid pseudopapillary neoplasm of the pancreas", oncotree_code="SPN")],
                   limitations=["multiple_conditions:3"], tier=MatchSpecificity.EXACT_VARIANT)
        fa, es = _run(case, [rec])
        # confirmed code is None -> UNKNOWN against the confirmed diagnosis, but SPN hypothesis matches the third condition
        self.assertEqual(es.hypothesis_disease_matches[rec.evidence_id]["SPN"].value, "same_disease")
        self.assertEqual(es.hypothesis_match_summary["SPN"]["same_disease"], 1)
        self.assertTrue(any("hypothesis-dependent relevance" in r for r in fa.relevance.rationale))
        self.assertTrue(any("8453/3" in u for u in fa.relevance.unresolved_questions))
        self.assertNotIn(fa.relevance.level, ("high", "moderate"))

    def test_planner_pseudo_source_never_reported_missing(self):
        case = _case("KRAS", "p.Gly12Asp", "missense_variant")
        fa, es = _run(case, [], extra_status={("planner", "pathway"): SourceStatus.NOT_QUERIED})
        self.assertEqual(es.missing_sources(), [])
        self.assertFalse(any("planner" in l for l in fa.limitations))
        self.assertFalse(any("planner" in f for f in fa.review_flags))


if __name__ == "__main__":
    unittest.main()
