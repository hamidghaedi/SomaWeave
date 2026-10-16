"""Deterministic parsing of protein and coding HGVS expressions.

This module is a strict pattern parser, not a validator against a reference
sequence or transcript. It extracts structure (reference residue, position,
alternate residue, change kind) from well-formed HGVS strings and refuses
anything it cannot interpret unambiguously. Unparseable input yields
``(None, reason)``; the parser never guesses.

Supported protein forms (three- or one-letter residues, optional
``NP_...:`` prefix, optional prediction parentheses ``p.(...)``):
substitution, nonsense (``Ter``/``*``/``X``), synonymous (``=``),
frameshift (``fs``, ``fsTer12``, ``fs*12``, ``Pfs*12``), single-residue and
range ``del``/``dup``, ``ins`` and ``delins`` with a residue sequence or a
residue count, and start-loss ``Met1?``.

Supported coding/genomic forms (``c.``, ``n.``, ``g.`` prefix): substitution
``94G>A`` (including intronic/UTR offsets such as ``c.123+1G>A`` or
``c.*45A>G``), ``del``/``dup`` with or without explicit sequence, ``ins`` and
``delins``, and ``inv``.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ProteinChangeKind = Literal[
    "missense",
    "nonsense",
    "frameshift",
    "inframe_deletion",
    "inframe_insertion",
    "inframe_duplication",
    "delins",
    "synonymous",
    "start_loss",
    "other",
]

CodingChangeKind = Literal[
    "substitution",
    "deletion",
    "duplication",
    "insertion",
    "delins",
    "inversion",
    "other",
]

THREE_TO_ONE: dict[str, str] = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
    "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
    "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
    "Tyr": "Y", "Val": "V", "Sec": "U", "Pyl": "O", "Ter": "*", "Xaa": "X",
}
ONE_TO_THREE: dict[str, str] = {v: k for k, v in THREE_TO_ONE.items()}
# 'X' is accepted as a legacy stop symbol in one-letter notation.
ONE_TO_THREE_INPUT: dict[str, str] = dict(ONE_TO_THREE)
ONE_TO_THREE_INPUT["X"] = "Ter"

_THREE = "|".join(sorted(THREE_TO_ONE, key=len, reverse=True))
_ONE = "".join(sorted(set(ONE_TO_THREE_INPUT) - {"*"}))
# A residue token: three-letter code, or a single one-letter code, or '*'.
_RES = rf"(?:{_THREE}|[{_ONE}]|\*)"
_PREFIX = r"^(?:(?P<acc>[A-Z]{2}_\d+(?:\.\d+)?):)?p\.(?P<pred>\()?"
_SUFFIX = r"(?(pred)\))$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ParsedProteinChange(_Model):
    """Structured protein-level change with canonical renderings.

    ``ref_aa``/``alt_aa`` are three-letter codes (``Ter`` for stop). For
    ranges, ``end_ref_aa``/``end_position`` describe the last affected
    residue. ``codon_label`` is the one-letter reference residue joined to
    the start position (``D32``), which is the key used for codon-level
    evidence lookups.
    """

    original: str = Field(description="Input string exactly as supplied.")
    kind: ProteinChangeKind
    ref_aa: str = Field(description="Three-letter reference residue at the start position.")
    position: int = Field(ge=1)
    alt_aa: Optional[str] = Field(default=None, description="Three-letter alternate residue, if the change has one.")
    end_ref_aa: Optional[str] = None
    end_position: Optional[int] = Field(default=None, ge=1)
    inserted: Optional[str] = Field(default=None, description="Inserted residues (three-letter, concatenated) or a residue count as text.")
    frameshift_stop_offset: Optional[int] = Field(default=None, ge=1, description="Residues from the shifted frame to the new stop, if stated.")
    predicted: bool = Field(default=False, description="True if the input used p.(...) prediction parentheses.")
    accession: Optional[str] = Field(default=None, description="Protein accession prefix if present.")
    codon_label: str
    one_letter: str = Field(description="Canonical one-letter rendering, e.g. p.D32N.")
    three_letter: str = Field(description="Canonical three-letter rendering, e.g. p.Asp32Asn.")


class ParsedCodingChange(_Model):
    """Structured coding (``c.``), non-coding (``n.``) or genomic (``g.``) change."""

    original: str
    prefix: Literal["c", "n", "g"]
    kind: CodingChangeKind
    start: str = Field(description="Start position as written (may carry intronic/UTR offsets, e.g. '123+1' or '*45').")
    end: Optional[str] = None
    start_base: int = Field(description="Integer part of the start position; negative for 5' UTR.")
    end_base: Optional[int] = None
    reference: Optional[str] = Field(default=None, description="Deleted/replaced bases if stated.")
    alternate: Optional[str] = Field(default=None, description="Substituted or inserted bases if stated.")
    accession: Optional[str] = None


def _to_three(token: str) -> Optional[str]:
    if token in THREE_TO_ONE:
        return token
    return ONE_TO_THREE_INPUT.get(token)


def _seq_to_three(seq: str, three_letter_mode: bool) -> Optional[str]:
    """Convert a residue sequence ('AlaGly' or 'AG') to concatenated three-letter form."""
    if three_letter_mode:
        if len(seq) % 3:
            return None
        parts = [seq[i:i + 3] for i in range(0, len(seq), 3)]
        if any(p not in THREE_TO_ONE for p in parts):
            return None
        return "".join(parts)
    out = []
    for ch in seq:
        t = ONE_TO_THREE_INPUT.get(ch)
        if t is None:
            return None
        out.append(t)
    return "".join(out)


def _three_seq_to_one(seq: str) -> str:
    return "".join(THREE_TO_ONE[seq[i:i + 3]] for i in range(0, len(seq), 3))


def _render(kind: str, ref: str, pos: int, alt: Optional[str], end_ref: Optional[str], end_pos: Optional[int],
            inserted: Optional[str], fs_off: Optional[int], one: bool) -> str:
    def r(x: str) -> str:
        return THREE_TO_ONE[x] if one else x

    def seq(x: str) -> str:
        if x.isdigit():
            return x
        return _three_seq_to_one(x) if one else x

    span = f"{r(ref)}{pos}"
    if end_ref is not None and end_pos is not None:
        span += f"_{r(end_ref)}{end_pos}"
    if kind in ("missense", "nonsense"):
        body = f"{span}{r(alt or '')}"
    elif kind == "synonymous":
        body = f"{span}="
    elif kind == "start_loss":
        body = f"{span}?"
    elif kind == "frameshift":
        body = f"{span}{r(alt) if alt else ''}fs"
        if fs_off is not None:
            body += f"{'*' if one else 'Ter'}{fs_off}"
    elif kind == "inframe_deletion":
        body = f"{span}del"
    elif kind == "inframe_duplication":
        body = f"{span}dup"
    elif kind == "inframe_insertion":
        body = f"{span}ins{seq(inserted or '')}"
    elif kind == "delins":
        body = f"{span}delins{seq(inserted or '')}"
    else:
        body = span
    return f"p.{body}"


_P_SUBST = re.compile(_PREFIX + rf"(?P<ref>{_RES})(?P<pos>\d+)(?P<alt>{_RES}|=|\?)" + _SUFFIX)
_P_FS = re.compile(_PREFIX + rf"(?P<ref>{_RES})(?P<pos>\d+)(?P<alt>{_RES})?fs(?:(?:Ter|\*)(?P<off>\d+|\?))?" + _SUFFIX)
_P_RANGE = re.compile(
    _PREFIX
    + rf"(?P<ref>{_RES})(?P<pos>\d+)(?:_(?P<eref>{_RES})(?P<epos>\d+))?"
    + r"(?P<op>delins|del|dup|ins)(?P<seq>[A-Za-z]+|\d+)?"
    + _SUFFIX
)


def parse_protein_hgvs(text: Optional[str]) -> tuple[Optional[ParsedProteinChange], Optional[str]]:
    """Parse a protein HGVS string.

    Returns ``(parsed, None)`` on success or ``(None, reason)`` when the
    input is missing, malformed, or uses a construct this parser does not
    cover. Mixed three-/one-letter residue notation is rejected.
    """
    if text is None:
        return None, "no protein HGVS supplied"
    s = text.strip()
    if not s:
        return None, "empty string"
    if not re.search(r"(^|:)p\.", s):
        return None, "missing 'p.' prefix"

    m = _P_FS.match(s)
    if m:
        ref = _to_three(m.group("ref"))
        alt = _to_three(m.group("alt")) if m.group("alt") else None
        if ref is None or (m.group("alt") and alt is None):
            return None, "unknown residue code"
        if not _consistent_mode([m.group("ref")] + ([m.group("alt")] if m.group("alt") else [])):
            return None, "mixed one-/three-letter residue notation"
        off = m.group("off")
        fs_off = int(off) if off and off.isdigit() else None
        pos = int(m.group("pos"))
        return _build("frameshift", s, ref, pos, alt, None, None, None, fs_off, m), None

    m = _P_SUBST.match(s)
    if m:
        ref = _to_three(m.group("ref"))
        if ref is None:
            return None, "unknown residue code"
        pos = int(m.group("pos"))
        alt_tok = m.group("alt")
        if alt_tok == "=":
            return _build("synonymous", s, ref, pos, ref, None, None, None, None, m), None
        if alt_tok == "?":
            if ref == "Met" and pos == 1:
                return _build("start_loss", s, ref, pos, None, None, None, None, None, m), None
            return None, "unknown consequence '?' outside the initiator codon"
        alt = _to_three(alt_tok)
        if alt is None:
            return None, "unknown residue code"
        if not _consistent_mode([m.group("ref"), alt_tok]):
            return None, "mixed one-/three-letter residue notation"
        if ref == "Ter":
            return None, "stop-loss/extension variants are not supported"
        kind = "nonsense" if alt == "Ter" else "missense"
        return _build(kind, s, ref, pos, alt, None, None, None, None, m), None

    m = _P_RANGE.match(s)
    if m:
        ref = _to_three(m.group("ref"))
        if ref is None:
            return None, "unknown residue code"
        three_mode = m.group("ref") in THREE_TO_ONE
        eref_tok, epos = m.group("eref"), m.group("epos")
        eref = None
        if eref_tok:
            eref = _to_three(eref_tok)
            if eref is None:
                return None, "unknown residue code"
            if (eref_tok in THREE_TO_ONE) != three_mode:
                return None, "mixed one-/three-letter residue notation"
            if int(epos) <= int(m.group("pos")):
                return None, "range end must be greater than range start"
        op, seq = m.group("op"), m.group("seq")
        pos = int(m.group("pos"))
        end_pos = int(epos) if epos else None
        inserted = None
        if op in ("ins", "delins"):
            if not seq:
                return None, f"'{op}' requires an inserted sequence or count"
            if seq.isdigit():
                inserted = seq
            else:
                inserted = _seq_to_three(seq, three_mode)
                if inserted is None:
                    return None, "inserted residues could not be interpreted"
        elif seq:
            return None, f"unexpected trailing text after '{op}'"
        if op == "ins" and eref is None:
            return None, "insertion requires a flanking residue range"
        kind = {"del": "inframe_deletion", "dup": "inframe_duplication", "ins": "inframe_insertion", "delins": "delins"}[op]
        return _build(kind, s, ref, pos, None, eref, end_pos, inserted, None, m), None

    return None, "unrecognised protein HGVS pattern"


def _consistent_mode(tokens: list[str]) -> bool:
    modes = {(t in THREE_TO_ONE) for t in tokens if t != "*"}
    return len(modes) <= 1


def _build(kind: str, original: str, ref: str, pos: int, alt: Optional[str], eref: Optional[str],
           epos: Optional[int], inserted: Optional[str], fs_off: Optional[int], m: re.Match) -> ParsedProteinChange:
    return ParsedProteinChange(
        original=original,
        kind=kind,
        ref_aa=ref,
        position=pos,
        alt_aa=alt,
        end_ref_aa=eref,
        end_position=epos,
        inserted=inserted,
        frameshift_stop_offset=fs_off,
        predicted=bool(m.group("pred")),
        accession=m.group("acc"),
        codon_label=f"{THREE_TO_ONE[ref]}{pos}",
        one_letter=_render(kind, ref, pos, alt, eref, epos, inserted, fs_off, one=True),
        three_letter=_render(kind, ref, pos, alt, eref, epos, inserted, fs_off, one=False),
    )


_C_POS = r"(?:\*|-)?\d+(?:[+-]\d+)?"
_C_PREFIX = r"^(?:(?P<acc>[A-Z]{2}_\d+(?:\.\d+)?):)?(?P<prefix>[cng])\."
_C_SUBST = re.compile(_C_PREFIX + rf"(?P<start>{_C_POS})(?P<ref>[ACGTN])>(?P<alt>[ACGTN])$")
_C_OP = re.compile(
    _C_PREFIX
    + rf"(?P<start>{_C_POS})(?:_(?P<end>{_C_POS}))?"
    + r"(?P<op>delins|del|dup|ins|inv)(?P<seq>[ACGTN]+|\d+)?$"
)


def _base(pos: str) -> int:
    core = pos.split("+")[0]
    if core.startswith("*"):
        return int(core[1:])
    # a leading '-' means 5' UTR; a '-' after digits is an intronic offset
    if core.startswith("-"):
        return -int(core[1:].split("-")[0])
    return int(core.split("-")[0])


def parse_coding_hgvs(text: Optional[str]) -> tuple[Optional[ParsedCodingChange], Optional[str]]:
    """Parse a ``c.``, ``n.`` or ``g.`` HGVS string into structure.

    Returns ``(None, reason)`` for missing or unsupported input.
    """
    if text is None:
        return None, "no coding HGVS supplied"
    s = text.strip()
    if not s:
        return None, "empty string"
    m = _C_SUBST.match(s)
    if m:
        return ParsedCodingChange(
            original=s, prefix=m.group("prefix"), kind="substitution",
            start=m.group("start"), start_base=_base(m.group("start")),
            reference=m.group("ref"), alternate=m.group("alt"), accession=m.group("acc"),
        ), None
    m = _C_OP.match(s)
    if m:
        op, seq = m.group("op"), m.group("seq")
        start, end = m.group("start"), m.group("end")
        if end is not None and _base(end) < _base(start):
            return None, "range end precedes range start"
        kind = {"del": "deletion", "dup": "duplication", "ins": "insertion", "delins": "delins", "inv": "inversion"}[op]
        ref = alt = None
        if op in ("ins", "delins"):
            if not seq:
                return None, f"'{op}' requires an inserted sequence or length"
            alt = seq
            if op == "ins" and end is None:
                return None, "insertion requires a flanking position range"
        elif seq:
            if seq.isdigit():
                # legacy length suffix (c.2235_2249del15): accept only if it matches the span
                span = (_base(end) - _base(start) + 1) if end else 1
                if int(seq) != span or ("+" in start or "-" in start[1:]):
                    return None, f"length suffix '{seq}' does not match the stated range"
            else:
                ref = seq
        return ParsedCodingChange(
            original=s, prefix=m.group("prefix"), kind=kind, start=start, end=end,
            start_base=_base(start), end_base=_base(end) if end else None,
            reference=ref, alternate=alt, accession=m.group("acc"),
        ), None
    if not re.search(r"(^|:)[cng]\.", s):
        return None, "missing 'c.', 'n.' or 'g.' prefix"
    return None, "unrecognised coding HGVS pattern"
