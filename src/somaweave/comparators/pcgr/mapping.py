"""Offline transcript-model mapping helpers for frozen synthetic alleles.

Models are extracted from the staged VEP 113 cache, selecting MANE_Select in
the matching bundle's transcript cross-reference. This is not an HGVS parser:
only single-base protein substitutions/stops, contiguous in-frame deletions
and explicit c.- offsets are supported. Enumerate all possible substitutions;
require exactly one rather than silently selecting a recurrent hotspot. A
reference-residue mismatch is an error. Verify genomic REF against the staged
indexed FASTA independently and forward-annotate the constructed VCF with VEP.
Side-map entries remain pending_owner; frozen case fixtures are never changed.
"""
from __future__ import annotations

from itertools import product
import csv
import gzip
from pathlib import Path

_AMINO = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODONS = dict(zip(("".join(x) for x in product("TCAG", repeat=3)), _AMINO))


def select_mane(xref: Path, genes: set[str]) -> dict:
    selected = {}
    with gzip.open(xref, "rt") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            gene = row["symbol"]
            if gene in genes and "MANE_Select" in row["gencode_tag"].split("&"):
                if gene in selected and selected[gene]["ensembl_transcript_id_full"] != row["ensembl_transcript_id_full"]:
                    raise ValueError(f"multiple MANE Select transcripts for {gene}")
                selected[gene] = row
    if genes - selected.keys():
        raise ValueError("not every requested gene has a MANE Select transcript")
    return selected


def complement(seq: str) -> str:
    return seq.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def cds_to_genomic(model: dict, coordinate: int) -> int:
    """1-based CDS coordinate, or <=0 for upstream offsets; no intron inference."""
    strand = int(model["strand"])
    exons = sorted(model["exons"], key=lambda e: e["start"], reverse=strand == -1)
    cdna = int(model["coding_start"]) + coordinate - 1
    if cdna < 1:
        # Extend beyond the annotated 5' transcript end on its actual strand.
        boundary = exons[0]["start"] if strand == 1 else exons[0]["end"]
        return boundary + strand * (cdna - 1)
    for exon in exons:
        length = exon["end"] - exon["start"] + 1
        if cdna <= length:
            return exon["start"] + cdna - 1 if strand == 1 else exon["end"] - cdna + 1
        cdna -= length
    raise ValueError("CDS coordinate exceeds transcript model")


def protein_snv(model: dict, residue: int, reference_aa: str, alternate_aa: str) -> tuple[int, str, str]:
    cds = model["cds"]
    start = 3 * (residue - 1)
    codon = cds[start:start + 3]
    if CODONS.get(codon) != reference_aa:
        raise ValueError(f"reference residue mismatch: expected {reference_aa}{residue}, transcript has {CODONS.get(codon)}")
    choices = []
    for offset in range(3):
        for base in "ACGT":
            if base == codon[offset]:
                continue
            alt_codon = codon[:offset] + base + codon[offset + 1:]
            if CODONS[alt_codon] == alternate_aa:
                ref, alt = codon[offset], base
                if int(model["strand"]) == -1:
                    ref, alt = complement(ref), complement(alt)
                choices.append((cds_to_genomic(model, start + offset + 1), ref, alt))
    if len(choices) != 1:
        raise ValueError(f"protein label has {len(choices)} possible single-base alleles, not one")
    return choices[0]


def deletion_interval(model: dict, first: int, last: int, first_aa: str, last_aa: str) -> tuple[int, int, str]:
    if model["peptide"][first - 1] != first_aa or model["peptide"][last - 1] != last_aa:
        raise ValueError("deletion reference residue mismatch")
    positions = [cds_to_genomic(model, c) for c in range(3 * (first - 1) + 1, 3 * last + 1)]
    if max(positions) - min(positions) + 1 != len(positions):
        raise ValueError("deletion spans an intron; cannot export as contiguous genomic deletion")
    seq = model["cds"][3 * (first - 1):3 * last]
    return min(positions), max(positions), seq if int(model["strand"]) == 1 else complement(seq)
