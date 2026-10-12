import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from support_pilot.infrastructure.database import get_session_factory
from support_pilot.rag.contracts import KnowledgeSearchInput, RetrievalFilters
from support_pilot.rag.faithfulness import build_evidence_claims, normalize_claim_text
from support_pilot.rag.providers.factory import get_provider_bundle
from support_pilot.rag.retrieval import HybridRetrievalService


class RequiredClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source_uri: str
    required_terms: list[str] = Field(min_length=1)


class FaithfulnessCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    answerable: bool = True
    relevant_sources: list[str] = Field(default_factory=list)
    required_claims: list[RequiredClaim] = Field(default_factory=list)
    product_version: str | None = None
    plan_code: str | None = None

    @model_validator(mode="after")
    def validate_answerability_labels(self) -> "FaithfulnessCase":
        if self.answerable and (not self.relevant_sources or not self.required_claims):
            raise ValueError("answerable cases require relevant sources and required claims")
        if not self.answerable and self.required_claims:
            raise ValueError("negative cases must not define required claims")
        return self


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate claim-level citations and faithfulness")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "local_bge"),
        default="deterministic",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/faithfulness_v2_cases.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evaluation/results/faithfulness-deterministic-v1.json"),
    )
    parser.add_argument("--k", type=int, default=5)
    return parser.parse_args()


def _average(values: list[float]) -> float:
    return round(mean(values), 4) if values else 0.0


def main() -> None:
    args = parse_args()
    cases = TypeAdapter(list[FaithfulnessCase]).validate_python(
        json.loads(args.dataset.read_text(encoding="utf-8"))
    )
    embedding, reranker = get_provider_bundle(args.provider)
    answerable_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    negative_count = 0
    negative_false_answers = 0

    with get_session_factory()() as session:
        service = HybridRetrievalService(
            session,
            embedding_provider=embedding,
            reranker_provider=reranker,
        )
        for case in cases:
            response = service.search(
                KnowledgeSearchInput(
                    query=case.query,
                    filters=RetrievalFilters(
                        product_version=case.product_version,
                        plan_code=case.plan_code,
                    ),
                    top_k=args.k,
                    candidate_k=20,
                )
            )
            selected_hits = response.hits[: response.decision.evidence_count]
            candidates = build_evidence_claims(selected_hits, include_unsupported=True)
            presented = response.claims
            unsupported = [claim for claim in candidates if not claim.verification.supported]
            support_rate = (
                round((len(candidates) - len(unsupported)) / len(candidates), 4)
                if candidates
                else 1.0
            )
            unsupported_rate = (
                round(len(unsupported) / len(candidates), 4) if candidates else 0.0
            )

            if not case.answerable:
                negative_count += 1
                false_answer = response.decision.answerable or bool(presented)
                if false_answer:
                    negative_false_answers += 1
                    failures.append(
                        {
                            "kind": "false_answer",
                            "id": case.id,
                            "query": case.query,
                            "decision": response.decision.model_dump(mode="json"),
                            "claims": [claim.model_dump(mode="json") for claim in presented],
                        }
                    )
                continue

            matched_claims: list[dict[str, str]] = []
            missing_claims: list[dict[str, str]] = []
            for required in case.required_claims:
                terms = [normalize_claim_text(term) for term in required.required_terms]
                matching = next(
                    (
                        claim
                        for claim in presented
                        if claim.source_uri == required.source_uri
                        and all(term in normalize_claim_text(claim.text) for term in terms)
                    ),
                    None,
                )
                if matching is None:
                    missing_claims.append(
                        {
                            "text": required.text,
                            "source_uri": required.source_uri,
                            "required_terms": ", ".join(required.required_terms),
                        }
                    )
                else:
                    matched_claims.append({"text": required.text, "claim_id": matching.claim_id})

            coverage = round(len(matched_claims) / len(case.required_claims), 4)
            citation_precision = (
                round(
                    sum(claim.source_uri in case.relevant_sources for claim in presented)
                    / len(presented),
                    4,
                )
                if presented
                else 1.0
            )
            answerable_reports.append(
                {
                    "claim_coverage": coverage,
                    "claim_support_rate": support_rate,
                    "citation_precision": citation_precision,
                    "unsupported_claim_rate": unsupported_rate,
                }
            )
            if missing_claims:
                failures.append(
                    {
                        "kind": "claim_coverage",
                        "id": case.id,
                        "query": case.query,
                        "coverage": coverage,
                        "retrieved_sources": list(
                            dict.fromkeys(hit.citation.source_uri for hit in selected_hits)
                        ),
                        "presented_claims": [claim.text for claim in presented],
                        "missing_claims": missing_claims,
                    }
                )
            if unsupported:
                failures.append(
                    {
                        "kind": "unsupported_claim",
                        "id": case.id,
                        "query": case.query,
                        "claims": [claim.model_dump(mode="json") for claim in unsupported],
                    }
                )

    metrics = {
        "claim_coverage": _average(
            [item["claim_coverage"] for item in answerable_reports]
        ),
        "claim_support_rate": _average(
            [item["claim_support_rate"] for item in answerable_reports]
        ),
        "citation_precision": _average(
            [item["citation_precision"] for item in answerable_reports]
        ),
        "unsupported_claim_rate": _average(
            [item["unsupported_claim_rate"] for item in answerable_reports]
        ),
        "false_answer_rate": round(negative_false_answers / negative_count, 4)
        if negative_count
        else 0.0,
    }
    report = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "dataset_version": "faithfulness-v2",
        "sample_count": len(cases),
        "answerable_count": len(answerable_reports),
        "negative_count": negative_count,
        "k": args.k,
        "data_origin": "human_labeled_synthetic",
        "embedding_provider": embedding.provider_name,
        "embedding_model": embedding.model_name,
        "reranker_provider": reranker.provider_name,
        "reranker_model": reranker.model_name,
        "metrics": metrics,
        "failure_count": len(failures),
        "failures": failures,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{rendered}\n", encoding="utf-8")
    if metrics["false_answer_rate"] or metrics["unsupported_claim_rate"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


