#!/usr/bin/env python3
"""GitHub Actions runner for Sybil pipeline. Called by sybil-pipeline.yml"""
import subprocess, sys, os, json, csv
from pathlib import Path

os.chdir(Path(__file__).parent.parent)

def generate_dashboard():
    """Generate dashboard JSON + copy reports to docs/"""
    os.makedirs("docs", exist_ok=True)
    
    # Copy latest report
    for src in ["reports/output/latest_report.md", "reports/output/latest_scores.csv"]:
        dst = f"docs/sybil_{Path(src).name}"
        if os.path.exists(src):
            import shutil
            shutil.copy2(src, dst)
            print(f"Copied {src} → {dst}")
    
    # Create summary JSON
    csv_path = "reports/output/latest_scores.csv"
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            wallets = list(csv.DictReader(f))
        
        high = len([w for w in wallets if w.get("risk_level") == "HIGH"])
        med = len([w for w in wallets if w.get("risk_level") == "MEDIUM"])
        low = len([w for w in wallets if w.get("risk_level") == "LOW"])
        
        from datetime import datetime, timezone
        summary = {
            "total_wallets": len(wallets),
            "high_risk": high,
            "med_risk": med,
            "low_risk": low,
            "sybil_pct": f"{(high+med)/len(wallets)*100:.1f}" if wallets else "0",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open("docs/sybil_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Dashboard summary: {summary}")
    else:
        print("No scores CSV found. Skipping dashboard.")

def get_summary_line():
    """Get a one-line summary for the commit message."""
    csv_path = "reports/output/latest_scores.csv"
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            wallets = list(csv.DictReader(f))
        high = len([w for w in wallets if w.get("risk_level") == "HIGH"])
        total = len(wallets)
        return f"{total} wallets, {high} high risk"
    return "analysis complete"

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--airdrop", default="synthetic")
    parser.add_argument("--wallets", type=int, default=300)
    args = parser.parse_args()
    
    print(f"🚀 Sybil Pipeline — airdrop={args.airdrop}, wallets={args.wallets}")
    
    # Run the analysis
    cmd = [sys.executable, "scripts/auto_analyze.py"]
    if args.airdrop == "synthetic":
        cmd.extend(["--test", "--wallets", str(args.wallets)])
    else:
        cmd.extend(["--airdrop", args.airdrop, "--wallets", str(args.wallets)])
    
    result = subprocess.run(cmd, capture_output=False, timeout=600)
    
    # Generate dashboard
    generate_dashboard()
    
    # Output for GH Actions
    summary = get_summary_line()
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"summary={summary}\n")
    
    print(f"\n✅ Sybil pipeline complete. {summary}")

if __name__ == "__main__":
    main()
