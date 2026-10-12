import re
from collections.abc import Iterable

TOKEN_PATTERN = re.compile(r"[a-z0-9_./:-]+|[\u4e00-\u9fff]", re.IGNORECASE)
TECHNICAL_FEATURE_PATTERN = re.compile(r"^[a-z0-9_./:-]+$", re.IGNORECASE)


def lexical_features(text: str) -> list[str]:
    """Return deterministic tokens plus Chinese bigrams for lexical comparison."""
    normalized = text.lower()
    tokens = TOKEN_PATTERN.findall(normalized)
    chinese = "".join(token for token in tokens if "\u4e00" <= token <= "\u9fff")
    bigrams = [chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0))]
    return tokens + bigrams


def feature_weight(feature: str) -> float:
    """Weight technical identifiers and Chinese bigrams more than single CJK characters."""
    if TECHNICAL_FEATURE_PATTERN.fullmatch(feature):
        return 3.0
    if len(feature) == 2:
        return 1.5
    return 0.25


def weighted_coverage(claim_features: Iterable[str], evidence_features: set[str]) -> float:
    unique_claim = set(claim_features)
    denominator = sum(feature_weight(feature) for feature in unique_claim)
    if denominator == 0:
        return 0.0
    matched = sum(
        feature_weight(feature) for feature in unique_claim if feature in evidence_features
    )
    return matched / denominator
