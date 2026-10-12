import math
from collections import Counter
from collections.abc import Sequence
from hashlib import sha256

from support_pilot.rag.text import feature_weight as feature_weight
from support_pilot.rag.text import lexical_features as lexical_features
from support_pilot.rag.text import weighted_coverage as weighted_coverage


class DeterministicEmbeddingProvider:
    provider_name = "deterministic"
    model_name = "hash-lexical-v1"
    dimensions = 512

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, count in Counter(lexical_features(text)).items():
            digest = sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * float(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class DeterministicRerankerProvider:
    provider_name = "deterministic"
    model_name = "weighted-token-overlap-v2"
    answerability_threshold = 0.28

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        query_features = set(lexical_features(query))
        return [
            weighted_coverage(query_features, set(lexical_features(document)))
            for document in documents
        ]
