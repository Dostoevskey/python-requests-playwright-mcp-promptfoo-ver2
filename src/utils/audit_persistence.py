"""
Audit Result Persistence and Trend Analysis

Provides utilities to save, load, and analyze LLM audit results over time.
Detects model degradation and generates historical trend insights.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass
class AuditRunMetadata:
    """Metadata for an audit run."""

    run_id: str
    timestamp: str
    environment: str
    fake_mode: bool
    audit_iterations: int
    total_scenarios: int


@dataclass
class ModelPerformanceSnapshot:
    """Performance snapshot for a single model in one audit run."""

    model: str
    success_rate: float
    successful_runs: int
    failed_runs: int
    total_runs: int
    failures_by_reason: dict[str, int]
    recommendation: str


@dataclass
class AuditHistoryEntry:
    """Complete audit run result with metadata and per-model performance."""

    metadata: AuditRunMetadata
    models: dict[str, ModelPerformanceSnapshot]


@dataclass
class TrendAnalysis:
    """Trend analysis for a model across multiple runs."""

    model: str
    runs_analyzed: int
    avg_success_rate: float
    min_success_rate: float
    max_success_rate: float
    latest_success_rate: float
    trend: str  # "improving", "stable", "degrading"
    degradation_detected: bool
    recommendation: str


class AuditPersistence:
    """Manages audit result persistence and historical analysis."""

    def __init__(self, storage_dir: Path | str = "audit_results"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True, parents=True)
        self.index_file = self.storage_dir / "audit_index.json"
        LOGGER.info("Audit persistence initialized at %s", self.storage_dir)

    def save_audit_result(
        self,
        metadata: AuditRunMetadata,
        model_summaries: dict[str, Any],
    ) -> Path:
        """
        Save an audit result with metadata.

        Args:
            metadata: Run metadata
            model_summaries: Dict of model_name -> ModelAuditSummary

        Returns:
            Path to the saved audit file
        """
        # Convert summaries to snapshots
        snapshots: dict[str, ModelPerformanceSnapshot] = {}
        for model_name, summary in model_summaries.items():
            snapshots[model_name] = ModelPerformanceSnapshot(
                model=summary.model,
                success_rate=summary.success_rate,
                successful_runs=summary.successful_runs,
                failed_runs=summary.failed_runs,
                total_runs=summary.total_runs,
                failures_by_reason=summary.failures_by_reason,
                recommendation=summary.recommendation,
            )

        entry = AuditHistoryEntry(metadata=metadata, models=snapshots)

        # Save individual audit file
        audit_file = self.storage_dir / f"audit_{metadata.run_id}.json"
        audit_data = {
            "metadata": asdict(entry.metadata),
            "models": {name: asdict(snapshot) for name, snapshot in entry.models.items()},
        }
        audit_file.write_text(json.dumps(audit_data, indent=2))
        LOGGER.info("Saved audit result to %s", audit_file)

        # Update index
        self._update_index(metadata.run_id, metadata.timestamp, audit_file)

        return audit_file

    def _update_index(self, run_id: str, timestamp: str, audit_file: Path) -> None:
        """Update the audit index with a new entry."""
        if self.index_file.exists():
            index = json.loads(self.index_file.read_text())
        else:
            index = {"runs": []}

        index["runs"].append(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "file": str(audit_file.relative_to(self.storage_dir)),
            }
        )

        # Sort by timestamp descending (newest first)
        index["runs"].sort(key=lambda x: x["timestamp"], reverse=True)

        self.index_file.write_text(json.dumps(index, indent=2))
        LOGGER.debug("Updated audit index with run %s", run_id)

    def load_audit_history(self, limit: int | None = None) -> list[AuditHistoryEntry]:
        """
        Load audit history from disk.

        Args:
            limit: Maximum number of recent runs to load (None = all)

        Returns:
            List of audit history entries, newest first
        """
        if not self.index_file.exists():
            LOGGER.warning("No audit index found at %s", self.index_file)
            return []

        index = json.loads(self.index_file.read_text())
        runs = index.get("runs", [])

        if limit:
            runs = runs[:limit]

        history: list[AuditHistoryEntry] = []
        for run_entry in runs:
            audit_file = self.storage_dir / run_entry["file"]
            if not audit_file.exists():
                LOGGER.warning("Audit file not found: %s", audit_file)
                continue

            audit_data = json.loads(audit_file.read_text())

            # Reconstruct entry
            metadata = AuditRunMetadata(**audit_data["metadata"])
            models = {
                name: ModelPerformanceSnapshot(**snapshot_data)
                for name, snapshot_data in audit_data["models"].items()
            }
            entry = AuditHistoryEntry(metadata=metadata, models=models)
            history.append(entry)

        LOGGER.info("Loaded %d audit history entries", len(history))
        return history

    def analyze_trends(self, model_name: str, lookback_runs: int = 10) -> TrendAnalysis | None:
        """
        Analyze performance trends for a specific model.

        Args:
            model_name: Model to analyze
            lookback_runs: Number of recent runs to analyze

        Returns:
            TrendAnalysis or None if insufficient data
        """
        history = self.load_audit_history(limit=lookback_runs)
        if not history:
            LOGGER.warning("No audit history available for trend analysis")
            return None

        # Extract success rates for this model
        success_rates: list[float] = []
        for entry in history:
            if model_name in entry.models:
                success_rates.append(entry.models[model_name].success_rate)

        if not success_rates:
            LOGGER.warning("No data found for model %s in history", model_name)
            return None

        # Reverse to get chronological order (oldest first)
        success_rates_chronological = list(reversed(success_rates))
        latest_rate = success_rates[0]  # Most recent run

        # Calculate statistics
        avg_rate = sum(success_rates) / len(success_rates)
        min_rate = min(success_rates)
        max_rate = max(success_rates)

        # Determine trend
        if len(success_rates) >= 3:
            # Compare recent third vs older two thirds
            recent_avg = sum(success_rates[: len(success_rates) // 3]) / (len(success_rates) // 3)
            older_avg = sum(success_rates[len(success_rates) // 3 :]) / (
                len(success_rates) - len(success_rates) // 3
            )

            if recent_avg < older_avg - 0.1:
                trend = "degrading"
            elif recent_avg > older_avg + 0.1:
                trend = "improving"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Detect degradation (latest significantly below average)
        degradation_detected = latest_rate < avg_rate - 0.15

        # Generate recommendation
        if degradation_detected:
            recommendation = (
                f"⚠️ DEGRADATION DETECTED - Recent performance ({latest_rate:.1%}) "
                f"significantly below historical average ({avg_rate:.1%}). "
                "Investigate model, prompt, or data changes."
            )
        elif trend == "degrading":
            recommendation = (
                f"🟡 DECLINING TREND - Performance trending downward. "
                f"Monitor closely and consider model evaluation."
            )
        elif trend == "improving":
            recommendation = f"✅ IMPROVING - Performance trending upward ({avg_rate:.1%} avg)."
        elif latest_rate < 0.4:
            recommendation = (
                f"🔴 POOR PERFORMANCE - Success rate {latest_rate:.1%} is unacceptable. "
                "Replace model immediately."
            )
        elif latest_rate < 0.6:
            recommendation = (
                f"🟡 MARGINAL PERFORMANCE - Success rate {latest_rate:.1%}. "
                "Consider replacement or prompt optimization."
            )
        else:
            recommendation = f"✅ ACCEPTABLE - Performance stable at {latest_rate:.1%}."

        analysis = TrendAnalysis(
            model=model_name,
            runs_analyzed=len(success_rates),
            avg_success_rate=avg_rate,
            min_success_rate=min_rate,
            max_success_rate=max_rate,
            latest_success_rate=latest_rate,
            trend=trend,
            degradation_detected=degradation_detected,
            recommendation=recommendation,
        )

        LOGGER.info(
            "Trend analysis for %s: %s (%.1f%% avg, trend=%s)",
            model_name,
            "DEGRADATION" if degradation_detected else "NORMAL",
            avg_rate * 100,
            trend,
        )

        return analysis

    def generate_trend_report(self, models: list[str], lookback_runs: int = 10) -> str:
        """
        Generate a comprehensive trend report for multiple models.

        Args:
            models: List of model names to analyze
            lookback_runs: Number of recent runs to analyze

        Returns:
            Markdown-formatted trend report
        """
        report_lines = [
            "# LLM Model Performance Trend Report\n",
            f"**Analysis Period**: Last {lookback_runs} audit runs",
            f"**Generated**: {datetime.now(UTC).isoformat()}\n",
        ]

        for model in models:
            analysis = self.analyze_trends(model, lookback_runs)
            if not analysis:
                report_lines.append(f"\n## {model}\n")
                report_lines.append("⚠️ Insufficient data for trend analysis\n")
                continue

            report_lines.append(f"\n## {model}\n")
            report_lines.append(f"- **Runs Analyzed**: {analysis.runs_analyzed}")
            report_lines.append(f"- **Latest Success Rate**: {analysis.latest_success_rate:.1%}")
            report_lines.append(f"- **Average Success Rate**: {analysis.avg_success_rate:.1%}")
            report_lines.append(
                f"- **Range**: {analysis.min_success_rate:.1%} - {analysis.max_success_rate:.1%}"
            )
            report_lines.append(f"- **Trend**: {analysis.trend.upper()}")
            report_lines.append(f"- **Status**: {analysis.recommendation}\n")

        return "\n".join(report_lines)


def create_audit_metadata(
    audit_iterations: int,
    total_scenarios: int,
    fake_mode: bool = False,
    environment: str = "local",
) -> AuditRunMetadata:
    """
    Create audit metadata for the current run.

    Args:
        audit_iterations: Number of iterations per scenario
        total_scenarios: Total number of scenarios tested
        fake_mode: Whether using fake Ollama mode
        environment: Environment name (local, ci, etc.)

    Returns:
        AuditRunMetadata instance
    """
    now_utc = datetime.now(UTC)
    run_id = now_utc.strftime("%Y%m%d_%H%M%S")
    timestamp = now_utc.isoformat()

    return AuditRunMetadata(
        run_id=run_id,
        timestamp=timestamp,
        environment=environment,
        fake_mode=fake_mode,
        audit_iterations=audit_iterations,
        total_scenarios=total_scenarios,
    )


__all__ = [
    "AuditPersistence",
    "AuditRunMetadata",
    "ModelPerformanceSnapshot",
    "AuditHistoryEntry",
    "TrendAnalysis",
    "create_audit_metadata",
]

