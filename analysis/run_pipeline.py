#!/usr/bin/env python3
"""
run_pipeline.py — Full Sybil Detection Pipeline Orchestrator

Builds funding graphs from transaction data, runs ML clustering,
calculates Sybil scores, evaluates against ground truth, and exports.

Usage:
    python analysis/run_pipeline.py [--data-dir data/synthetic]
"""

import argparse
import json
import logging
import os
import pickle
import sys
from typing import Dict, List, Any, Optional
from collections import defaultdict

import networkx as nx
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.cluster_detector import ClusterDetector
from analysis.score_calculator import ScoreCalculator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_pipeline")


def load_data(data_dir: str) -> dict:
    """Load synthetic/real data from directory."""
    paths = {
        "transactions": os.path.join(data_dir, "transactions.json"),
        "funding_sources": os.path.join(data_dir, "funding_sources.json"),
        "timestamps": os.path.join(data_dir, "timestamps.json"),
        "amounts": os.path.join(data_dir, "amounts.json"),
        "first_seen": os.path.join(data_dir, "first_seen.json"),
        "ground_truth": os.path.join(data_dir, "ground_truth.json"),
    }

    data = {}
    for key, path in paths.items():
        if os.path.exists(path):
            with open(path) as f:
                data[key] = json.load(f)
            logger.info(f"  Loaded {key}: {os.path.getsize(path)} bytes")
        else:
            logger.warning(f"  Missing {key}: {path}")
            data[key] = None
    return data


def build_funding_graph(funding_sources: dict) -> nx.Graph:
    """
    Build undirected funding graph:
    Wallets are connected if they share a common funding source.
    This is the KEY graph structure for Sybil detection.
    """
    # Invert: funder -> set of wallets
    funder_to_wallets = defaultdict(set)
    for funder, recipients in funding_sources.items():
        for r in recipients:
            funder_to_wallets[funder].add(r)

    G = nx.Graph()
    # Connect wallets that share a funder
    for funder, wallets in funder_to_wallets.items():
        wallets = list(wallets)
        if len(wallets) < 2:
            # If only one wallet funded, add it as isolated node
            if wallets:
                G.add_node(wallets[0])
            continue
        for i in range(len(wallets)):
            for j in range(i + 1, len(wallets)):
                w1, w2 = wallets[i], wallets[j]
                edge_data = G.get_edge_data(w1, w2) or {}
                G.add_edge(
                    w1, w2,
                    shared_funders=edge_data.get("shared_funders", 0) + 1,
                )

    logger.info(
        f"Built funding graph: {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges"
    )
    return G


def evaluate_results(
    scores_report: dict,
    ground_truth: dict,
) -> dict:
    """Evaluate pipeline results against ground truth."""
    gt = ground_truth.get("wallets", {})
    total = len(gt)

    results = {
        "total_wallets": total,
        "true_sybil": sum(1 for v in gt.values() if v["is_sybil"]),
        "true_honest": sum(1 for v in gt.values() if not v["is_sybil"]),
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
    }

    for ws in scores_report.get("wallets_scored", []):
        addr = ws.get("address", "").lower()
        # Normalize address for matching
        matched = False
        for gt_addr, gt_val in gt.items():
            if gt_addr.lower() == addr:
                matched = True
                predicted_sybil = ws.get("is_sybil", False)
                actual_sybil = gt_val["is_sybil"]
                if predicted_sybil and actual_sybil:
                    results["true_positives"] += 1
                elif predicted_sybil and not actual_sybil:
                    results["false_positives"] += 1
                elif not predicted_sybil and not actual_sybil:
                    results["true_negatives"] += 1
                elif not predicted_sybil and actual_sybil:
                    results["false_negatives"] += 1
                break

    tp = results["true_positives"]
    fp = results["false_positives"]
    fn = results["false_negatives"]
    tn = results["true_negatives"]

    results["precision"] = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    results["recall"] = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    results["f1_score"] = round(
        2 * results["precision"] * results["recall"] / (results["precision"] + results["recall"]),
        4,
    ) if (results["precision"] + results["recall"]) > 0 else 0.0
    results["accuracy"] = round((tp + tn) / total, 4) if total > 0 else 0.0
    results["false_positive_rate"] = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0

    # Mean scores
    sybil_scores = []
    honest_scores = []
    for ws in scores_report.get("wallets_scored", []):
        for gt_addr, gt_val in gt.items():
            if gt_addr.lower() == ws.get("address", "").lower():
                if gt_val["is_sybil"]:
                    sybil_scores.append(ws.get("sybil_score", 0))
                else:
                    honest_scores.append(ws.get("sybil_score", 0))
                break

    results["mean_sybil_score"] = round(float(np.mean(sybil_scores)), 2) if sybil_scores else 0.0
    results["mean_honest_score"] = round(float(np.mean(honest_scores)), 2) if honest_scores else 0.0
    results["score_separation"] = round(results["mean_sybil_score"] - results["mean_honest_score"], 2)

    return results


def format_cluster_visualization(clusters: list, max_display: int = 20) -> str:
    """Create a text-based visualization of clusters."""
    lines = []
    lines.append("")
    lines.append("TEXT-BASED CLUSTER MAP")
    lines.append("=" * 60)
    lines.append("")

    # Filter out noise cluster (-1)
    display_clusters = [c for c in clusters if c.get("cluster_id", -1) >= 0]
    display_clusters = sorted(display_clusters, key=lambda c: c.get("size", 0), reverse=True)

    for i, c in enumerate(display_clusters[:max_display]):
        size = c.get("size", 0)
        conf = c.get("confidence", 0)
        is_syb = c.get("is_sybil", False)
        cid = c.get("cluster_id", i)
        label = "SYBIL" if is_syb else "UNSURE"

        bar_len = min(size, 50)
        bar = "█" * bar_len
        line = f"  Cluster #{cid:2d} |{bar:50s}| n={size:3d}  {label}  conf={conf:.2f}"
        lines.append(line)

    if len(display_clusters) > max_display:
        lines.append(f"  ... and {len(display_clusters) - max_display} more clusters")

    lines.append("")
    total_clusters = len(display_clusters)
    total_wallets_in_clusters = sum(c.get("size", 0) for c in display_clusters)
    lines.append(f"  Total clusters: {total_clusters}  |  Total wallets in clusters: {total_wallets_in_clusters}")
    lines.append("  Legend: █ = wallets in cluster, SYBIL = high-confidence Sybil")
    lines.append("")
    return "\n".join(lines)


def format_score_distribution(dist: dict) -> str:
    """Create text-based score distribution chart."""
    lines = []
    lines.append("SCORE DISTRIBUTION")
    lines.append("-" * 50)
    labels = [
        ("high_risk_75_100",   "  High Risk (75-100)  "),
        ("medium_risk_50_74",  "  Medium Risk (50-74) "),
        ("low_risk_25_49",    "  Low Risk (25-49)    "),
        ("minimal_risk_0_24",  "  Minimal Risk (0-24) "),
    ]
    total = sum(dist.values()) or 1
    for key, label in labels:
        count = dist.get(key, 0)
        pct = count / total * 100
        bar_len = int(pct / 2)
        bar = "▓" * bar_len + "░" * max(0, 25 - bar_len)
        lines.append(f"{label}: {count:4d} ({pct:5.1f}%) |{bar}|")
    lines.append(f"{'─' * 50}")
    lines.append(f"  Total: {total}")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run Sybil Detection Pipeline")
    parser.add_argument(
        "--data-dir",
        default="data/synthetic",
        help="Directory with pre-generated data (default: data/synthetic)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/output",
        help="Directory for output reports (default: reports/output)",
    )
    parser.add_argument(
        "--method",
        default="dbscan",
        choices=["dbscan", "hierarchical"],
        help="Clustering method (default: dbscan)",
    )
    parser.add_argument(
        "--eps",
        type=float,
        default=0.5,
        help="DBSCAN eps parameter (default: 0.5)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=2,
        help="DBSCAN min_samples parameter (default: 2)",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("\n" + "=" * 60)
    print("  SYBIL DETECTION ORACLE")
    print("  On-Chain Sybil Analysis Pipeline")
    print("=" * 60)

    # =========================================================
    # STEP 1: Load Data
    # =========================================================
    print("\n[Step 1/5] Loading Data...")
    data = load_data(args.data_dir)

    transactions = data.get("transactions", [])
    funding_sources = data.get("funding_sources", {})
    timestamps = data.get("timestamps", {})
    amounts = data.get("amounts", {})
    first_seen = data.get("first_seen", {})
    ground_truth = data.get("ground_truth")

    if not funding_sources or not transactions:
        logger.error("No data found. Run scripts/generate_synthetic_data.py first.")
        sys.exit(1)

    print(f"  Transactions: {len(transactions)}")
    print(f"  Funding sources: {len(funding_sources)}")

    # =========================================================
    # STEP 2: Build Funding Graph (the KEY graph for Sybil detection)
    # =========================================================
    print("\n[Step 2/5] Building Funding Graph...")
    G = build_funding_graph(funding_sources)

    print(f"  Funding graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  Connected components: {nx.number_connected_components(G)}")

    # Analyze components
    components = sorted(nx.connected_components(G), key=len, reverse=True)
    print(f"  Largest component: {len(components[0])} wallets" if components else "  No components")
    for i, comp in enumerate(components[:5]):
        print(f"    Component {i+1}: {len(comp)} wallets")
    if len(components) > 5:
        print(f"    ... and {len(components)-5} more components")

    # =========================================================
    # STEP 3: Feature Extraction & Clustering
    # =========================================================
    print(f"\n[Step 3/5] Running {args.method.upper()} Clustering...")

    detector = ClusterDetector(
        eps=args.eps,
        min_samples=args.min_samples,
        confidence_threshold=0.5,
        random_state=42,
    )

    # Pre-warm by building subgraph of wallets that are in funding_sources
    all_funded_wallets = set()
    for funder, recipients in funding_sources.items():
        for r in recipients:
            all_funded_wallets.add(r)

    # Also include funders as nodes
    all_wallets_in_funding = set(G.nodes())

    clustering_output = detector.detect(
        G,
        method=args.method,
        wallet_subset=list(all_wallets_in_funding) if len(all_wallets_in_funding) > 0 else None,
    )

    print(f"  Algorithm: {clustering_output.algorithm_used}")
    print(f"  Clusters found: {len(clustering_output.clusters)}")
    print(f"  Noise wallets: {len(clustering_output.noise_wallets)}")
    print(f"  Silhouette score: {clustering_output.silhouette_score}")

    detector.export_clusters(clustering_output, f"{args.output_dir}/clusters.json")

    # =========================================================
    # STEP 4: Score Computation
    # =========================================================
    print("\n[Step 4/5] Calculating Sybil Scores...")

    clusters_dicts = [c.to_dict() for c in clustering_output.clusters]
    calculator = ScoreCalculator()

    report = calculator.generate_report(
        graph=G,
        clusters=clusters_dicts,
        funding_sources=funding_sources,
        tx_timestamps=timestamps,
        tx_amounts=amounts,
        first_seen_timestamps=first_seen,
    )

    print(f"  Wallets scored: {report.total_wallets}")
    print(f"  Sybil wallets detected: {report.sybil_wallets}")
    print(f"  Average Sybil score: {report.average_sybil_score:.2f}")

    # Export
    scores_path = calculator.export_report(report, f"{args.output_dir}/scores.json")
    onchain_path = calculator.export_onchain_payload(report, f"{args.output_dir}/onchain_payload.json")
    print(f"  Scores exported to: {scores_path}")
    print(f"  On-chain payload: {onchain_path}")

    # =========================================================
    # STEP 5: Evaluation & Summary
    # =========================================================
    print("\n[Step 5/5] Evaluation & Summary...")

    eval_results = {}
    if ground_truth:
        eval_results = evaluate_results(report.to_dict(), ground_truth)
        print(f"\n  ┌────────────────────────────────────────────┐")
        print(f"  │         EVALUATION AGAINST GROUND TRUTH        │")
        print(f"  ├────────────────────────────────────────────┤")
        print(f"  │  True Positives:   {eval_results['true_positives']:5d}                   │")
        print(f"  │  False Positives:  {eval_results['false_positives']:5d}                   │")
        print(f"  │  True Negatives:   {eval_results['true_negatives']:5d}                   │")
        print(f"  │  False Negatives:  {eval_results['false_negatives']:5d}                   │")
        print(f"  ├────────────────────────────────────────────┤")
        print(f"  │  Precision:        {eval_results['precision']:7.2%}               │")
        print(f"  │  Recall:           {eval_results['recall']:7.2%}               │")
        print(f"  │  F1 Score:         {eval_results['f1_score']:7.4f}               │")
        print(f"  │  Accuracy:         {eval_results['accuracy']:7.2%}               │")
        print(f"  │  False Pos Rate:   {eval_results['false_positive_rate']:7.2%}               │")
        print(f"  ├────────────────────────────────────────────┤")
        print(f"  │  Mean Sybil Score:  {eval_results['mean_sybil_score']:5.1f}                │")
        print(f"  │  Mean Honest Score: {eval_results['mean_honest_score']:5.1f}                │")
        print(f"  │  Score Separation:  {eval_results['score_separation']:5.1f}                │")
        print(f"  └────────────────────────────────────────────┘")

        with open(f"{args.output_dir}/evaluation.json", "w") as f:
            json.dump(eval_results, f, indent=2)
    else:
        print("  No ground truth data — skipping evaluation.")

    # Score distribution
    print("\n" + format_score_distribution(report.score_distribution))

    # Cluster visualization
    print(format_cluster_visualization(clusters_dicts))

    # Top scoring wallets
    print("TOP 10 HIGHEST-SCORING WALLETS")
    print("-" * 60)
    print(f"  {'Address':<30} {'Score':>6} {'Cluster':>8} {'Status':>10}")
    print(f"  {'─' * 30} {'─' * 6} {'─' * 8} {'─' * 10}")
    for ws in report.wallets_scored[:10]:
        flag = "⚠ SYBIL" if ws.is_sybil else "✓ OK"
        print(f"  {ws.address[:30]:30} {ws.sybil_score:6.1f} {ws.cluster_id:8d} {flag:>10}")

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  All reports saved to: {args.output_dir}/")
    print("=" * 60 + "\n")

    return eval_results


if __name__ == "__main__":
    main()
