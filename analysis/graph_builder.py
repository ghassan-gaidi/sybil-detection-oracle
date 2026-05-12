"""
graph_builder.py — Transaction Graph Construction

Builds directed and undirected transaction graphs from on-chain data.
Uses Web3.py to fetch wallet transaction histories, identifies common
funding sources, and tracks token transfer chains (farm-to-dump).

Output: NetworkX graph objects for downstream clustering.
"""

import logging
import json
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

import networkx as nx
from web3 import Web3
from web3.types import TxData, TxReceipt

logger = logging.getLogger(__name__)


class TransactionGraphBuilder:
    """
    Builds transaction graphs from on-chain data.

    Supports:
    - Directed transaction graphs (who sent to whom)
    - Common funding source detection (same deposit address)
    - Token transfer chain tracking (linear farm-to-dump patterns)
    - Multi-chain data ingestion
    """

    def __init__(
        self,
        rpc_url: str = "",
        web3_instance: Optional[Web3] = None,
    ):
        """
        Initialize the graph builder.

        Args:
            rpc_url: Ethereum RPC endpoint URL (used if web3_instance not provided)
            web3_instance: Existing Web3.py instance
        """
        if web3_instance:
            self.w3 = web3_instance
        elif rpc_url:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        else:
            self.w3 = None
            logger.warning("No Web3 connection provided. Using offline mode.")

        # Directed graph: edge (A -> B) means A sent funds to B
        self.digraph: nx.DiGraph = nx.DiGraph()

        # Undirected graph: used for clustering (nodes connected if they share a funder)
        self.undirected: nx.Graph = nx.Graph()

        # Funding source mapping: wallet -> set of funder addresses
        self.funding_sources: Dict[str, set] = defaultdict(set)

        # Token transfer chains
        self.transfer_chains: List[List[str]] = []

    def fetch_transactions(
        self,
        address: str,
        from_block: int = 0,
        to_block: int = "latest",
        max_tx: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch native ETH transactions for a given address.

        Uses eth_getLogs or Etherscan-style iteration. This is a simplified
        implementation; in production use archive nodes or block explorer APIs.

        Args:
            address: Wallet address to query
            from_block: Starting block number
            to_block: Ending block number ('latest' or int)
            max_tx: Maximum transactions to fetch

        Returns:
            List of transaction dicts with 'from', 'to', 'value', 'hash', 'block'
        """
        if not self.w3:
            logger.warning("Web3 not connected; returning empty tx list.")
            return []

        address = Web3.to_checksum_address(address)
        txs: List[Dict[str, Any]] = []

        try:
            # Use get_logs for transfer events if ERC-20, else scan blocks
            # For native ETH: iterate recent blocks and filter
            latest_block = self.w3.eth.block_number
            if to_block == "latest":
                to_block = latest_block

            # Simple block range scan (use getLogs for production)
            block_range = min(to_block - from_block, 100)  # limit for demo
            for offset in range(block_range):
                block_num = to_block - offset
                block = self.w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.transactions:
                    if isinstance(tx, dict):
                        tx_from = tx.get("from", "").lower()
                        tx_to = tx.get("to", "").lower()
                        addr_lower = address.lower()
                        if tx_from == addr_lower or tx_to == addr_lower:
                            txs.append({
                                "hash": tx.get("hash", "").hex(),
                                "from": tx.get("from", ""),
                                "to": tx.get("to", ""),
                                "value": float(Web3.from_wei(tx.get("value", 0), "ether")),
                                "block": block_num,
                                "timestamp": block.get("timestamp", 0),
                            })
                            if len(txs) >= max_tx:
                                break
                if len(txs) >= max_tx:
                    break

        except Exception as e:
            logger.error(f"Error fetching transactions for {address}: {e}")

        logger.info(f"Fetched {len(txs)} transactions for {address}")
        return txs

    def add_transaction(self, tx: Dict[str, Any]) -> None:
        """
        Add a single transaction to the graph.

        Args:
            tx: Transaction dict with 'from', 'to', 'value', 'hash', 'block', 'timestamp'
        """
        sender = Web3.to_checksum_address(tx["from"]) if tx.get("from") else None
        receiver = Web3.to_checksum_address(tx["to"]) if tx.get("to") else None
        value = tx.get("value", 0)
        tx_hash = tx.get("hash", "")

        if not sender or not receiver:
            return

        # Add nodes
        self.digraph.add_node(sender, first_seen=tx.get("timestamp"), tx_count=0)
        self.digraph.add_node(receiver, first_seen=tx.get("timestamp"), tx_count=0)

        # Add directed edge
        edge_attrs = {
            "value": value,
            "hash": tx_hash,
            "block": tx.get("block", 0),
            "timestamp": tx.get("timestamp", 0),
        }
        if self.digraph.has_edge(sender, receiver):
            self.digraph[sender][receiver]["value"] += value
            self.digraph[sender][receiver]["tx_count"] = (
                self.digraph[sender][receiver].get("tx_count", 0) + 1
            )
        else:
            self.digraph.add_edge(sender, receiver, **edge_attrs, tx_count=1)

        # Track funding source
        self.funding_sources[receiver].add(sender)

    def build_from_transactions(
        self, transactions: List[Dict[str, Any]]
    ) -> nx.DiGraph:
        """
        Build a directed graph from a list of transactions.

        Args:
            transactions: List of transaction dicts

        Returns:
            NetworkX DiGraph
        """
        for tx in transactions:
            self.add_transaction(tx)
        logger.info(
            f"Built directed graph: {self.digraph.number_of_nodes()} nodes, "
            f"{self.digraph.number_of_edges()} edges"
        )
        return self.digraph

    def find_common_funding_sources(
        self, min_overlap: int = 2
    ) -> Dict[str, List[str]]:
        """
        Identify wallets that share funding sources.

        Wallets funded by the same address within a short time window
        are likely Sybils.

        Args:
            min_overlap: Minimum number of shared funders to flag

        Returns:
            Dict mapping funder address -> list of wallets it funded
        """
        funder_to_wallets: Dict[str, List[str]] = defaultdict(list)
        for wallet, funders in self.funding_sources.items():
            for funder in funders:
                funder_to_wallets[funder].append(wallet)

        # Filter to funders with enough wallets
        result = {
            funder: wallets
            for funder, wallets in funder_to_wallets.items()
            if len(wallets) >= min_overlap
        }
        logger.info(
            f"Found {len(result)} common funding sources "
            f"(min overlap={min_overlap})"
        )
        return result

    def build_undirected_funding_graph(self) -> nx.Graph:
        """
        Build an undirected graph where wallets are connected if they
        share a common funding source.

        Returns:
            NetworkX Graph
        """
        common = self.find_common_funding_sources(min_overlap=2)
        wallet_sets = list(common.values())

        for wallets in wallet_sets:
            for i in range(len(wallets)):
                for j in range(i + 1, len(wallets)):
                    w1 = Web3.to_checksum_address(wallets[i])
                    w2 = Web3.to_checksum_address(wallets[j])
                    edge_data = self.undirected.get_edge_data(w1, w2) or {}
                    self.undirected.add_edge(
                        w1, w2,
                        shared_funders=edge_data.get("shared_funders", 0) + 1,
                    )

        logger.info(
            f"Built undirected funding graph: {self.undirected.number_of_nodes()} "
            f"nodes, {self.undirected.number_of_edges()} edges"
        )
        return self.undirected

    def track_transfer_chains(
        self, token_address: Optional[str] = None
    ) -> List[List[str]]:
        """
        Identify token transfer chains (linear farm-to-dump patterns).

        Traces ERC-20 transfers from initial recipients through intermediate
        wallets to final exchange deposits.

        Args:
            token_address: Optional ERC-20 token address to filter

        Returns:
            List of transfer chains (each chain is a list of wallet addresses)
        """
        # Simple heuristic: follow high-value out-degree paths
        chains = []
        visited = set()

        for node in self.digraph.nodes():
            if node in visited:
                continue
            chain = []
            current = node
            depth = 0
            while current and depth < 20:
                chain.append(current)
                visited.add(current)
                successors = list(self.digraph.successors(current))
                if not successors:
                    break
                # Pick the successor with highest total received value
                current = max(
                    successors,
                    key=lambda n: self.digraph[current][n].get("value", 0),
                )
                depth += 1
            if len(chain) >= 3:
                chains.append(chain)

        self.transfer_chains = chains
        logger.info(f"Identified {len(chains)} transfer chains")
        return chains

    def get_graph_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the built graph.

        Returns:
            Dict with graph statistics
        """
        return {
            "directed_nodes": self.digraph.number_of_nodes(),
            "directed_edges": self.digraph.number_of_edges(),
            "undirected_nodes": self.undirected.number_of_nodes(),
            "undirected_edges": self.undirected.number_of_edges(),
            "funding_sources": len(self.funding_sources),
            "transfer_chains": len(self.transfer_chains),
        }

    def export_graph(self, filepath: str = "data/current_graph.gpickle") -> None:
        """
        Export the directed graph to a GPickle file.

        Args:
            filepath: Output file path
        """
        nx.write_gpickle(self.digraph, filepath)
        logger.info(f"Exported graph to {filepath}")

    def load_graph(self, filepath: str) -> nx.DiGraph:
        """
        Load a previously exported graph.

        Args:
            filepath: Path to GPickle file

        Returns:
            Loaded DiGraph
        """
        self.digraph = nx.read_gpickle(filepath)
        logger.info(
            f"Loaded graph from {filepath}: "
            f"{self.digraph.number_of_nodes()} nodes, "
            f"{self.digraph.number_of_edges()} edges"
        )
        return self.digraph


if __name__ == "__main__":
    # Demo / test run
    logging.basicConfig(level=logging.INFO)

    builder = TransactionGraphBuilder()
    sample_txs = [
        {"from": "0x1111...1111", "to": "0xaaaa...aaaa", "value": 1.0, "hash": "0xaa", "block": 100, "timestamp": 1000000},
        {"from": "0x1111...1111", "to": "0xbbbb...bbbb", "value": 1.0, "hash": "0xbb", "block": 101, "timestamp": 1000001},
        {"from": "0x1111...1111", "to": "0xcccc...cccc", "value": 1.0, "hash": "0xcc", "block": 102, "timestamp": 1000002},
        {"from": "0xaaaa...aaaa", "to": "0xdddd...dddd", "value": 10.0, "hash": "0xdd", "block": 200, "timestamp": 2000000},
        {"from": "0xbbbb...bbbb", "to": "0xdddd...dddd", "value": 10.0, "hash": "0xee", "block": 201, "timestamp": 2000001},
    ]

    builder.build_from_transactions(sample_txs)
    print("Graph summary:", json.dumps(builder.get_graph_summary(), indent=2))
    print("Common funding sources:", builder.find_common_funding_sources())
