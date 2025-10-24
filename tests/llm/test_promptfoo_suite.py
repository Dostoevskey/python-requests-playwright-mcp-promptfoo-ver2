from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import allure
import pytest

# Guard and timeout values
PROMPTFOO_TIMEOUT = 60  # seconds
PROMPTFOO_OPT_IN_FILE = ".enable_promptfoo"


@pytest.mark.llm
def test_promptfoo_eval(settings, tmp_path: Path) -> None:
    """
    Run Promptfoo evaluation as an integration test.
    - Requires npx available (Node.js).
    - Requires opt-in via an empty .enable_promptfoo file located beside the env file
      (to avoid accidental long-running runs in CI/local dev).
    - Times out after PROMPTFOO_TIMEOUT seconds to avoid hanging the test runner.
    """
    if shutil.which("npx") is None:
        pytest.skip("npx not available; install Node.js to run promptfoo evaluations")

    # Simple opt-in guard to avoid accidental runs
    env_dir = Path(settings.env_file).parent if settings.env_file else Path(".")
    if not (env_dir / PROMPTFOO_OPT_IN_FILE).exists() and not Path(PROMPTFOO_OPT_IN_FILE).exists():
        pytest.skip("Promptfoo evaluation is disabled; create a .enable_promptfoo file to opt in")

    config_paths = list(settings.promptfoo_configs)

    for config_path in config_paths:
        with allure.step(f"promptfoo eval: {config_path}"):
            report_path = tmp_path / f"promptfoo_report_{config_path.parent.name}.json"
            command = [
                "npx",
                "promptfoo",
                "eval",
                "--config",
                str(config_path),
                "--output",
                str(report_path),
            ]

            # Run with timeout to avoid hangs
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=PROMPTFOO_TIMEOUT,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                allure.attach(str(exc), name=f"promptfoo_timeout_{config_path.parent.name}", attachment_type=allure.attachment_type.TEXT)
                pytest.fail(f"promptfoo eval timed out for {config_path} after {PROMPTFOO_TIMEOUT}s")

            # Attach stdout/stderr unconditionally for diagnostics
            allure.attach(completed.stdout or "<no stdout>", name=f"promptfoo_stdout_{config_path.parent.name}", attachment_type=allure.attachment_type.TEXT)
            allure.attach(completed.stderr or "<no stderr>", name=f"promptfoo_stderr_{config_path.parent.name}", attachment_type=allure.attachment_type.TEXT)

            if completed.returncode != 0:
                pytest.fail(f"promptfoo eval failed for {config_path} with code {completed.returncode}\n\nSTDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}")

            if not report_path.exists():
                pytest.fail(f"promptfoo did not produce the expected report file for {config_path}")

            try:
                data = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raw = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else "<no file>"
                allure.attach(raw, name=f"promptfoo_report_raw_{config_path.parent.name}", attachment_type=allure.attachment_type.TEXT)
                pytest.fail(f"Unable to parse promptfoo report for {config_path}: {exc}")

            allure.attach(json.dumps(data, indent=2), name=f"promptfoo_report_{config_path.parent.name}", attachment_type=allure.attachment_type.JSON)

            prompts = data.get("results", {}).get("prompts", [])
            failing = [
                (prompt.get("label", prompt.get("raw", "<unknown>")), prompt.get("metrics", {}))
                for prompt in prompts
                if prompt.get("metrics", {}).get("testFailCount", 0) > 0
                or prompt.get("metrics", {}).get("testErrorCount", 0) > 0
            ]
            if failing:
                serialized = json.dumps(
                    [
                        {
                            "prompt": label,
                            "metrics": metrics,
                        }
                        for label, metrics in failing
                    ],
                    indent=2,
                )
                allure.attach(
                    serialized,
                    name=f"promptfoo_failures_{config_path.parent.name}",
                    attachment_type=allure.attachment_type.JSON,
                )
                pytest.fail(f"Promptfoo reported failures for {config_path}: see attachment for details")
