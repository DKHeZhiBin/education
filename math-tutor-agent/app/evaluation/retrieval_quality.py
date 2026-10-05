from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

from app.domain.evaluation import RetrievalEvaluationDocument, RetrievalEvaluationQuery
from app.domain.retrieval_evaluation import (
    RetrievalEvaluationRunRecord,
    RetrievalQualityMetric,
    RetrievalQualityReport,
    RetrievalQueryQuality,
)
from app.evaluation.datasets import (
    DEFAULT_RETRIEVAL_MANIFEST,
    EvaluationDatasetError,
    load_retrieval_evaluation_suite,
)


class RetrievalQualityEvaluator:
    def evaluate(
        self,
        records: list[RetrievalEvaluationRunRecord],
        *,
        manifest_path: str | Path = DEFAULT_RETRIEVAL_MANIFEST,
        production_collection: str,
    ) -> RetrievalQualityReport:
        manifest, documents, queries, _ = load_retrieval_evaluation_suite(
            manifest_path,
            production_collection=production_collection,
        )
        query_by_id = {item.id: item for item in queries}
        document_by_id = {item.id: item for item in documents}
        record_ids = [item.query_id for item in records]
        if len(record_ids) != len(set(record_ids)):
            raise EvaluationDatasetError("A retrieval run may contain only one record per query")
        unknown_queries = set(record_ids) - query_by_id.keys()
        if unknown_queries:
            raise EvaluationDatasetError(
                f"Retrieval run references unknown queries: {sorted(unknown_queries)}"
            )
        if any(item.index_namespace != manifest.index_namespace for item in records):
            raise EvaluationDatasetError("Retrieval run escaped the evaluation namespace")

        query_results = [
            self._evaluate_query(record, query_by_id[record.query_id], document_by_id)
            for record in records
        ]
        recall_sum = sum(item.recall_at_k for item in query_results)
        ndcg_sum = sum(item.reranked_ndcg_at_k for item in query_results)
        baseline_sum = sum(item.baseline_ndcg_at_k for item in query_results)
        claim_total = sum(item.assessed_claim_count for item in query_results)
        claim_correct = sum(item.consistent_claim_count for item in query_results)
        citation_total = sum(item.citation_count for item in query_results)
        citation_correct = sum(item.correct_citation_count for item in query_results)
        query_count = len(query_results)
        return RetrievalQualityReport(
            generated_at=datetime.now(timezone.utc),
            suite_name=manifest.name,
            index_namespace=manifest.index_namespace,
            expected_query_count=len(queries),
            evaluated_query_count=query_count,
            query_coverage=round(query_count / len(queries), 6),
            metrics=[
                self._metric(
                    key="retrieval_recall_at_k",
                    label="检索召回率",
                    numerator=recall_sum,
                    denominator=query_count,
                    definition="各查询 Recall@K 的宏平均；相关文档按冻结标注计算。",
                    details={
                        "required_query_hits": sum(item.required_hit for item in query_results),
                        "forbidden_hits": sum(item.forbidden_hit_count for item in query_results),
                    },
                ),
                self._metric(
                    key="rerank_ndcg_at_k",
                    label="重排质量",
                    numerator=ndcg_sum,
                    denominator=query_count,
                    definition="重排结果 nDCG@K 的宏平均；必选文档相关度为2，其他相关文档为1。",
                    details={
                        "baseline_ndcg_at_k": round(baseline_sum / query_count, 6)
                        if query_count else None,
                        "mean_rerank_delta": round((ndcg_sum - baseline_sum) / query_count, 6)
                        if query_count else None,
                    },
                ),
                self._metric(
                    key="answer_evidence_consistency",
                    label="答案依据一致性",
                    numerator=claim_correct,
                    denominator=claim_total,
                    definition="经独立评估为 supported，且依据来自前K结果、命中相关标注并避开禁止文档的回答主张比例。",
                ),
                self._metric(
                    key="citation_correctness",
                    label="引用正确性",
                    numerator=citation_correct,
                    denominator=citation_total,
                    definition="引用指向相关且已检索的依据文档，并与主张依据及语料 source_version 一致的比例。",
                ),
            ],
            queries=query_results,
            notes=[
                "not_assessed 主张不进入答案依据一致性分母。",
                "没有回答主张或引用时对应指标返回 no_samples，不视为通过。",
                "unknown_document_ids 会降低相关指标，不允许把生产集合文档混入隔离评估。",
            ],
        )

    def _evaluate_query(
        self,
        record: RetrievalEvaluationRunRecord,
        query: RetrievalEvaluationQuery,
        document_by_id: dict[str, RetrievalEvaluationDocument],
    ) -> RetrievalQueryQuality:
        k = query.k
        initial = record.initial_document_ids[:k]
        reranked = record.reranked_document_ids[:k]
        relevant = set(query.relevant_document_ids)
        required = set(query.required_document_ids)
        forbidden = set(query.forbidden_document_ids)
        recall = len(relevant & set(reranked)) / len(relevant)
        baseline_ndcg = self._ndcg(initial, relevant, required, k)
        reranked_ndcg = self._ndcg(reranked, relevant, required, k)
        unknown = sorted(
            (set(initial) | set(reranked)) - document_by_id.keys()
        )

        claim_by_id = {item.claim_id: item for item in record.answer_claims}
        assessed = [
            item for item in record.answer_claims if item.support_status != "not_assessed"
        ]
        consistent_claims = {
            item.claim_id for item in assessed
            if self._claim_consistent(item, set(reranked), relevant, forbidden, document_by_id)
        }
        correct_citations = sum(
            self._citation_correct(
                item,
                claim_by_id,
                consistent_claims,
                set(reranked),
                relevant,
                document_by_id,
            )
            for item in record.citations
        )
        return RetrievalQueryQuality(
            query_id=query.id,
            k=k,
            recall_at_k=round(recall, 6),
            recall_threshold_met=recall >= query.minimum_recall_at_k,
            required_hit=required <= set(reranked),
            forbidden_hit_count=len(forbidden & set(reranked)),
            baseline_ndcg_at_k=round(baseline_ndcg, 6),
            reranked_ndcg_at_k=round(reranked_ndcg, 6),
            rerank_delta=round(reranked_ndcg - baseline_ndcg, 6),
            assessed_claim_count=len(assessed),
            consistent_claim_count=len(consistent_claims),
            citation_count=len(record.citations),
            correct_citation_count=correct_citations,
            unknown_document_ids=unknown,
        )

    @staticmethod
    def _ndcg(
        ranked_ids: list[str], relevant: set[str], required: set[str], k: int
    ) -> float:
        grades = [2 if item in required else 1 if item in relevant else 0 for item in ranked_ids[:k]]
        ideal = sorted(
            [2 if item in required else 1 for item in relevant], reverse=True
        )[:k]
        dcg = sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))
        idcg = sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(ideal))
        return dcg / idcg if idcg else 0.0

    @staticmethod
    def _claim_consistent(
        claim,
        reranked: set[str],
        relevant: set[str],
        forbidden: set[str],
        document_by_id: dict[str, RetrievalEvaluationDocument],
    ) -> bool:
        evidence = set(claim.evidence_document_ids)
        return bool(
            claim.support_status == "supported"
            and evidence
            and evidence <= set(document_by_id)
            and evidence <= reranked
            and evidence.isdisjoint(forbidden)
            and bool(evidence & relevant)
        )

    @staticmethod
    def _citation_correct(
        citation,
        claim_by_id: dict,
        consistent_claims: set[str],
        reranked: set[str],
        relevant: set[str],
        document_by_id: dict[str, RetrievalEvaluationDocument],
    ) -> bool:
        claim = claim_by_id.get(citation.claim_id)
        document = document_by_id.get(citation.document_id)
        return bool(
            claim is not None
            and citation.claim_id in consistent_claims
            and document is not None
            and citation.document_id in claim.evidence_document_ids
            and citation.document_id in reranked
            and citation.document_id in relevant
            and citation.source_version == document.metadata.get("source_version")
        )

    @staticmethod
    def _metric(
        *, key: str, label: str, numerator: float, denominator: float,
        definition: str, details: dict | None = None,
    ) -> RetrievalQualityMetric:
        score = numerator / denominator if denominator else None
        return RetrievalQualityMetric(
            key=key,
            label=label,
            numerator=round(numerator, 6),
            denominator=denominator,
            score=round(score, 6) if score is not None else None,
            percentage=round(score * 100, 2) if score is not None else None,
            status="available" if denominator else "no_samples",
            definition=definition,
            details=details or {},
        )
