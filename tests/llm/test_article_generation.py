from __future__ import annotations

import hashlib
import os
import re
import textwrap
from pathlib import Path

import allure
import pytest
import yaml
from jinja2 import Template

from src.utils.logger import get_logger
from src.utils.ollama_client import OllamaRunner

LOGGER = get_logger(__name__)

PROMPTS_FILE = Path("promptfoo/prompts/articles.yaml")
GENERATOR_MODELS = ["gemma3:4b", "deepseek-r1:8b"]
JUDGE_MODEL = "gpt-oss:20b"
default_fake = "1" if os.environ.get("CI", "").lower() in {"1", "true", "yes"} else "0"
FAKE_OLLAMA = os.environ.get("USE_FAKE_OLLAMA", default_fake).lower() in {"1", "true", "yes"}


@pytest.mark.llm
def test_local_article_generation(settings) -> None:
    if not PROMPTS_FILE.exists():
        pytest.skip(f"Prompt definitions missing; ensure {PROMPTS_FILE} is present")

    runner = OllamaRunner(settings.ollama_base_url)

    missing_models = [model for model in GENERATOR_MODELS + [JUDGE_MODEL] if not runner.ensure_model(model)]
    if missing_models:
        pytest.skip(f"Missing Ollama models: {', '.join(missing_models)}")

    data = yaml.safe_load(PROMPTS_FILE.read_text())
    prompt_template = next(prompt["template"] for prompt in data["prompts"] if prompt["id"] == "concise_article")
    template = Template(prompt_template)

    for scenario in data["scenarios"]:
        vars_ = scenario["vars"]
        rendered_prompt = template.render(**vars_)
        LOGGER.info("Evaluating LLM scenario %s", scenario["id"])
        allure.attach(
            rendered_prompt,
            name=f"prompt_{scenario['id']}",
            attachment_type=allure.attachment_type.TEXT,
        )
        if FAKE_OLLAMA:
            attempt_configs = [(120, 0.0)]
        else:
            # Reduced from 4 to 2 attempts to expose genuine model failures
            # while maintaining minimal stability against random flakiness
            attempt_configs = [
                (180, 0.25),
                (160, 0.15),
            ]

        for model in GENERATOR_MODELS:
            attempt_log: list[str] = []
            failure_log: list[str] = []
            output = ""
            success = False
            last_judge_text = ""
            stabilized = False
            LOGGER.debug("Running generator model %s for scenario %s", model, scenario["id"])
            seed_base = int(hashlib.md5(f"{scenario['id']}::{model}".encode()).hexdigest()[:8], 16)
            for index, (max_tokens, temp) in enumerate(attempt_configs, start=1):
                options = {"temperature": temp, "num_predict": max_tokens, "seed": seed_base + index}
                result = runner.generate(model, rendered_prompt, options=options)
                output = result.output.strip()
                output = re.sub(r"-{2,}\s*", " ", output)
                output = re.sub(r"\s+", " ", output).strip()
                length = len(output)
                note = (
                    f"attempt {index} (num_predict={max_tokens}, temp={temp}, seed={seed_base + index})"
                    f": raw={length} chars"
                )
                if length > 500:
                    trimmed = output[:500].rsplit(" ", 1)[0].strip()
                    output = trimmed
                    length = len(output)
                    note += f", trimmed={length}"
                if length < 300:
                    attempt_log.append(f"{note} -> too short")
                    continue
                topic_terms = {term.lower() for term in re.findall(r"[A-Za-z]+", vars_["topic"]) if len(term) > 3}
                matched_terms = {term for term in topic_terms if term in output.lower()}
                if topic_terms:
                    note += f", keywords={len(matched_terms)}/{len(topic_terms)}"
                    required_matches = 1 if len(topic_terms) <= 1 else min(2, len(topic_terms))
                    if len(matched_terms) < required_matches:
                        missing_terms = ", ".join(sorted(topic_terms - matched_terms)[:3])
                        attempt_log.append(f"{note} -> insufficient topic coverage ({missing_terms})")
                        continue
                judge_pass, judge_text = runner.evaluate_with_judge(
                    JUDGE_MODEL,
                    output,
                    vars_["topic"],
                    seed_override=seed_base + 97,
                )
                last_judge_text = judge_text
                note_with_judge = f"{note}, judge={'PASS' if judge_pass else 'FAIL'}"
                if not judge_pass and not FAKE_OLLAMA:
                    retry_pass, retry_text = runner.evaluate_with_judge(
                        JUDGE_MODEL,
                        output,
                        vars_["topic"],
                        seed_override=seed_base + 197,
                    )
                    note_with_judge += f", retry_judge={'PASS' if retry_pass else 'FAIL'}"
                    if retry_pass:
                        judge_pass = True
                        last_judge_text = retry_text
                        stabilized = True
                attempt_log.append(note_with_judge)
                if not judge_pass:
                    failure_log.append(note_with_judge)
                    allure.attach(
                        textwrap.shorten(output, width=800, placeholder="..."),
                        name=f"{scenario['id']}_{model}_attempt{index}_failure_output",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    if judge_text:
                        allure.attach(
                            judge_text,
                            name=f"{scenario['id']}_{model}_attempt{index}_judge_reason",
                            attachment_type=allure.attachment_type.TEXT,
                        )
                if judge_pass:
                    success = True
                    LOGGER.info(
                        "Scenario %s model %s satisfied judge on attempt %d",
                        scenario["id"],
                        model,
                        index,
                    )
                    break
            if not success:
                allure.attach(
                    "\n".join(attempt_log),
                    name=f"{scenario['id']}_{model}_attempts",
                    attachment_type=allure.attachment_type.TEXT,
                )
                allure.attach(
                    last_judge_text,
                    name=f"{scenario['id']}_{model}_judge_reason",
                    attachment_type=allure.attachment_type.TEXT,
                )
                LOGGER.error("Scenario %s failed for model %s", scenario["id"], model)
                pytest.fail(f"{model} could not satisfy judge for scenario {scenario['id']}")

            if stabilized and failure_log:
                allure.attach(
                    "\n".join(failure_log),
                    name=f"{scenario['id']}_{model}_recovered_failures",
                    attachment_type=allure.attachment_type.TEXT,
                )

            allure.attach(
                textwrap.shorten(output, width=800, placeholder="..."),
                name=f"{scenario['id']}_{model}",
                attachment_type=allure.attachment_type.TEXT,
            )
            allure.attach(
                "\n".join(attempt_log),
                name=f"{scenario['id']}_{model}_lengths",
                attachment_type=allure.attachment_type.TEXT,
            )
            if last_judge_text:
                allure.attach(
                    last_judge_text,
                    name=f"{scenario['id']}_{model}_judge",
                    attachment_type=allure.attachment_type.TEXT,
                )
