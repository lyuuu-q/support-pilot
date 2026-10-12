from uuid import uuid4

from support_pilot.rag.contracts import Citation, RetrievalHit
from support_pilot.rag.faithfulness import (
    build_evidence_claims,
    split_claims,
    verify_claim,
)


def _hit(
    content: str,
    *,
    source_uri: str = "kb://exampleapi/reference/rate-limits",
) -> RetrievalHit:
    return RetrievalHit(
        citation=Citation(
            chunk_id=uuid4(),
            document_title="Synthetic guide",
            source_uri=source_uri,
            heading_path=["Synthetic"],
            product_version="v2",
            excerpt=content[:300],
        ),
        content=content,
        metadata={},
        keyword_rank=1,
        vector_rank=1,
        rrf_score=1.0,
        rerank_score=0.9,
    )


def test_split_claims_removes_bullets_and_respects_limit() -> None:
    claims = split_claims(
        "- HTTP 429 表示短期限流。\n- 客户端应以 Retry-After 为准。\n- 不要立即并发重试。",
        max_claims=2,
    )

    assert claims == ["HTTP 429 表示短期限流", "客户端应以 Retry-After 为准"]


def test_verifier_accepts_verbatim_claim() -> None:
    verification = verify_claim(
        "客户端应以 Retry-After 为准。",
        "客户端应以 Retry-After 为准，不要立即并发重试。",
    )

    assert verification.supported
    assert verification.method == "verbatim"
    assert verification.support_score == 1.0


def test_verifier_requires_exact_technical_identifier() -> None:
    verification = verify_claim(
        "Webhook 使用 HMAC-SHA512 签名。",
        "Webhook 使用 HMAC-SHA256 签名，验证原始 request body。",
    )

    assert not verification.supported
    assert "hmac-sha512" in verification.missing_terms


def test_verifier_rejects_unrelated_claim() -> None:
    verification = verify_claim(
        "如何配置企业 SAML 单点登录？",
        "列表接口使用 limit 和 cursor，next_cursor 非空时才有下一页。",
    )

    assert not verification.supported
    assert verification.method == "unverified"
    assert verification.support_score < 0.85


def test_build_evidence_claims_filters_unsupported_candidates_by_default() -> None:
    hit = _hit("HTTP 429 表示短期限流。客户端应以 Retry-After 为准。")
    supported = build_evidence_claims([hit])
    all_candidates = build_evidence_claims([hit], include_unsupported=True)

    assert [claim.claim_id for claim in supported] == ["c1-1", "c1-2"]
    assert len(all_candidates) == 2
    assert all(claim.verification.supported for claim in supported)
