"""
Smart Model Recommendation Engine

Analyzes LLM model performance and failure patterns to suggest
specific replacement models that better match workload requirements.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.utils.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass
class ModelCharacteristics:
    """Characteristics of an LLM model."""

    name: str
    size_gb: float
    context_window: int
    strengths: list[str]
    weaknesses: list[str]
    recommended_for: list[str]
    min_ram_gb: int


# Model database with characteristics
MODEL_DATABASE: dict[str, ModelCharacteristics] = {
    "gemma3:4b": ModelCharacteristics(
        name="gemma3:4b",
        size_gb=2.4,
        context_window=8192,
        strengths=["Fast inference", "Low resource usage", "Good for testing"],
        weaknesses=["Prone to hallucinations", "Limited reasoning", "Short outputs"],
        recommended_for=["Development smoke tests", "CI/CD pipelines (with stubs)"],
        min_ram_gb=4,
    ),
    "deepseek-r1:8b": ModelCharacteristics(
        name="deepseek-r1:8b",
        size_gb=4.7,
        context_window=32768,
        strengths=["Better reasoning", "Longer context", "More coherent outputs"],
        weaknesses=["Slower inference", "Higher resource usage", "Occasional verbosity"],
        recommended_for=["Local development", "Medium-quality content generation"],
        min_ram_gb=8,
    ),
    "llama3:8b": ModelCharacteristics(
        name="llama3:8b",
        size_gb=4.7,
        context_window=8192,
        strengths=["Balanced performance", "Good instruction following", "Stable outputs"],
        weaknesses=["Moderate resource usage", "Can be verbose"],
        recommended_for=["Production-like testing", "Balanced quality/speed"],
        min_ram_gb=8,
    ),
    "llama3.1:8b": ModelCharacteristics(
        name="llama3.1:8b",
        size_gb=4.9,
        context_window=131072,
        strengths=["Extended context", "Improved reasoning", "Better coherence"],
        weaknesses=["Higher memory usage", "Slower with long contexts"],
        recommended_for=["Long-context tasks", "High-quality content"],
        min_ram_gb=8,
    ),
    "qwen2.5:7b": ModelCharacteristics(
        name="qwen2.5:7b",
        size_gb=4.4,
        context_window=32768,
        strengths=["Strong multilingual", "Good coding", "Fast inference"],
        weaknesses=["Less common ecosystem"],
        recommended_for=["Coding tasks", "Technical content", "Multilingual support"],
        min_ram_gb=8,
    ),
    "mistral:7b": ModelCharacteristics(
        name="mistral:7b",
        size_gb=4.1,
        context_window=32768,
        strengths=["Excellent reasoning", "Good instruction following", "Efficient"],
        weaknesses=["Can be terse"],
        recommended_for=["Production testing", "High-quality outputs", "Reasoning tasks"],
        min_ram_gb=8,
    ),
    "phi3:3.8b": ModelCharacteristics(
        name="phi3:3.8b",
        size_gb=2.2,
        context_window=4096,
        strengths=["Very efficient", "Good for small tasks", "Low latency"],
        weaknesses=["Limited context", "Struggles with complex tasks"],
        recommended_for=["Ultra-fast smoke tests", "Simple classification"],
        min_ram_gb=4,
    ),
    "gpt-oss:20b": ModelCharacteristics(
        name="gpt-oss:20b",
        size_gb=12.0,
        context_window=8192,
        strengths=["High-quality judgements", "Strong reasoning", "Reliable"],
        weaknesses=["High resource usage", "Slow inference"],
        recommended_for=["Judge/validation tasks", "Quality assessment"],
        min_ram_gb=16,
    ),
}


@dataclass
class ReplacementRecommendation:
    """Recommendation for replacing a model."""

    current_model: str
    recommended_model: str
    confidence: str  # "high", "medium", "low"
    reasoning: str
    expected_improvement: str
    trade_offs: str
    command: str


class ModelRecommender:
    """Analyzes failure patterns and recommends better models."""

    def __init__(self, model_db: dict[str, ModelCharacteristics] | None = None):
        self.model_db = model_db or MODEL_DATABASE
        LOGGER.info("Model recommender initialized with %d models", len(self.model_db))

    def analyze_and_recommend(
        self,
        model_name: str,
        success_rate: float,
        failures_by_reason: dict[str, int],
        total_runs: int,
    ) -> ReplacementRecommendation | None:
        """
        Analyze failure patterns and recommend a replacement model.

        Args:
            model_name: Current model name
            success_rate: Overall success rate (0.0 - 1.0)
            failures_by_reason: Dict of failure_reason -> count
            total_runs: Total number of test runs

        Returns:
            ReplacementRecommendation or None if current model is acceptable
        """
        # If success rate is good, no replacement needed
        if success_rate >= 0.75:
            LOGGER.info("Model %s performing well (%.1f%%), no replacement needed", model_name, success_rate * 100)
            return None

        current_model_info = self.model_db.get(model_name)
        if not current_model_info:
            LOGGER.warning("Model %s not in database, cannot provide specific recommendations", model_name)
            return self._generic_recommendation(model_name, success_rate, failures_by_reason)

        # Analyze failure patterns
        failure_analysis = self._analyze_failure_patterns(failures_by_reason, total_runs)

        # Select best replacement based on failure patterns
        recommended = self._select_replacement(current_model_info, failure_analysis, success_rate)

        if not recommended:
            return self._generic_recommendation(model_name, success_rate, failures_by_reason)

        return recommended

    def _analyze_failure_patterns(
        self, failures_by_reason: dict[str, int], total_runs: int
    ) -> dict[str, Any]:
        """Analyze failure patterns to understand model weaknesses."""
        total_failures = sum(failures_by_reason.values())

        analysis = {
            "dominant_failure": None,
            "hallucination_rate": 0.0,
            "length_issues_rate": 0.0,
            "topic_drift_rate": 0.0,
            "needs_better_reasoning": False,
            "needs_longer_output": False,
            "needs_better_coherence": False,
        }

        if total_failures == 0:
            return analysis

        # Find dominant failure type
        if failures_by_reason:
            analysis["dominant_failure"] = max(failures_by_reason.items(), key=lambda x: x[1])[0]

        # Calculate specific failure rates
        for reason, count in failures_by_reason.items():
            rate = count / total_runs

            if "judge_rejected" in reason or "hallucination" in reason or "incoherence" in reason:
                analysis["hallucination_rate"] += rate
                analysis["needs_better_reasoning"] = True
                analysis["needs_better_coherence"] = True

            if "too_short" in reason or "too_long" in reason:
                analysis["length_issues_rate"] += rate
                if "too_short" in reason:
                    analysis["needs_longer_output"] = True

            if "off_topic" in reason or "coverage" in reason:
                analysis["topic_drift_rate"] += rate
                analysis["needs_better_reasoning"] = True

        LOGGER.debug(
            "Failure analysis: hallucination=%.1f%%, length=%.1f%%, topic_drift=%.1f%%",
            analysis["hallucination_rate"] * 100,
            analysis["length_issues_rate"] * 100,
            analysis["topic_drift_rate"] * 100,
        )

        return analysis

    def _select_replacement(
        self,
        current_model: ModelCharacteristics,
        failure_analysis: dict[str, Any],
        success_rate: float,
    ) -> ReplacementRecommendation | None:
        """Select the best replacement model based on failure patterns."""
        # Scoring candidates
        candidates: dict[str, float] = {}

        for model_name, model_info in self.model_db.items():
            # Skip current model
            if model_name == current_model.name:
                continue

            # Skip smaller models
            if model_info.size_gb <= current_model.size_gb:
                continue

            score = 0.0

            # High hallucination -> prioritize models good at reasoning
            if failure_analysis["hallucination_rate"] > 0.3:
                if "reasoning" in " ".join(model_info.strengths).lower():
                    score += 30
                if "coherent" in " ".join(model_info.strengths).lower():
                    score += 20

            # Length issues -> prioritize models with better instruction following
            if failure_analysis["length_issues_rate"] > 0.2:
                if "instruction" in " ".join(model_info.strengths).lower():
                    score += 25

            # Topic drift -> prioritize reasoning models
            if failure_analysis["topic_drift_rate"] > 0.2:
                if "reasoning" in " ".join(model_info.strengths).lower():
                    score += 25

            # Prefer models recommended for production/quality
            if any(
                keyword in " ".join(model_info.recommended_for).lower()
                for keyword in ["production", "quality", "high-quality"]
            ):
                score += 15

            # Penalize extreme resource requirements
            if model_info.min_ram_gb > 16:
                score -= 20

            if score > 0:
                candidates[model_name] = score

        if not candidates:
            return None

        # Select best candidate
        best_model_name = max(candidates, key=candidates.get)
        best_model = self.model_db[best_model_name]

        # Determine confidence based on score difference
        best_score = candidates[best_model_name]
        confidence = "high" if best_score >= 50 else "medium" if best_score >= 30 else "low"

        # Generate reasoning
        reasoning_parts = [f"Current model {current_model.name} has {success_rate:.1%} success rate."]

        if failure_analysis["hallucination_rate"] > 0.3:
            reasoning_parts.append(
                f"High hallucination rate ({failure_analysis['hallucination_rate']:.1%}) "
                f"indicates need for better reasoning capabilities."
            )

        if failure_analysis["length_issues_rate"] > 0.2:
            reasoning_parts.append(
                f"Frequent length issues ({failure_analysis['length_issues_rate']:.1%}) "
                f"suggest better instruction following needed."
            )

        if failure_analysis["topic_drift_rate"] > 0.2:
            reasoning_parts.append(
                f"Topic drift ({failure_analysis['topic_drift_rate']:.1%}) indicates "
                f"need for stronger topic adherence."
            )

        reasoning_parts.append(
            f"{best_model.name} offers: {', '.join(best_model.strengths[:3])}."
        )

        # Expected improvement
        if success_rate < 0.4:
            expected_improvement = "Major improvement expected (likely 60-80% success rate)"
        elif success_rate < 0.6:
            expected_improvement = "Significant improvement expected (likely 70-85% success rate)"
        else:
            expected_improvement = "Moderate improvement expected (likely 75-90% success rate)"

        # Trade-offs
        trade_offs_parts = []
        if best_model.size_gb > current_model.size_gb + 2:
            trade_offs_parts.append(
                f"Larger model ({best_model.size_gb:.1f}GB vs {current_model.size_gb:.1f}GB)"
            )
        if best_model.min_ram_gb > current_model.min_ram_gb:
            trade_offs_parts.append(
                f"Requires more RAM (min {best_model.min_ram_gb}GB vs {current_model.min_ram_gb}GB)"
            )
        trade_offs_parts.append("Slower inference time expected")

        return ReplacementRecommendation(
            current_model=current_model.name,
            recommended_model=best_model.name,
            confidence=confidence,
            reasoning=" ".join(reasoning_parts),
            expected_improvement=expected_improvement,
            trade_offs="; ".join(trade_offs_parts) if trade_offs_parts else "None significant",
            command=f"ollama pull {best_model.name}",
        )

    def _generic_recommendation(
        self,
        model_name: str,
        success_rate: float,
        failures_by_reason: dict[str, int],
    ) -> ReplacementRecommendation:
        """Provide generic recommendation when model not in database."""
        if success_rate < 0.4:
            recommended = "llama3.1:8b or mistral:7b"
            reasoning = (
                f"Model {model_name} has very low success rate ({success_rate:.1%}). "
                "Consider upgrading to a larger, more capable model."
            )
        elif success_rate < 0.6:
            recommended = "llama3:8b or qwen2.5:7b"
            reasoning = (
                f"Model {model_name} has marginal success rate ({success_rate:.1%}). "
                "Consider upgrading to a more balanced model."
            )
        else:
            recommended = "deepseek-r1:8b or llama3:8b"
            reasoning = (
                f"Model {model_name} has acceptable but improvable success rate ({success_rate:.1%})."
            )

        return ReplacementRecommendation(
            current_model=model_name,
            recommended_model=recommended,
            confidence="medium",
            reasoning=reasoning,
            expected_improvement="Improvement expected based on general patterns",
            trade_offs="Larger models require more resources",
            command=f"ollama pull {recommended.split()[0]}",
        )

    def generate_recommendation_report(
        self, model_summaries: dict[str, Any]
    ) -> str:
        """
        Generate a comprehensive recommendation report for multiple models.

        Args:
            model_summaries: Dict of model_name -> ModelAuditSummary

        Returns:
            Markdown-formatted recommendation report
        """
        report_lines = [
            "# Model Replacement Recommendations\n",
            "Based on failure pattern analysis and model characteristics:\n",
        ]

        for model_name, summary in model_summaries.items():
            recommendation = self.analyze_and_recommend(
                model_name,
                summary.success_rate,
                summary.failures_by_reason,
                summary.total_runs,
            )

            report_lines.append(f"\n## {model_name}\n")
            report_lines.append(f"**Current Performance**: {summary.success_rate:.1%} success rate\n")

            if recommendation is None:
                report_lines.append("✅ **Status**: Performing well, no replacement needed\n")
                continue

            report_lines.append(f"### Recommended Replacement: {recommendation.recommended_model}\n")
            report_lines.append(f"**Confidence**: {recommendation.confidence.upper()}\n")
            report_lines.append(f"**Reasoning**: {recommendation.reasoning}\n")
            report_lines.append(f"**Expected Improvement**: {recommendation.expected_improvement}\n")
            report_lines.append(f"**Trade-offs**: {recommendation.trade_offs}\n")
            report_lines.append(f"**Installation**:\n```bash\n{recommendation.command}\n```\n")

        return "\n".join(report_lines)


__all__ = [
    "ModelRecommender",
    "ModelCharacteristics",
    "ReplacementRecommendation",
    "MODEL_DATABASE",
]

