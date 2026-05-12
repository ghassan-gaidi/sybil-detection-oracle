"""
cluster_detector.py — ML Clustering for Sybil Detection

Takes graph data from graph_builder and applies clustering algorithms
(DBSCAN, hierarchical) to identify coordinated Sybil wallet clusters.

Feature vectors include:
- Timing correlation between wallet activities
- Amount correlation across transactions
- Interaction overlap (shared counterparties)
- Graph structural features (centrality, clustering coefficient)

Output: Identified clusters with confidence metrics.
"""

import logging
import json
import warnings
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

import networkx as nx
import numpy as np
from sklearn.cluster import DBSCAN, AgglomerativeClustering
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors

logger = logging.getLogger(__name__)


@dataclass
class ClusterResult:
    """Represents a detected Sybil cluster."""
    cluster_id: int
    wallet_addresses: List[str]
    size: int
    confidence: float
    avg_timing_correlation: float
    avg_amount_correlation: float
    shared_funders: int
    is_sybil: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClusteringOutput:
    """Complete clustering results."""
    clusters: List[ClusterResult]
    noise_wallets: List[str]
    total_wallets_analyzed: int
    algorithm_used: str
    silhouette_score: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clusters": [c.to_dict() for c in self.clusters],
            "noise_wallets": self.noise_wallets,
            "total_wallets_analyzed": self.total_wallets_analyzed,
            "algorithm_used": self.algorithm_used,
            "silhouette_score": self.silhouette_score,
        }


class ClusterDetector:
    """
    ML-based cluster detector for Sybil wallet identification.

    Supports DBSCAN and hierarchical (agglomerative) clustering.
    Computes feature vectors from graph data and detects coordinated
    clusters with confidence scoring.
    """

    def __init__(
        self,
        eps: float = 0.3,
        min_samples: int = 5,
        confidence_threshold: float = 0.7,
        random_state: int = 42,
    ):
        """
        Initialize the cluster detector.

        Args:
            eps: DBSCAN epsilon parameter (max distance between neighbors)
            min_samples: DBSCAN min_samples parameter
            confidence_threshold: Minimum confidence to label as Sybil
            random_state: Random seed for reproducibility
        """
        self.eps = eps
        self.min_samples = min_samples
        self.confidence_threshold = confidence_threshold
        self.random_state = random_state
        self.scaler = StandardScaler()

    def extract_features(
        self,
        graph: nx.Graph,
        wallet_subset: Optional[List[str]] = None,
    ) -> Tuple[np.ndarray, List[str], Dict[str, Any]]:
        """
        Extract feature vectors for each wallet in the graph.

        Feature dimensions:
        1.  Degree centrality (normalized degree)
        2.  Clustering coefficient (local transitivity)
        3.  Average neighbor degree
        4.  Eccentricity / farness
        5.  Transaction count (from edge weights)
        6.  Total value transacted
        7.  Unique counterparties
        8.  Timestamp entropy (if available)
        9.  Amount entropy (if available)

        Args:
            graph: NetworkX Graph (undirected)
            wallet_subset: Optional list of wallets to restrict analysis

        Returns:
            Tuple of (feature_matrix, wallet_addresses, feature_metadata)
        """
        nodes = list(graph.nodes())
        if wallet_subset:
            nodes = [n for n in nodes if n in wallet_subset]

        if not nodes:
            return np.array([]), [], {}

        features = []
        wallet_addresses = []
        feature_metadata = {
            "feature_names": [
                "degree_centrality",
                "clustering_coefficient",
                "avg_neighbor_degree",
                "eccentricity",
                "transaction_count",
                "total_value",
                "unique_counterparties",
                "timing_entropy",
                "amount_entropy",
            ]
        }

        for node in nodes:
            addr = str(node)
            wallet_addresses.append(addr)

            # Graph structural features
            dc = nx.degree_centrality(graph).get(node, 0)
            cc = nx.clustering(graph).get(node, 0)

            # Average neighbor degree
            neighbor_deg = 0
            neighbors = list(graph.neighbors(node))
            if neighbors:
                neighbor_deg = np.mean([graph.degree(n) for n in neighbors])

            # Eccentricity (approximate — use 2-hop eccentricity for speed)
            try:
                # Use 2-hop subgraph for eccentricity to avoid O(n^3)
                subgraph = nx.ego_graph(graph, node, radius=2)
                if subgraph.number_of_nodes() > 1:
                    ecc = nx.eccentricity(subgraph, node)
                else:
                    ecc = 0
            except (nx.NetworkXError, nx.NodeNotFound):
                ecc = 0

            # Edge-based features
            tx_count = 0
            total_value = 0.0
            for neighbor in neighbors:
                edge_data = graph.get_edge_data(node, neighbor) or {}
                tx_count += edge_data.get("tx_count", 1)
                total_value += edge_data.get("value", 0)

            unique_counterparties = len(neighbors)

            # Entropy features (placeholder — computed from timestamp data)
            timing_entropy = 0.0
            amount_entropy = 0.0

            features.append([
                dc,
                cc,
                neighbor_deg,
                ecc,
                tx_count,
                total_value,
                unique_counterparties,
                timing_entropy,
                amount_entropy,
            ])

        feature_matrix = np.array(features, dtype=np.float64)
        logger.info(
            f"Extracted features: {feature_matrix.shape[0]} wallets, "
            f"{feature_matrix.shape[1]} dimensions"
        )
        return feature_matrix, wallet_addresses, feature_metadata

    def compute_timing_correlation(
        self,
        wallet_a: str,
        wallet_b: str,
        tx_timestamps: Dict[str, List[int]],
    ) -> float:
        """
        Compute timing correlation between two wallets.

        High correlation suggests coordinated behavior (wallets acting
        in the same blocks or short time windows).

        Args:
            wallet_a: First wallet address
            wallet_b: Second wallet address
            tx_timestamps: Dict mapping wallet -> list of timestamps

        Returns:
            Correlation coefficient (0-1)
        """
        ts_a = set(tx_timestamps.get(wallet_a, []))
        ts_b = set(tx_timestamps.get(wallet_b, []))

        if not ts_a or not ts_b:
            return 0.0

        intersection = len(ts_a & ts_b)
        union = len(ts_a | ts_b)
        if union == 0:
            return 0.0
        return intersection / union

    def compute_amount_correlation(
        self,
        wallet_a: str,
        wallet_b: str,
        tx_amounts: Dict[str, List[float]],
    ) -> float:
        """
        Compute amount correlation between two wallets.

        Sybils often transact in identical or near-identical amounts.

        Args:
            wallet_a: First wallet address
            wallet_b: Second wallet address
            tx_amounts: Dict mapping wallet -> list of transaction amounts

        Returns:
            Correlation coefficient (0-1)
        """
        amounts_a = np.array(tx_amounts.get(wallet_a, []))
        amounts_b = np.array(tx_amounts.get(wallet_b, []))

        if len(amounts_a) < 2 or len(amounts_b) < 2:
            return 0.0

        try:
            # Resample or align by size
            min_len = min(len(amounts_a), len(amounts_b))
            if min_len < 2:
                return 0.0
            corr = np.corrcoef(amounts_a[:min_len], amounts_b[:min_len])
            return float(abs(corr[0, 1])) if not np.isnan(corr[0, 1]) else 0.0
        except Exception:
            return 0.0

    def compute_interaction_overlap(
        self,
        wallet_a: str,
        wallet_b: str,
        graph: nx.Graph,
    ) -> float:
        """
        Compute interaction overlap (shared counterparties) between two wallets.

        High overlap is a strong Sybil signal.

        Args:
            wallet_a: First wallet address
            wallet_b: Second wallet address
            graph: NetworkX graph

        Returns:
            Jaccard similarity of neighbor sets
        """
        try:
            neighbors_a = set(graph.neighbors(wallet_a))
            neighbors_b = set(graph.neighbors(wallet_b))

            if not neighbors_a or not neighbors_b:
                return 0.0

            intersection = len(neighbors_a & neighbors_b)
            union = len(neighbors_a | neighbors_b)
            if union == 0:
                return 0.0
            return intersection / union
        except (nx.NetworkXError, Exception):
            return 0.0

    def run_dbscan(
        self,
        feature_matrix: np.ndarray,
        wallet_addresses: List[str],
        graph: nx.Graph,
        tx_timestamps: Dict[str, List[int]] = None,
        tx_amounts: Dict[str, List[float]] = None,
    ) -> ClusteringOutput:
        """
        Run DBSCAN clustering on feature matrix.

        Args:
            feature_matrix: N x D numpy array of features
            wallet_addresses: List of wallet addresses (length N)
            graph: NetworkX graph for correlation computations
            tx_timestamps: Optional dict for timing correlation
            tx_amounts: Optional dict for amount correlation

        Returns:
            ClusteringOutput with detected clusters
        """
        if tx_timestamps is None:
            tx_timestamps = {}
        if tx_amounts is None:
            tx_amounts = {}

        logger.info(f"Running DBSCAN with eps={self.eps}, min_samples={self.min_samples}")

        # Standardize features
        features_scaled = self.scaler.fit_transform(feature_matrix)

        # Run DBSCAN
        clusterer = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
            metric="euclidean",
            n_jobs=-1,
        )
        labels = clusterer.fit_predict(features_scaled)

        # Organize clusters
        cluster_map: Dict[int, List[str]] = defaultdict(list)
        for wallet_id, label in enumerate(labels):
            cluster_map[int(label)].append(wallet_addresses[wallet_id])

        # Compute silhouette score (if enough clusters)
        sil_score = None
        unique_labels = set(labels)
        n_clusters = len([l for l in unique_labels if l != -1])
        n_noise = list(labels).count(-1)

        if n_clusters > 1 and len(features_scaled) > n_clusters:
            try:
                # Filter noise for silhouette
                mask = labels != -1
                if np.sum(mask) > n_clusters:
                    sil_score = float(
                        silhouette_score(features_scaled[mask], labels[mask])
                    )
            except Exception as e:
                logger.warning(f"Silhouette computation failed: {e}")

        # Build cluster results
        clusters = []
        noise_wallets = cluster_map.get(-1, [])

        for label_id, wallets in cluster_map.items():
            if label_id == -1:
                continue

            cluster_size = len(wallets)

            # Compute confidence metrics
            confidence_factors = []

            # Factor 1: Cluster size penalty / reward
            if cluster_size >= 5:
                confidence_factors.append(0.8)
            elif cluster_size >= 3:
                confidence_factors.append(0.6)
            else:
                confidence_factors.append(0.3)

            # Factor 2: Timing correlation within cluster
            timing_corrs = []
            for i in range(min(len(wallets), 10)):
                for j in range(i + 1, min(len(wallets), 10)):
                    corr = self.compute_timing_correlation(
                        wallets[i], wallets[j], tx_timestamps
                    )
                    timing_corrs.append(corr)
            avg_timing = np.mean(timing_corrs) if timing_corrs else 0.0
            confidence_factors.append(avg_timing)

            # Factor 3: Amount correlation within cluster
            amount_corrs = []
            for i in range(min(len(wallets), 10)):
                for j in range(i + 1, min(len(wallets), 10)):
                    corr = self.compute_amount_correlation(
                        wallets[i], wallets[j], tx_amounts
                    )
                    amount_corrs.append(corr)
            avg_amount = np.mean(amount_corrs) if amount_corrs else 0.0
            confidence_factors.append(avg_amount)

            # Factor 4: Interaction overlap
            overlap_scores = []
            for i in range(min(len(wallets), 10)):
                for j in range(i + 1, min(len(wallets), 10)):
                    overlap = self.compute_interaction_overlap(
                        wallets[i], wallets[j], graph
                    )
                    overlap_scores.append(overlap)
            avg_overlap = np.mean(overlap_scores) if overlap_scores else 0.0
            confidence_factors.append(avg_overlap)

            # Combined confidence (weighted average)
            weights = [0.25, 0.25, 0.25, 0.25]
            confidence = float(np.average(confidence_factors, weights=weights))

            # Count shared funders (look for common predecessors in digraph)
            shared_funders = 0

            cluster = ClusterResult(
                cluster_id=label_id,
                wallet_addresses=wallets,
                size=cluster_size,
                confidence=round(confidence, 4),
                avg_timing_correlation=round(avg_timing, 4),
                avg_amount_correlation=round(avg_amount, 4),
                shared_funders=shared_funders,
                is_sybil=confidence >= self.confidence_threshold,
            )
            clusters.append(cluster)

        # Sort clusters by size descending
        clusters.sort(key=lambda c: c.size, reverse=True)

        output = ClusteringOutput(
            clusters=clusters,
            noise_wallets=noise_wallets,
            total_wallets_analyzed=len(wallet_addresses),
            algorithm_used="DBSCAN",
            silhouette_score=round(sil_score, 4) if sil_score is not None else None,
        )

        logger.info(
            f"DBSCAN complete: {len(clusters)} clusters, "
            f"{len(noise_wallets)} noise wallets"
        )
        return output

    def run_hierarchical(
        self,
        feature_matrix: np.ndarray,
        wallet_addresses: List[str],
        graph: nx.Graph,
        n_clusters: int = 10,
        tx_timestamps: Dict[str, List[int]] = None,
        tx_amounts: Dict[str, List[float]] = None,
    ) -> ClusteringOutput:
        """
        Run hierarchical (agglomerative) clustering.

        Useful for smaller datasets where we want a controlled number of clusters.

        Args:
            feature_matrix: N x D numpy array
            wallet_addresses: List of wallet addresses
            graph: NetworkX graph
            n_clusters: Target number of clusters
            tx_timestamps: Optional timestamp data
            tx_amounts: Optional amount data

        Returns:
            ClusteringOutput
        """
        if tx_timestamps is None:
            tx_timestamps = {}
        if tx_amounts is None:
            tx_amounts = {}

        logger.info(f"Running hierarchical clustering: {n_clusters} clusters")

        features_scaled = self.scaler.fit_transform(feature_matrix)

        clusterer = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric="euclidean",
            linkage="ward",
        )
        labels = clusterer.fit_predict(features_scaled)

        # Build results (similar to DBSCAN output format)
        cluster_map: Dict[int, List[str]] = defaultdict(list)
        for wallet_id, label in enumerate(labels):
            cluster_map[int(label)].append(wallet_addresses[wallet_id])

        sil_score = None
        if n_clusters > 1 and len(features_scaled) > n_clusters:
            try:
                sil_score = float(
                    silhouette_score(features_scaled, labels)
                )
            except Exception:
                pass

        clusters = []
        for label_id, wallets in cluster_map.items():
            cluster_size = len(wallets)
            # Simplified confidence for hierarchical
            confidence = min(0.5 + (cluster_size / 100), 0.95)

            cluster = ClusterResult(
                cluster_id=label_id,
                wallet_addresses=wallets,
                size=cluster_size,
                confidence=round(confidence, 4),
                avg_timing_correlation=0.0,
                avg_amount_correlation=0.0,
                shared_funders=0,
                is_sybil=confidence >= self.confidence_threshold,
            )
            clusters.append(cluster)

        clusters.sort(key=lambda c: c.size, reverse=True)

        return ClusteringOutput(
            clusters=clusters,
            noise_wallets=[],
            total_wallets_analyzed=len(wallet_addresses),
            algorithm_used=f"Hierarchical (n={n_clusters})",
            silhouette_score=round(sil_score, 4) if sil_score is not None else None,
        )

    def detect(
        self,
        graph: nx.Graph,
        method: str = "dbscan",
        wallet_subset: Optional[List[str]] = None,
        **kwargs,
    ) -> ClusteringOutput:
        """
        High-level detection interface.

        Args:
            graph: NetworkX graph (undirected, from funding analysis)
            method: 'dbscan' or 'hierarchical'
            wallet_subset: Optional wallet filter
            **kwargs: Additional arguments to clustering methods

        Returns:
            ClusteringOutput with all detected clusters
        """
        feature_matrix, wallet_addresses, _ = self.extract_features(
            graph, wallet_subset
        )

        if feature_matrix.shape[0] == 0:
            logger.warning("No features extracted — returning empty result")
            return ClusteringOutput(
                clusters=[], noise_wallets=[], total_wallets_analyzed=0,
                algorithm_used=method, silhouette_score=None,
            )

        if method == "dbscan":
            return self.run_dbscan(feature_matrix, wallet_addresses, graph, **kwargs)
        elif method == "hierarchical":
            n_clusters = kwargs.pop("n_clusters", min(10, len(wallet_addresses) // 5))
            return self.run_hierarchical(
                feature_matrix, wallet_addresses, graph, n_clusters, **kwargs
            )
        else:
            raise ValueError(f"Unknown method: {method}. Use 'dbscan' or 'hierarchical'.")

    def export_clusters(
        self,
        output: ClusteringOutput,
        filepath: str = "data/clusters.json",
    ) -> None:
        """
        Export clustering results to JSON.

        Args:
            output: ClusteringOutput object
            filepath: Output JSON path
        """
        with open(filepath, "w") as f:
            json.dump(output.to_dict(), f, indent=2)
        logger.info(f"Exported clusters to {filepath}")

    def load_clusters(self, filepath: str) -> Dict[str, Any]:
        """
        Load clustering results from JSON.

        Args:
            filepath: Path to clusters JSON

        Returns:
            Dict with cluster data
        """
        with open(filepath) as f:
            data = json.load(f)
        logger.info(f"Loaded clusters from {filepath}")
        return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo: create a small synthetic graph
    G = nx.Graph()
    # Sybil cluster 1 — all funded by 0xfunder1
    sybil_1 = [f"0xsybil1_{i:04d}" for i in range(10)]
    # Sybil cluster 2 — all funded by 0xfunder2
    sybil_2 = [f"0xsybil2_{i:04d}" for i in range(7)]
    # Honest wallets
    honest = [f"0xhonest_{i:04d}" for i in range(5)]

    for i, s in enumerate(sybil_1):
        for j, t in enumerate(sybil_1):
            if i < j:
                G.add_edge(s, t, value=1.0, tx_count=1)

    for i, s in enumerate(sybil_2):
        for j, t in enumerate(sybil_2):
            if i < j:
                G.add_edge(s, t, value=1.0, tx_count=1)

    detector = ClusterDetector(eps=0.5, min_samples=3)
    result = detector.detect(G, method="dbscan")
    print(f"Found {len(result.clusters)} clusters")
    for c in result.clusters:
        print(f"  Cluster {c.cluster_id}: {c.size} wallets, confidence={c.confidence}, sybil={c.is_sybil}")
    print(f"Silhouette score: {result.silhouette_score}")
