#!/usr/bin/env python3
"""
generate_summary.py — Generate a GitHub Actions step summary from analysis results.
Called by .github/workflows/analyze.yml after scoring completes.
"""

import json
import os

SCORES_PATH = "reports/output/scores.json"

if not os.path.exists(SCORES_PATH):
    print("No scores found — analysis may have failed.")
    exit(1)

with open(SCORES_PATH) as f:
    report = json.load(f)

summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
if summary_file:
    with open(summary_file, "a") as out:
        out.write(f"**Wallets analyzed**: {report['total_wallets']}\n\n")
        out.write(f"**Sybil wallets detected**: {report['sybil_wallets']}\n\n")
        out.write(f"**Average Sybil score**: {report['average_sybil_score']}\n\n")
        out.write("**Score distribution**:\n\n")
        for k, v in report.get("score_distribution", {}).items():
            out.write(f"- {k}: {v}\n")
else:
    # Fallback: print to stdout
    print(f"Wallets analyzed: {report['total_wallets']}")
    print(f"Sybil wallets detected: {report['sybil_wallets']}")
    print(f"Average Sybil score: {report['average_sybil_score']}")
    print("Score distribution:")
    for k, v in report.get("score_distribution", {}).items():
        print(f"  {k}: {v}")
