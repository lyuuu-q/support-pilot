import re
import unicodedata

from support_pilot.rag.contracts import ClaimVerification, EvidenceClaim, RetrievalHit
from support_pilot.rag.text import (
    TECHNICAL_FEATURE_PATTERN,
    lexical_features,
    weighted_coverage,
)

_SPLIT_PATTERN = re.compile(r"[。！？!?；;\n]+")
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*")
_EDGE_PUNCTUATION = " \t\r\n。；;，,、：:!?！？()（）[]【】\"'“”‘’"
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _containment_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(
        character
        for character in normalized
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def normalize_claim_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def split_claims(text: str, *, max_claims: int = 4, min_length: int = 6) -> list[str]:
    claims: list[str] = []
    for raw_part in _SPLIT_PATTERN.split(text):
        part = _BULLET_PATTERN.sub("", raw_part).strip(_EDGE_PUNCTUATION)
        if len(part) < min_length:
            continue
        claims.append(part[:1_000])
        if len(claims) >= max_claims:
            break
    return claims


def verify_claim(claim_text: str, evidence_text: str) -> ClaimVerification:
    claim_normalized = normalize_claim_text(claim_text)
    if not claim_normalized:
        return ClaimVerification(
            supported=False,
            method="unverified",
            support_score=0.0,
            missing_terms=[],
        )
    if _containment_text(claim_text) in _containment_text(evidence_text):
        return ClaimVerification(
            supported=True,
            method="verbatim",
            support_score=1.0,
            missing_terms=[],
        )
    claim_features = lexical_features(claim_text)
    evidence_features = set(lexical_features(evidence_text))
    technical_terms = list(
        dict.fromkeys(
            feature
            for feature in claim_features
            if TECHNICAL_FEATURE_PATTERN.fullmatch(feature)
        )
    )
    missing_terms = [term for term in technical_terms if term not in evidence_features]
    coverage = weighted_coverage(claim_features, evidence_features)
    supported = not missing_terms and coverage >= 0.85
    return ClaimVerification(
        supported=supported,
        method="token_overlap" if supported else "unverified",
        support_score=round(coverage, 4),
        missing_terms=missing_terms[:10],
    )


def build_evidence_claims(
    hits: list[RetrievalHit],
    *,
    include_unsupported: bool = False,
    max_claims_per_hit: int = 8,
) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for citation_index, hit in enumerate(hits):
        for claim_index, claim_text in enumerate(
            split_claims(hit.content, max_claims=max_claims_per_hit),
            start=1,
        ):
            verification = verify_claim(claim_text, hit.content)
            if not include_unsupported and not verification.supported:
                continue
            claims.append(
                EvidenceClaim(
                    claim_id=f"c{citation_index + 1}-{claim_index}",
                    text=claim_text,
                    chunk_id=hit.citation.chunk_id,
                    source_uri=hit.citation.source_uri,
                    citation_index=citation_index,
                    verification=verification,
                )
            )
    return claims

