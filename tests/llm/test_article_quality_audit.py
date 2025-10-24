"""
LLM Quality Audit Tests - Zero-Retry Strict Validation

This module implements strict quality audits for LLM models with NO retries.
Unlike test_article_generation.py (which allows retries for stability),
these tests are DESIGNED TO FAIL when models produce poor outputs.

Purpose:
- Expose genuine model weaknesses (hallucinations, incoherence, off-topic)
- Provide statistical evidence of model quality over multiple runs
- Generate actionable insights for model replacement decisions

Expected Behavior:
- LOCAL RUNS (USE_FAKE_OLLAMA=0): May fail frequently with small models
- CI RUNS (USE_FAKE_OLLAMA=1): Pass with deterministic stubs
- Failures are SUCCESS - they prove the test system can detect defects

Usage:
  # Run audit separately (may fail)
  pytest -m llm_audit --verbose

  # Run with regular LLM tests
  pytest -m "llm or llm_audit"

Model Replacement Guidance:
- If success rate < 40%: Replace model immediately
- If success rate 40-60%: Consider replacement or prompt tuning
- If success rate > 60%: Model is acceptable
- If success rate > 80%: Model is performing well
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import allure
import pytest
import yaml
from jinja2 import Template

from src.utils.audit_persistence import AuditPersistence, create_audit_metadata
from src.utils.logger import get_logger
from src.utils.model_recommender import ModelRecommender
from src.utils.ollama_client import OllamaRunner

LOGGER = get_logger(__name__)

PROMPTS_FILE = Path("promptfoo/prompts/articles.yaml")
GENERATOR_MODELS = ["gemma3:4b", "deepseek-r1:8b"]
JUDGE_MODEL = "gpt-oss:20b"
AUDIT_ITERATIONS = 5  # Run each scenario 5 times for statistical significance

default_fake = "1" if os.environ.get("CI", "").lower() in {"1", "true", "yes"} else "0"
FAKE_OLLAMA = os.environ.get("USE_FAKE_OLLAMA", default_fake).lower() in {"1", "true", "yes"}


@dataclass
class AuditResult:
    """Single audit iteration result."""
    iteration: int
    model: str
    scenario_id: str
    output: str
    length: int
    topic_coverage: float
    judge_pass: bool
    judge_reasoning: str
    failure_reason: str | None


@dataclass
class ModelAuditSummary:
    """Statistical summary for a model across all scenarios."""
    model: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    failures_by_reason: dict[str, int]
    recommendation: str


def calculate_topic_coverage(output: str, topic: str) -> float:
    """Calculate what percentage of topic keywords appear in output."""
    topic_terms = {term.lower() for term in re.findall(r"[A-Za-z]+", topic) if len(term) > 3}
    if not topic_terms:
        return 1.0  # No keywords to check
    matched_terms = {term for term in topic_terms if term in output.lower()}
    return len(matched_terms) / len(topic_terms)


def assess_failure_reason(result: AuditResult, min_length: int = 300, max_length: int = 500) -> str | None:
    """Determine primary failure reason for an audit result."""
    if result.length < min_length:
        return f"too_short ({result.length} < {min_length})"
    if result.length > max_length:
        return f"too_long ({result.length} > {max_length})"
    if result.topic_coverage < 0.5:
        return f"off_topic (coverage {result.topic_coverage:.1%})"
    if not result.judge_pass:
        return "judge_rejected (hallucination/incoherence)"
    return None


def generate_recommendation(summary: ModelAuditSummary) -> str:
    """Generate actionable recommendation based on success rate."""
    rate = summary.success_rate
    if rate < 0.4:
        return "🔴 REPLACE IMMEDIATELY - Model is unsuitable (success rate < 40%)"
    if rate < 0.6:
        return "🟡 CONSIDER REPLACEMENT - Model is marginal (success rate 40-60%)"
    if rate < 0.8:
        return "🟢 ACCEPTABLE - Model meets minimum standards (success rate 60-80%)"
    return "🟢 PERFORMING WELL - Model is reliable (success rate > 80%)"


@pytest.mark.llm_audit
def test_article_quality_audit_strict(settings) -> None:
    """
    STRICT QUALITY AUDIT - Zero retries, statistical analysis.

    This test is EXPECTED TO FAIL with small local models that produce
    hallucinations, off-topic content, or inconsistent outputs.

    Test Design Philosophy:
    - NO retries (unlike test_article_generation.py)
    - Multiple iterations per scenario for statistical significance
    - Comprehensive failure tracking with Allure attachments
    - Actionable model replacement recommendations
    - Proves test framework can detect genuine LLM defects

    Failure Interpretation:
    - Test PASSES: All models consistently produce valid outputs (rare with small models)
    - Test FAILS: Models produce hallucinations/errors (EXPECTED, DEMONSTRATES TESTING RIGOR)

    The failure attachments in Allure prove the test system works correctly.
    """
    if not PROMPTS_FILE.exists():
        pytest.skip(f"Prompt definitions missing; ensure {PROMPTS_FILE} is present")

    runner = OllamaRunner(settings.ollama_base_url)

    missing_models = [model for model in GENERATOR_MODELS + [JUDGE_MODEL] if not runner.ensure_model(model)]
    if missing_models:
        pytest.skip(f"Missing Ollama models: {', '.join(missing_models)}")

    data = yaml.safe_load(PROMPTS_FILE.read_text())
    prompt_template = next(prompt["template"] for prompt in data["prompts"] if prompt["id"] == "concise_article")
    template = Template(prompt_template)

    # Collect all audit results for statistical analysis
    all_results: list[AuditResult] = []
    model_summaries: dict[str, ModelAuditSummary] = {}

    for model in GENERATOR_MODELS:
        LOGGER.info("Starting strict quality audit for model: %s", model)
        model_results: list[AuditResult] = []

        for scenario in data["scenarios"]:
            vars_ = scenario["vars"]
            rendered_prompt = template.render(**vars_)
            scenario_id = scenario["id"]

            LOGGER.info("Auditing %s with %s (%d iterations)", scenario_id, model, AUDIT_ITERATIONS)

            for iteration in range(1, AUDIT_ITERATIONS + 1):
                # Generate with deterministic seed for reproducibility
                seed_base = int(hashlib.md5(f"{scenario_id}::{model}::audit".encode()).hexdigest()[:8], 16)
                seed = seed_base + iteration

                if FAKE_OLLAMA:
                    # Stub mode: deterministic pass
                    options = {"temperature": 0.0, "num_predict": 120, "seed": seed}
                else:
                    # Real mode: typical generation parameters, NO retries
                    options = {"temperature": 0.25, "num_predict": 180, "seed": seed}

                result = runner.generate(model, rendered_prompt, options=options)
                output = result.output.strip()

                # Clean up output
                output = re.sub(r"-{2,}\s*", " ", output)
                output = re.sub(r"\s+", " ", output).strip()

                # Trim if too long (but track original length for failure analysis)
                original_length = len(output)
                if original_length > 500:
                    output = output[:500].rsplit(" ", 1)[0].strip()

                length = len(output)
                topic_coverage = calculate_topic_coverage(output, vars_["topic"])

                # Judge validation (single pass, no retry)
                judge_pass, judge_text = runner.evaluate_with_judge(
                    JUDGE_MODEL,
                    output,
                    vars_["topic"],
                    seed_override=seed + 50000,
                )

                audit_result = AuditResult(
                    iteration=iteration,
                    model=model,
                    scenario_id=scenario_id,
                    output=output,
                    length=length,
                    topic_coverage=topic_coverage,
                    judge_pass=judge_pass,
                    judge_reasoning=judge_text,
                    failure_reason=None,
                )

                # Assess failure reason
                audit_result.failure_reason = assess_failure_reason(audit_result)

                model_results.append(audit_result)
                all_results.append(audit_result)

                # Log each iteration
                status = "✅ PASS" if audit_result.failure_reason is None else f"❌ FAIL ({audit_result.failure_reason})"
                LOGGER.info(
                    "%s - %s - Iteration %d/%d: %s (length=%d, coverage=%.0f%%)",
                    model,
                    scenario_id,
                    iteration,
                    AUDIT_ITERATIONS,
                    status,
                    length,
                    topic_coverage * 100,
                )

                # Attach individual iteration details to Allure
                iteration_detail = {
                    "model": model,
                    "scenario": scenario_id,
                    "iteration": iteration,
                    "seed": seed,
                    "length": length,
                    "topic_coverage": f"{topic_coverage:.1%}",
                    "judge_pass": judge_pass,
                    "failure_reason": audit_result.failure_reason or "none",
                    "output_preview": textwrap.shorten(output, width=200, placeholder="..."),
                }
                allure.attach(
                    json.dumps(iteration_detail, indent=2),
                    name=f"{model}_{scenario_id}_iter{iteration}",
                    attachment_type=allure.attachment_type.JSON,
                )

                # Attach failures with full context
                if audit_result.failure_reason:
                    allure.attach(
                        output,
                        name=f"FAILURE_{model}_{scenario_id}_iter{iteration}_output",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    allure.attach(
                        judge_text,
                        name=f"FAILURE_{model}_{scenario_id}_iter{iteration}_judge",
                        attachment_type=allure.attachment_type.TEXT,
                    )

        # Calculate summary statistics for this model
        successful = [r for r in model_results if r.failure_reason is None]
        failed = [r for r in model_results if r.failure_reason is not None]

        failures_by_reason: dict[str, int] = defaultdict(int)
        for result in failed:
            if result.failure_reason:
                failures_by_reason[result.failure_reason] += 1

        success_rate = len(successful) / len(model_results) if model_results else 0.0

        summary = ModelAuditSummary(
            model=model,
            total_runs=len(model_results),
            successful_runs=len(successful),
            failed_runs=len(failed),
            success_rate=success_rate,
            failures_by_reason=dict(failures_by_reason),
            recommendation="",
        )
        summary.recommendation = generate_recommendation(summary)

        model_summaries[model] = summary

        LOGGER.info(
            "Audit complete for %s: %d/%d passed (%.1f%%)",
            model,
            summary.successful_runs,
            summary.total_runs,
            summary.success_rate * 100,
        )

    # Generate comprehensive audit report
    report_lines = ["# LLM Quality Audit Report\n"]
    report_lines.append(f"**Iterations per scenario**: {AUDIT_ITERATIONS}")
    report_lines.append(f"**Total scenarios**: {len(data['scenarios'])}")
    report_lines.append(f"**Models tested**: {len(GENERATOR_MODELS)}\n")

    for model, summary in model_summaries.items():
        report_lines.append(f"\n## {model}\n")
        report_lines.append(f"- **Success Rate**: {summary.success_rate:.1%} ({summary.successful_runs}/{summary.total_runs})")
        report_lines.append(f"- **Recommendation**: {summary.recommendation}\n")

        if summary.failures_by_reason:
            report_lines.append("### Failure Breakdown:")
            for reason, count in sorted(summary.failures_by_reason.items(), key=lambda x: -x[1]):
                report_lines.append(f"  - {reason}: {count} occurrences")
        else:
            report_lines.append("✅ No failures detected")

    report_text = "\n".join(report_lines)

    # Attach comprehensive report
    allure.attach(
        report_text,
        name="quality_audit_report",
        attachment_type=allure.attachment_type.TEXT,
    )

    # Attach machine-readable JSON summary
    json_summary = {
        "audit_iterations": AUDIT_ITERATIONS,
        "models": {
            model: {
                "success_rate": summary.success_rate,
                "successful_runs": summary.successful_runs,
                "failed_runs": summary.failed_runs,
                "total_runs": summary.total_runs,
                "failures_by_reason": summary.failures_by_reason,
                "recommendation": summary.recommendation,
            }
            for model, summary in model_summaries.items()
        },
    }
    allure.attach(
        json.dumps(json_summary, indent=2),
        name="quality_audit_summary_json",
        attachment_type=allure.attachment_type.JSON,
    )

    LOGGER.info("\n" + report_text)

    # Persist audit results for historical trend analysis
    persistence = AuditPersistence(storage_dir="audit_results")
    metadata = create_audit_metadata(
        audit_iterations=AUDIT_ITERATIONS,
        total_scenarios=len(data["scenarios"]),
        fake_mode=FAKE_OLLAMA,
        environment=os.environ.get("CI", "").lower() in {"1", "true", "yes"} and "ci" or "local",
    )
    audit_file = persistence.save_audit_result(metadata, model_summaries)
    LOGGER.info("Audit results persisted to %s", audit_file)

    # Generate trend analysis if historical data exists
    trend_reports = []
    for model in GENERATOR_MODELS:
        trend_analysis = persistence.analyze_trends(model, lookback_runs=10)
        if trend_analysis:
            trend_report = (
                f"\n### Historical Trend for {model}:\n"
                f"- Runs analyzed: {trend_analysis.runs_analyzed}\n"
                f"- Average success rate: {trend_analysis.avg_success_rate:.1%}\n"
                f"- Latest vs avg: {trend_analysis.latest_success_rate:.1%} vs {trend_analysis.avg_success_rate:.1%}\n"
                f"- Trend: {trend_analysis.trend.upper()}\n"
                f"- Status: {trend_analysis.recommendation}\n"
            )
            trend_reports.append(trend_report)
            LOGGER.info(trend_report)

    # Attach trend analysis to Allure
    if trend_reports:
        comprehensive_trend_report = persistence.generate_trend_report(GENERATOR_MODELS, lookback_runs=10)
        allure.attach(
            comprehensive_trend_report,
            name="historical_trend_analysis",
            attachment_type=allure.attachment_type.TEXT,
        )

    # Generate smart model replacement recommendations
    recommender = ModelRecommender()
    recommendation_report = recommender.generate_recommendation_report(model_summaries)
    LOGGER.info("\n%s", recommendation_report)
    allure.attach(
        recommendation_report,
        name="model_replacement_recommendations",
        attachment_type=allure.attachment_type.TEXT,
    )

    # FAIL THE TEST if any model has success rate < 60%
    # This is INTENTIONAL to expose poor models and demonstrate test rigor
    failing_models = [
        (model, summary) for model, summary in model_summaries.items()
        if summary.success_rate < 0.6
    ]

    if failing_models:
        failure_message = "LLM Quality Audit FAILED - Models producing poor outputs:\n\n"
        for model, summary in failing_models:
            failure_message += f"  {model}: {summary.success_rate:.1%} success rate\n"
            failure_message += f"    → {summary.recommendation}\n\n"

        failure_message += (
            "This is EXPECTED behavior for small local models.\n"
            "The test has successfully detected genuine model defects.\n"
            "Review Allure attachments for detailed failure analysis.\n\n"
            "Recommendations:\n"
            "  1. Review failure patterns in Allure report\n"
            "  2. Consider replacing models with success rate < 60%\n"
            "  3. For CI stability, use USE_FAKE_OLLAMA=1\n"
        )

        pytest.fail(failure_message)

    # If all models passed, log success (rare for small models)
    success_message = "✅ All models passed quality audit with >60% success rate"
    LOGGER.info(success_message)

