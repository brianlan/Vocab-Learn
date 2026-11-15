"""Probe the configured example preparation; calls incur provider charges.

Default mode is the RAW generator: unedited Generator outputs for explicit human review.
--review mode is the FULL reviewed pipeline: generation plus one Example Quality Review call
that accepts, repairs or replaces the pair, followed by deterministic validation. The two
modes are separate evaluations; never compare a raw result against a reviewed verdict.
"""
import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from learning import providers


def probe(cases, repeats=1, review=False):
    assert cases and len({case["id"] for case in cases}) == len(cases)
    assert repeats >= 1
    profile = providers.profile("GENERATOR")

    def run(case, repeat):
        started = time.monotonic()
        row = {"case_id": case["id"], "repeat": repeat}
        try:
            if review:
                local.candidate = None
                try:
                    row["data"], row["provenance"] = providers.generate(dict(case["source"]))
                    row["verdict"] = row["provenance"]["reviewer"]["verdict"]
                    row["reviewer_issues"] = row["provenance"]["reviewer"]["issues"]
                    row["status"] = "reviewed"
                finally:
                    row["raw"] = local.candidate  # kept on failure too: the draft arrived before the reviewer failed
            else:
                row["raw"] = providers.chat(profile, providers.GENERATOR_RULES, case["source"])
                row["data"] = providers.validate_pair(row["raw"], case["source"]["word"], case["source"]["native_language"])
                previous = case["source"].get("previous_pair")
                if previous and any(row["data"][key] == previous[key] for key in ["target_sentence", "native_sentence"]):
                    raise providers.StageError("GENERATOR", "The replacement repeated an old sentence.")
                row["status"] = "needs_semantic_review"
        except providers.StageError as error:
            row.update(status="failed", error=str(error), category=error.category, stage=error.stage)
        row["seconds"] = round(time.monotonic() - started, 2)
        return row

    rows = []
    local = threading.local()
    if review:
        # Observe the generator payload inside the real generate() call without changing its contract.
        original_chat = providers.chat
        def recording_chat(profile_, rules, payload):
            result = original_chat(profile_, rules, payload)
            if profile_.task == "GENERATOR":
                local.candidate = result
            return result
        providers.chat = recording_chat
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(run, case, repeat) for repeat in range(1, repeats + 1) for case in cases]
            for future in as_completed(pending):
                row = future.result()
                rows.append(row)
                print(row["case_id"], row["repeat"], row["status"], row["seconds"], flush=True)
    finally:
        if review:
            providers.chat = original_chat
    assert len(rows) == len(cases) * repeats
    report = {"prompt_version": providers.PROMPT_VERSIONS["GENERATOR"],
              "prompt_sha256": hashlib.sha256(providers.GENERATOR_RULES.encode()).hexdigest(),
              "prompt": providers.GENERATOR_RULES, "profile": profile.metadata(), "cases": cases,
              "results": sorted(rows, key=lambda row: (row["case_id"], row["repeat"]))}
    if review:
        reviewer = providers.profile("EXAMPLE_REVIEWER")
        report.update({"mode": "reviewed_pipeline", "reviewer_prompt_version": providers.PROMPT_VERSIONS["EXAMPLE_REVIEWER"],
                       "reviewer_prompt_sha256": hashlib.sha256(providers.EXAMPLE_REVIEW_RULES.encode()).hexdigest(),
                       "reviewer_prompt": providers.EXAMPLE_REVIEW_RULES, "reviewer_profile": reviewer.metadata()})
    else:
        report.update({"mode": "raw_generator", "status": "needs_semantic_review"})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Acknowledge paid calls to the configured Generator.")
    parser.add_argument("--review", action="store_true", help="Run the full reviewed pipeline (generation + one Example Quality Review call) instead of the raw generator.")
    parser.add_argument("--cases", type=Path, default=Path("docs/research/generator-regression-cases.json"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if not options.live or options.repeat < 1:
        parser.error("Pass --live and a positive --repeat count.")
    report = probe(json.loads(options.cases.read_text()), options.repeat, review=options.review)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    options.output.chmod(0o600)
    raise SystemExit(1 if any(row["status"] == "failed" for row in report["results"]) else 0)
