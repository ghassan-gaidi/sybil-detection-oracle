"""
score_calculator.py — Sybil Score Computation

Takes cluster data from cluster_detector and assigns a Sybil score (0-100)
to each wallet. Scoring factors include:

- Cluster size and density
- Funding source uniqueness
- Behavioral correlation (timing, amounts)
- Wallet age
- Transaction diversity
- Interaction with known Sybil clusters

Output: JSON reports suitable for on-chain publishing.
"""

import logging
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime

import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class WalletScore:
    """Score breakdown for a single wallet."""
    address: str
    sybil_score: float  # 0-100
    cluster_id: int
    cluster_size: int
    funding_source_uniqueness: float
    behavior_correlation: float
    wallet_age_days: float
    transaction_diversity: float
    confidence: float
    is_sybil: bool
    factors: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreReport:
    """Complete scoring report."""
    generated_at: str
    total_wallets: int
    wallets_scored: List[WalletScore]
    clusters_detected: int
    sybil_wallets: int
    average_sybil_score: float
    score_distribution: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_wallets": self.total_wallets,
            "clusters_detected": self.clusters_detected,
            "sybil_wallets": self.sybil_wallets,
            "average_sybil_score": self.average_sybil_score,
            "score_distribution": self.score_distribution,
            "wallets_scored": [w.to_dict() for w in self.wallets_scored],
        }


class ScoreCalculator:
    """
    Computes Sybil scores (0-100) for wallets based on clustering
    and behavioral analysis.

    Scoring factors (weighted):
    - Cluster size (20%)
    - Funding source uniqueness (20%)
    - Behavior correlation (25%)
    - Wallet age (15%)
    - Transaction diversity (20%)
    """

    # Score thresholds
    HIGH_RISK_THRESHOLD = 75
    MEDIUM_RISK_THRESHOLD = 50
    LOW_RISK_THRESHOLD = 25

    # Factor weights (must sum to 1.0)
    WEIGHTS = {
        "cluster_size": 0.20,
        "funding_uniqueness": 0.20,
        "behavior_correlation": 0.25,
        "wallet_age": 0.15,
        "transaction_diversity": 0.20,
    }

    def __init__(self, current_timestamp: Optional[int] = None):
        """
        Initialize the score calculator.

        Args:
            current_timestamp: Unix timestamp for "now" (default: now)
        """
        self.current_time = current_timestamp or int(datetime.now().timestamp())

    def score_cluster_size(self, cluster_size: int, total_wallets: int) -> float:
        """
        Score based on cluster size.

        Larger clusters are more likely Sybil. Normalize by total dataset size.

        Args:
            cluster_size: Number of wallets in the cluster
            total_wallets: Total wallets in analysis

        Returns:
            Score component (0-100)
        """
        if total_wallets == 0:
            return 0.0

        ratio = cluster_size / total_wallets
        # Sigmoid-like scaling: clusters > 5% of dataset are suspicious
        if ratio > 0.1:
            return 90.0
        elif ratio > 0.05:
            return 75.0
        elif ratio > 0.02:
            return 60.0
        elif ratio > 0.01:
            return 45.0
        elif cluster_size >= 10:
            return 70.0
        elif cluster_size >= 5:
            return 55.0
        elif cluster_size >= 3:
            return 40.0
        else:
            return 20.0

    def score_funding_uniqueness(
        self,
        wallet_address: str,
        cluster_wallets: List[str],
        funding_sources: Dict[str, List[str]],
    ) -> float:
        """
        Score based on funding source uniqueness.

        Wallets sharing a single funding source get high Sybil score.

        Args:
            wallet_address: The wallet being scored
            cluster_wallets: All wallets in the same cluster
            funding_sources: Dict mapping funder -> list of recipients

        Returns:
            Score component (0-100)
        """
        # Find funders for this wallet and cluster
        cluster_funders = set()
        wallet_funders = set()

        for funder, recipients in funding_sources.items():
            for recipient in recipients:
                if recipient.lower() == wallet_address.lower():
                    wallet_funders.add(funder.lower())
                if recipient.lower() in [w.lower() for w in cluster_wallets]:
                    cluster_funders.add(funder.lower())

        if not wallet_funders:
            # Wallet may be an EOA with no inbound — low signal
            return 30.0

        # Check if multiple cluster wallets share the same funder
        shared_funders = wallet_funders & cluster_funders

        if len(shared_funders) == 1:
            # Single shared funder across cluster — strong Sybil signal
            return 85.0
        elif len(shared_funders) >= 2:
            return 60.0
        elif len(wallet_funders) == 1:
            return 50.0
        else:
            # Multiple unique funders — more organic
            return 20.0

    def score_behavior_correlation(
        self,
        wallet_address: str,
        cluster_wallets: List[str],
        tx_timestamps: Dict[str, List[int]],
        tx_amounts: Dict[str, List[float]],
        max_peers: int = 50,
    ) -> float:
        """
        Score based on behavioral correlation with cluster members.

        High timing/amount correlation indicates bot-like coordination.

        Args:
            wallet_address: The wallet being scored
            cluster_wallets: All wallets in the same cluster
            tx_timestamps: Dict mapping wallet -> list of timestamps
            tx_amounts: Dict mapping wallet -> list of amounts
            max_peers: Maximum peers to compare against (to avoid O(n^2))

        Returns:
            Score component (0-100)
        """
        if len(cluster_wallets) <= 1:
            return 0.0

        timing_corrs = []
        amount_corrs = []

        # Sample peers to avoid O(n^2) for large clusters
        peers = [p for p in cluster_wallets if p.lower() != wallet_address.lower()]
        if len(peers) > max_peers:
            import random
            random.seed(42)
            peers = random.sample(peers, max_peers)

        for peer in peers:
            # Timing correlation
            ts_self = set(tx_timestamps.get(wallet_address, []))
            ts_peer = set(tx_timestamps.get(peer, []))
            if ts_self and ts_peer:
                intersection = len(ts_self & ts_peer)
                union = len(ts_self | ts_peer)
                timing_corrs.append(intersection / union if union > 0 else 0.0)

            # Amount correlation
            amt_self = np.array(tx_amounts.get(wallet_address, []))
            amt_peer = np.array(tx_amounts.get(peer, []))
            if len(amt_self) >= 2 and len(amt_peer) >= 2:
                try:
                    min_len = min(len(amt_self), len(amt_peer))
                    corr = np.corrcoef(amt_self[:min_len], amt_peer[:min_len])
                    if not np.isnan(corr[0, 1]):
                        amount_corrs.append(abs(corr[0, 1]))
                except Exception:
                    pass

        avg_timing = np.mean(timing_corrs) if timing_corrs else 0.0
        avg_amount = np.mean(amount_corrs) if amount_corrs else 0.0

        # Combine timing and amount correlations
        combined = (avg_timing * 0.5 + avg_amount * 0.5) * 100.0
        return float(min(combined, 100.0))

    def score_wallet_age(
        self,
        wallet_address: str,
        graph: nx.Graph,
        first_seen_timestamps: Dict[str, int],
    ) -> float:
        """
        Score based on wallet age.

        New wallets (created shortly before the airdrop) are more suspicious.

        Args:
            wallet_address: The wallet being scored
            graph: NetworkX graph with node attributes
            first_seen_timestamps: Dict mapping wallet -> first tx timestamp

        Returns:
            Score component (0-100). Higher = newer = more Sybil-like.
        """
        # Try to get first_seen from node attributes
        first_seen = None
        if wallet_address in graph.nodes:
            first_seen = graph.nodes[wallet_address].get("first_seen")
        if first_seen is None:
            first_seen = first_seen_timestamps.get(wallet_address, 0)

        if first_seen == 0:
            # Unknown age — neutral score
            return 50.0

        age_seconds = self.current_time - first_seen
        age_days = age_seconds / (24 * 3600)

        if age_days < 7:
            return 95.0  # Less than a week old — extremely suspicious
        elif age_days < 30:
            return 85.0  # Less than a month
        elif age_days < 90:
            return 70.0
        elif age_days < 180:
            return 50.0
        elif age_days < 365:
            return 30.0
        else:
            return 15.0  # >1 year old — more likely genuine

    def score_transaction_diversity(
        self,
        wallet_address: str,
        graph: nx.Graph,
    ) -> float:
        """
        Score based on transaction diversity.

        Low diversity (only interacting with cluster members, only one token)
        is a Sybil signal.

        Args:
            wallet_address: The wallet being scored
            graph: NetworkX graph

        Returns:
            Score component (0-100). Higher = less diverse = more Sybil-like.
        """
        if wallet_address not in graph:
            return 50.0

        degree = graph.degree(wallet_address)
        if degree == 0:
            return 70.0  # Isolated wallet

        # Get unique counterparties
        neighbors = list(graph.neighbors(wallet_address))

        # Check if all interactions are with cluster members (inferred)
        # Simplified: low degree with high edge weight concentration
        total_value = 0.0
        for neighbor in neighbors:
            edge_data = graph.get_edge_data(wallet_address, neighbor) or {}
            total_value += edge_data.get("value", 0)

        if degree <= 2 and total_value > 0:
            return 75.0  # Very few counterparties
        elif degree <= 5:
            return 55.0
        elif degree <= 10:
            return 35.0
        else:
            return 15.0  # Diverse interactions

    def compute_score(
        self,
        wallet_address: str,
        cluster_id: int,
        cluster_wallets: List[str],
        total_wallets: int,
        graph: nx.Graph,
        funding_sources: Dict[str, List[str]],
        tx_timestamps: Dict[str, List[int]],
        tx_amounts: Dict[str, List[float]],
        first_seen_timestamps: Dict[str, int],
    ) -> WalletScore:
        """
        Compute the full Sybil score for a single wallet.

        Args:
            wallet_address: Wallet to score
            cluster_id: Cluster identifier
            cluster_wallets: All wallets in this cluster
            total_wallets: Total wallets in the dataset
            graph: NetworkX graph for diversity checks
            funding_sources: Funding source mapping
            tx_timestamps: Timestamp data per wallet
            tx_amounts: Amount data per wallet
            first_seen_timestamps: First activity timestamp per wallet

        Returns:
            WalletScore with breakdown
        """
        cluster_size = len(cluster_wallets)

        # Compute individual factor scores (0-100)
        size_score = self.score_cluster_size(cluster_size, total_wallets)
        funding_score = self.score_funding_uniqueness(
            wallet_address, cluster_wallets, funding_sources
        )
        behavior_score = self.score_behavior_correlation(
            wallet_address, cluster_wallets, tx_timestamps, tx_amounts
        )
        age_score = self.score_wallet_age(wallet_address, graph, first_seen_timestamps)
        diversity_score = self.score_transaction_diversity(wallet_address, graph)

        factors = {
            "cluster_size": round(size_score, 2),
            "funding_uniqueness": round(funding_score, 2),
            "behavior_correlation": round(behavior_score, 2),
            "wallet_age": round(age_score, 2),
            "transaction_diversity": round(diversity_score, 2),
        }

        # Weighted combination
        sybil_score = (
            size_score * self.WEIGHTS["cluster_size"]
            + funding_score * self.WEIGHTS["funding_uniqueness"]
            + behavior_score * self.WEIGHTS["behavior_correlation"]
            + age_score * self.WEIGHTS["wallet_age"]
            + diversity_score * self.WEIGHTS["transaction_diversity"]
        )

        sybil_score = round(min(sybil_score, 100.0), 2)

        # Compute overall confidence
        confidence = round(
            min(
                0.5 + (sybil_score / 200) + (cluster_size / 100),
                0.99,
            ),
            4,
        )

        is_sybil = sybil_score >= self.MEDIUM_RISK_THRESHOLD

        # Wallet age in days for reporting
        first_seen = first_seen_timestamps.get(wallet_address, 0)
        age_days = 0.0
        if first_seen > 0:
            age_days = round((self.current_time - first_seen) / (24 * 3600), 1)

        return WalletScore(
            address=wallet_address,
            sybil_score=sybil_score,
            cluster_id=cluster_id,
            cluster_size=cluster_size,
            funding_source_uniqueness=round(funding_score, 2),
            behavior_correlation=round(behavior_score, 2),
            wallet_age_days=age_days,
            transaction_diversity=round(diversity_score, 2),
            confidence=confidence,
            is_sybil=is_sybil,
            factors=factors,
        )

    def generate_report(
        self,
        graph: nx.Graph,
        clusters: List[Dict[str, Any]],
        funding_sources: Dict[str, List[str]],
        tx_timestamps: Dict[str, List[int]] = None,
        tx_amounts: Dict[str, List[float]] = None,
        first_seen_timestamps: Dict[str, int] = None,
    ) -> ScoreReport:
        """
        Generate a complete scoring report from cluster data.

        Args:
            graph: NetworkX graph
            clusters: List of cluster dicts (from ClusteringOutput)
            funding_sources: Funding source mapping
            tx_timestamps: Optional timestamp data
            tx_amounts: Optional amount data
            first_seen_timestamps: Optional first-seen data

        Returns:
            ScoreReport with all wallet scores
        """
        if tx_timestamps is None:
            tx_timestamps = {}
        if tx_amounts is None:
            tx_amounts = {}
        if first_seen_timestamps is None:
            first_seen_timestamps = {}

        total_wallets = graph.number_of_nodes()
        all_scores: List[WalletScore] = []
        scored_addresses = set()

        for cluster in clusters:
            cluster_id = cluster.get("cluster_id", -1)
            wallets = cluster.get("wallet_addresses", [])

            for wallet in wallets:
                score = self.compute_score(
                    wallet_address=wallet,
                    cluster_id=cluster_id,
                    cluster_wallets=wallets,
                    total_wallets=total_wallets,
                    graph=graph,
                    funding_sources=funding_sources,
                    tx_timestamps=tx_timestamps,
                    tx_amounts=tx_amounts,
                    first_seen_timestamps=first_seen_timestamps,
                )
                all_scores.append(score)
                scored_addresses.add(wallet.lower())

        # Score noise wallets (not in any cluster — low score by default)
        for node in graph.nodes():
            if node.lower() not in scored_addresses:
                score = WalletScore(
                    address=node,
                    sybil_score=10.0,
                    cluster_id=-1,
                    cluster_size=0,
                    funding_source_uniqueness=10.0,
                    behavior_correlation=0.0,
                    wallet_age_days=0.0,
                    transaction_diversity=20.0,
                    confidence=0.8,
                    is_sybil=False,
                    factors={"default": 10.0},
                )
                all_scores.append(score)

        # Sort by score descending (highest risk first)
        all_scores.sort(key=lambda s: s.sybil_score, reverse=True)

        sybil_wallets = [s for s in all_scores if s.is_sybil]
        avg_score = np.mean([s.sybil_score for s in all_scores]) if all_scores else 0.0

        # Score distribution buckets
        distribution = {
            "high_risk_75_100": len([s for s in all_scores if s.sybil_score >= 75]),
            "medium_risk_50_74": len([s for s in all_scores if 50 <= s.sybil_score < 75]),
            "low_risk_25_49": len([s for s in all_scores if 25 <= s.sybil_score < 50]),
            "minimal_risk_0_24": len([s for s in all_scores if s.sybil_score < 25]),
        }

        return ScoreReport(
            generated_at=datetime.utcnow().isoformat() + "Z",
            total_wallets=total_wallets,
            wallets_scored=all_scores,
            clusters_detected=len(clusters),
            sybil_wallets=len(sybil_wallets),
            average_sybil_score=round(float(avg_score), 2),
            score_distribution=distribution,
        )

    def export_report(
        self,
        report: ScoreReport,
        filepath: str = "reports/output/scores.json",
    ) -> str:
        """
        Export the score report to JSON.

        Args:
            report: ScoreReport to export
            filepath: Output file path

        Returns:
            Path to the exported file
        """
        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"Exported score report to {filepath}")
        return filepath

    def export_onchain_payload(
        self,
        report: ScoreReport,
        filepath: str = "reports/output/onchain_payload.json",
    ) -> str:
        """
        Export a minimal payload suitable for on-chain submission to SybilOracle.

        Args:
            report: ScoreReport
            filepath: Output path

        Returns:
            Path to exported file
        """
        # Only include wallets with score >= threshold
        onchain_wallets = []
        for ws in report.wallets_scored:
            if ws.sybil_score >= self.MEDIUM_RISK_THRESHOLD:
                onchain_wallets.append({
                    "address": ws.address,
                    "score": int(round(ws.sybil_score)),
                    "cluster_id": ws.cluster_id,
                })

        # Create Merkle-like structure for efficient on-chain verification
        # (simplified — real implementation uses Merkle tree)
        payload = {
            "contract": "SybilOracle",
            "timestamp": report.generated_at,
            "total_entries": len(onchain_wallets),
            "wallets": onchain_wallets,
            "merkle_root": hashlib.sha256(
                json.dumps(onchain_wallets, sort_keys=True).encode()
            ).hexdigest(),
        }

        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Exported on-chain payload to {filepath}")
        return filepath


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo
    G = nx.Graph()
    sybil_wallets = [f"0xsybil_{i:04d}" for i in range(10)]
    honest_wallets = [f"0xhonest_{i:04d}" for i in range(5)]

    for i, s in enumerate(sybil_wallets):
        for j, t in enumerate(sybil_wallets):
            if i < j:
                G.add_edge(s, t, value=1.0, tx_count=1)

    for w in honest_wallets:
        G.add_edge(w, f"0xcounterparty_{w[-4:]}", value=0.5, tx_count=2)

    clusters = [
        {
            "cluster_id": 1,
            "wallet_addresses": sybil_wallets,
        }
    ]

    funding_sources = {"0xfunder": sybil_wallets}
    tx_timestamps = {w: [1000000, 1000001, 1000002] for w in sybil_wallets}
    tx_amounts = {w: [0.1, 0.1, 0.1] for w in sybil_wallets}
    first_seen = {w: 999900 for w in sybil_wallets}

    calculator = ScoreCalculator(current_timestamp=2000000)
    report = calculator.generate_report(
        G, clusters, funding_sources,
        tx_timestamps=tx_timestamps,
        tx_amounts=tx_amounts,
        first_seen_timestamps=first_seen,
    )

    print(f"Total wallets scored: {report.total_wallets}")
    print(f"Sybil wallets detected: {report.sybil_wallets}")
    print(f"Average Sybil score: {report.average_sybil_score}")
    print(f"Score distribution: {report.score_distribution}")
    print("\nTop 3 highest scores:")
    for ws in report.wallets_scored[:3]:
        print(f"  {ws.address}: score={ws.sybil_score}, cluster={ws.cluster_id}")
