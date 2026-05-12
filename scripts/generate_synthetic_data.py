#!/usr/bin/env python3
"""
generate_synthetic_data.py — Generate realistic synthetic wallet data for Sybil detection.

Produces:
- 500+ wallet profiles with transaction histories
- Known Sybil patterns: same funding source, coordinated timing, linear transfer chains
- Legitimate users: diverse interactions, random timing, unique funders
- Ground truth labels for validation

Output: data/synthetic/ directory with wallets, transactions, and ground truth.
"""

import json
import random
import hashlib
import os
import sys
import pickle
from typing import Dict, List, Tuple
from collections import defaultdict

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import networkx as nx

random.seed(42)
np.random.seed(42)

OUTPUT_DIR = "data/synthetic"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs("reports/output", exist_ok=True)


def pseudo_address(seed: str) -> str:
    """Generate a deterministic pseudo-Ethereum address from a seed string."""
    h = hashlib.sha256(seed.encode()).hexdigest()[:40]
    return "0x" + h


def generate_sybil_cluster(
    cluster_id: int,
    num_wallets: int,
    funder_address: str,
    base_timestamp: int,
    interaction_count: int = 5,
    amount_mean: float = 0.1,
    amount_std: float = 0.01,
    timing_spread: int = 3600,  # 1 hour spread
) -> Tuple[List[Dict], Dict, Dict, Dict]:
    """
    Generate a Sybil cluster: multiple wallets funded by same address,
    with coordinated timing and nearly identical amounts.
    """
    wallets = []
    tx_timestamps: Dict[str, List[int]] = {}
    tx_amounts: Dict[str, List[float]] = {}
    first_seen: Dict[str, int] = {}

    for i in range(num_wallets):
        addr = pseudo_address(f"sybil_cluster_{cluster_id}_wallet_{i}")
        wallets.append(addr)

        # Funding transaction from funder -> wallet
        funding_time = base_timestamp + random.randint(0, timing_spread)
        fund_tx = {
            "hash": pseudo_address(f"tx_fund_{cluster_id}_{i}"),
            "from": funder_address,
            "to": addr,
            "value": amount_mean + random.gauss(0, amount_std * 0.5),
            "block": funding_time // 12,
            "timestamp": funding_time,
        }
        tx_timestamps[addr] = []
        tx_amounts[addr] = []

        # Transactions from wallet (coordinated)
        for j in range(interaction_count):
            tx_time = funding_time + (j * 86400) + random.randint(0, 600)  # same day, same hour
            tx_val = amount_mean + random.gauss(0, amount_std)
            tx_to = pseudo_address(f"sybil_target_{cluster_id}_{j}")
            tx = {
                "hash": pseudo_address(f"tx_act_{cluster_id}_{i}_{j}"),
                "from": addr,
                "to": tx_to,
                "value": max(0.001, tx_val),
                "block": tx_time // 12,
                "timestamp": tx_time,
            }
            tx_timestamps[addr].append(tx_time)
            tx_amounts[addr].append(max(0.001, tx_val))

        # Consolidation transaction back to funder
        cons_time = funding_time + (interaction_count * 86400) + random.randint(0, 3600)
        cons_tx = {
            "hash": pseudo_address(f"tx_cons_{cluster_id}_{i}"),
            "from": addr,
            "to": funder_address,
            "value": amount_mean * interaction_count,
            "block": cons_time // 12,
            "timestamp": cons_time,
        }
        tx_timestamps[addr].append(cons_time)
        tx_amounts[addr].append(amount_mean * interaction_count)

        first_seen[addr] = funding_time

    return wallets, tx_timestamps, tx_amounts, first_seen


def generate_honest_wallet(
    wallet_id: int,
    num_funders: int = 2,
    num_counterparties: int = 8,
    base_timestamp: int = 1700000000,
    age_days_range: Tuple[int, int] = (180, 800),
) -> Tuple[str, List[Dict], Dict, Dict, Dict]:
    """
    Generate a legitimate wallet with diverse interactions, multiple funders,
    random timing, and long history.
    """
    addr = pseudo_address(f"honest_wallet_{wallet_id}")
    tx_timestamps: Dict[str, List[int]] = {addr: []}
    tx_amounts: Dict[str, List[float]] = {addr: []}
    tx_list = []

    age_days = random.randint(*age_days_range)
    wallet_birth = base_timestamp - (age_days * 86400)

    # Multiple funding sources (organic)
    funders = [pseudo_address(f"honest_funder_{wallet_id}_{k}") for k in range(num_funders)]
    for funder in funders:
        ft = wallet_birth + random.randint(0, 30 * 86400)
        val = random.uniform(0.5, 5.0)
        tx_list.append({
            "hash": pseudo_address(f"htx_fund_{wallet_id}_{funder[-8:]}"),
            "from": funder,
            "to": addr,
            "value": val,
            "block": ft // 12,
            "timestamp": ft,
        })
        tx_timestamps[addr].append(ft)
        tx_amounts[addr].append(val)

    # Diverse interactions over time
    counterparties = [pseudo_address(f"honest_cp_{wallet_id}_{k}") for k in range(num_counterparties)]
    for j, cp in enumerate(counterparties):
        tx_time = wallet_birth + random.randint((j * 30 + 1) * 86400, (j * 30 + 15) * 86400)
        val = random.uniform(0.01, 2.0)
        direction = "from" if random.random() < 0.5 else "to"
        tx_from = addr if direction == "to" else cp
        tx_to = cp if direction == "to" else addr
        tx_list.append({
            "hash": pseudo_address(f"htx_act_{wallet_id}_{j}"),
            "from": tx_from,
            "to": tx_to,
            "value": val,
            "block": tx_time // 12,
            "timestamp": tx_time,
        })
        tx_timestamps[addr].append(tx_time)
        tx_amounts[addr].append(val)

    return addr, tx_list, tx_timestamps, tx_amounts, {addr: wallet_birth}


def main():
    print("=== Generating Synthetic Wallet Data ===\n")

    all_timestamps: Dict[str, List[int]] = {}
    all_amounts: Dict[str, List[float]] = {}
    all_first_seen: Dict[str, int] = {}
    all_transactions: List[Dict] = []
    ground_truth: Dict[str, bool] = {}  # address -> is_sybil

    # =========================================================
    # SYBIL CLUSTERS
    # =========================================================
    sybil_configs = [
        # (cluster_id, num_wallets, funder_seed, base_timestamp)
        (1, 15, "sybil_funder_1", 1700000000),
        (2, 10, "sybil_funder_2", 1700100000),
        (3, 8,  "sybil_funder_3", 1700200000),
        (4, 20, "sybil_funder_4", 1700300000),  # Large cluster
        (5, 6,  "sybil_funder_5", 1700400000),
        (6, 12, "sybil_funder_6", 1700500000),
        (7, 7,  "sybil_funder_7", 1700600000),
        (8, 5,  "sybil_funder_8", 1700700000),
        (9, 18, "sybil_funder_9", 1700800000),  # Another large one
        (10, 9, "sybil_funder_10", 1700900000),
    ]

    total_sybil_wallets = 0
    for cid, n, fseed, bt in sybil_configs:
        funder = pseudo_address(fseed)
        wallets, txs_ts, txs_amt, first_seen_map = generate_sybil_cluster(
            cid, n, funder, bt,
            interaction_count=random.randint(3, 7),
            amount_mean=random.uniform(0.05, 0.3),
            amount_std=random.uniform(0.005, 0.02),
            timing_spread=random.randint(600, 7200),  # 10min to 2hr
        )
        total_sybil_wallets += n
        for w in wallets:
            ground_truth[w] = True
            all_timestamps[w] = txs_ts.get(w, [])
            all_amounts[w] = txs_amt.get(w, [])
            all_first_seen[w] = first_seen_map.get(w, 0)
        print(f"  Sybil cluster {cid}: {n} wallets (funder: {funder[:14]}...)")

    # =========================================================
    # HONEST WALLETS
    # =========================================================
    num_honest = 300
    total_honest = 0
    for i in range(num_honest):
        addr, tx_list, txs_ts, txs_amt, first_seen_map = generate_honest_wallet(
            i,
            num_funders=random.randint(1, 4),
            num_counterparties=random.randint(5, 20),
            age_days_range=(90, 900),
        )
        ground_truth[addr] = False
        all_timestamps[addr] = txs_ts.get(addr, [])
        all_amounts[addr] = txs_amt.get(addr, [])
        all_first_seen[addr] = first_seen_map.get(addr, 0)
        all_transactions.extend(tx_list)
        total_honest += 1

    print(f"\n  Honest wallets: {total_honest}")
    print(f"  Sybil wallets:  {total_sybil_wallets}")
    print(f"  Total wallets:  {len(ground_truth)}")

    # =========================================================
    # ADDITIONAL TRANSACTIONS BETWEEN WALLETS (for graph edges)
    # =========================================================
    # Add inter-wallet transfers within Sybil clusters (linear chains)
    extra_txs = 0
    for cid, n, fseed, bt in sybil_configs:
        wallets = [pseudo_address(f"sybil_cluster_{cid}_wallet_{i}") for i in range(n)]
        # Linear transfer chain: wallet0 -> wallet1 -> wallet2 -> ...
        for i in range(n - 1):
            tx_time = bt + 100000 + (i * 3600) + random.randint(0, 300)
            tx = {
                "hash": pseudo_address(f"chain_tx_{cid}_{i}"),
                "from": wallets[i],
                "to": wallets[i + 1],
                "value": random.uniform(0.01, 0.1),
                "block": tx_time // 12,
                "timestamp": tx_time,
            }
            all_transactions.append(tx)
            all_timestamps.setdefault(wallets[i], []).append(tx_time)
            all_timestamps.setdefault(wallets[i + 1], []).append(tx_time)
            all_amounts.setdefault(wallets[i], []).append(tx.get("value", 0))
            all_amounts.setdefault(wallets[i + 1], []).append(tx.get("value", 0))
            extra_txs += 1

    # Add some inter-wallet transfers for honest wallets (organic)
    honest_addresses = [a for a, is_syb in ground_truth.items() if not is_syb]
    for _ in range(200):
        a = random.choice(honest_addresses)
        b = random.choice(honest_addresses)
        if a == b:
            continue
        tx_time = random.randint(1700000000, 1730000000)
        tx = {
            "hash": pseudo_address(f"honest_inter_{a[-8:]}_{b[-8:]}"),
            "from": a,
            "to": b,
            "value": random.uniform(0.001, 0.5),
            "block": tx_time // 12,
            "timestamp": tx_time,
        }
        all_transactions.append(tx)
        all_timestamps.setdefault(a, []).append(tx_time)
        all_timestamps.setdefault(b, []).append(tx_time)
        all_amounts.setdefault(a, []).append(tx.get("value", 0))
        all_amounts.setdefault(b, []).append(tx.get("value", 0))

    print(f"  Extra transactions: {extra_txs + 200}")

    # =========================================================
    # BUILD FUNDING SOURCE MAP
    # =========================================================
    funding_sources: Dict[str, List[str]] = defaultdict(list)
    for tx in all_transactions:
        if tx.get("from") and tx.get("to"):
            # Track who funded whom
            funding_sources[tx["from"]].append(tx["to"])

    # =========================================================
    # BUILD GRAPH
    # =========================================================
    G = nx.Graph()
    for tx in all_transactions:
        if tx.get("from") and tx.get("to"):
            f = tx["from"]
            t = tx["to"]
            val = G.get_edge_data(f, t, {}).get("value", 0)
            cnt = G.get_edge_data(f, t, {}).get("tx_count", 0)
            G.add_edge(f, t, value=val + tx["value"], tx_count=cnt + 1)

    DG = nx.DiGraph()
    for tx in all_transactions:
        if tx.get("from") and tx.get("to"):
            f = tx["from"]
            t = tx["to"]
            val = DG.get_edge_data(f, t, {}).get("value", 0)
            cnt = DG.get_edge_data(f, t, {}).get("tx_count", 0)
            DG.add_edge(f, t, value=val + tx["value"], tx_count=cnt + 1)

    print(f"\n  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # =========================================================
    # EXPORT
    # =========================================================
    # Save ground truth
    with open(f"{OUTPUT_DIR}/ground_truth.json", "w") as f:
        json.dump({
            "wallets": {addr: {"is_sybil": is_syb} for addr, is_syb in ground_truth.items()},
            "total_wallets": len(ground_truth),
            "sybil_wallets": total_sybil_wallets,
            "honest_wallets": total_honest,
        }, f, indent=2)

    # Save transactions
    with open(f"{OUTPUT_DIR}/transactions.json", "w") as f:
        json.dump(all_transactions, f, indent=2)

    # Save timestamps, amounts, first_seen
    with open(f"{OUTPUT_DIR}/timestamps.json", "w") as f:
        json.dump({k: v for k, v in all_timestamps.items() if k in ground_truth}, f, indent=2)
    with open(f"{OUTPUT_DIR}/amounts.json", "w") as f:
        json.dump({k: v for k, v in all_amounts.items() if k in ground_truth}, f, indent=2)
    with open(f"{OUTPUT_DIR}/first_seen.json", "w") as f:
        json.dump(all_first_seen, f, indent=2)

    # Save funding sources
    with open(f"{OUTPUT_DIR}/funding_sources.json", "w") as f:
        json.dump(dict(funding_sources), f, indent=2)

    # Save graph
    with open(f"{OUTPUT_DIR}/undirected_graph.gpickle", "wb") as f:
        pickle.dump(G, f)
    with open(f"{OUTPUT_DIR}/directed_graph.gpickle", "wb") as f:
        pickle.dump(DG, f)

    # Save wallet list
    all_wallets = list(ground_truth.keys())
    with open(f"{OUTPUT_DIR}/wallets.json", "w") as f:
        json.dump(all_wallets, f, indent=2)

    print(f"\n  Data exported to {OUTPUT_DIR}/")
    print(f"\n=== Generation Complete ===")
    print(f"  Sybil rate: {total_sybil_wallets / len(ground_truth) * 100:.1f}%")

    # Return paths for downstream consumption
    return {
        "graph_path": f"{OUTPUT_DIR}/undirected_graph.gpickle",
        "digraph_path": f"{OUTPUT_DIR}/directed_graph.gpickle",
        "wallets_path": f"{OUTPUT_DIR}/wallets.json",
        "funding_sources_path": f"{OUTPUT_DIR}/funding_sources.json",
        "timestamps_path": f"{OUTPUT_DIR}/timestamps.json",
        "amounts_path": f"{OUTPUT_DIR}/amounts.json",
        "first_seen_path": f"{OUTPUT_DIR}/first_seen.json",
        "ground_truth_path": f"{OUTPUT_DIR}/ground_truth.json",
    }


if __name__ == "__main__":
    main()
