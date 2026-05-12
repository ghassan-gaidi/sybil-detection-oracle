# Methodology — Sybil Detection Oracle

## Overview

The Sybil Detection Oracle identifies coordinated Sybil wallets in blockchain ecosystems using a multi-stage pipeline: graph construction → feature engineering → ML clustering → score computation → on-chain publishing. This document details the technical approach.

---

## 1. Graph Construction Methodology

### 1.1 Data Sources

| Source | Type | Coverage |
|--------|------|----------|
| Ethereum RPC (eth_getLogs, eth_getBlockByNumber) | Native ETH transfers | Full history via archive nodes |
| Block Explorer APIs (Etherscan, Arbiscan, Optimistic Etherscan) | Historical tx lists | Last 10K txs per wallet (free tier) |
| The Graph / Subgraphs | ERC-20 transfers, protocol-specific events | Custom subgraph deployments |
| Dune Analytics | Aggregated data exports | Pre-computed datasets |

### 1.2 Graph Types

**Directed Transaction Graph (DiGraph)**
- Nodes = wallet addresses
- Directed edges = value transfer (A → B means A sent funds to B)
- Edge attributes: value, timestamp, tx hash, block number
- Used for: funding source tracing, transfer chain detection

**Undirected Funding Graph (Graph)**
- Nodes = wallet addresses
- Undirected edges = wallets connected if they share a common funding source
- Edge attributes: shared_funders count
- Used for: clustering input

**Interaction Graph (Graph)**
- Nodes = wallet addresses
- Undirected edges = wallets interacted with the same protocol contract
- Edge attributes: interaction_count, first_interaction, last_interaction
- Used for: behavioral similarity analysis

### 1.3 Common Funding Source Detection

The most reliable Sybil signal: multiple wallets funded by the same address.

**Algorithm:**
1. For each wallet, collect all addresses that sent it native ETH or ERC-20 tokens
2. Group wallets by their set of funders
3. Flag wallet groups sharing ≥1 funder
4. Time-window filtering: funder must have sent to all wallets within a configurable window (default: 7 days)

**False positive mitigation:**
- Exchange deposit addresses that batch-distribute are excluded via allowlist
- Smart contract funders are analyzed separately (different Sybil patterns)
- Minimum funder-to-wallet value threshold prevents dusting attacks from triggering false flags

### 1.4 Token Transfer Chain Detection (Farm-to-Dump)

Sybil operators typically:
1. Fund wallets from a central source
2. Distribute to many wallets
3. Each wallet performs minimal interactions
4. Accumulated tokens flow back to a consolidation address
5. Consolidation address dumps on a DEX/CEX

**Algorithm:**
```
for each wallet in graph:
    follow the highest-value outgoing edge
    if path length >= 3:
        mark as transfer chain
        check if terminal wallet is an exchange deposit
```

---

## 2. Feature Engineering for Sybil Detection

### 2.1 Feature Vector Dimensions

Each wallet is represented as a 9-dimensional feature vector:

| # | Feature | Description | Sybil Signal |
|---|---------|-------------|--------------|
| 1 | `degree_centrality` | Normalized number of unique counterparties | Low degree = isolated sybils |
| 2 | `clustering_coefficient` | Local transitivity (how connected are neighbors) | High = tightly coordinated |
| 3 | `avg_neighbor_degree` | Mean degree of wallet's neighbors | Low = sybils connected to sybils |
| 4 | `eccentricity` | Maximum distance to any other wallet | Low = tightly clustered |
| 5 | `transaction_count` | Total number of outgoing + incoming txs | Low = minimal interaction |
| 6 | `total_value` | Sum of all transacted value | Uniform = bot-like |
| 7 | `unique_counterparties` | Distinct wallets interacted with | Low = isolated behavior |
| 8 | `timing_entropy` | Shannon entropy of transaction timestamps | Low = periodic/bot behavior |
| 9 | `amount_entropy` | Shannon entropy of transaction amounts | Low = uniform amounts |

### 2.2 Timing Correlation Features

Extracted from raw timestamp data:
- **Block distance**: Mean block distance between wallets in the same cluster
- **Co-occurrence**: Fraction of blocks where both wallets transacted
- **Periodicity**: FFT-based period detection in transaction sequences

### 2.3 Amount Correlation Features

- **Value similarity**: Pairwise Pearson correlation of transaction amounts
- **Round number ratio**: Fraction of transactions with round amounts (e.g., 0.1 ETH, 1.0 ETH)
- **Dust detection**: Presence of many sub-$0.01 transactions (gas-only wallets)

---

## 3. ML Model Selection Rationale

### 3.1 Primary: DBSCAN (Density-Based Spatial Clustering)

**Why DBSCAN?**
- **No pre-defined cluster count**: Sybil clusters can be any size (3 to 10,000+)
- **Noise handling**: Genuine wallets are naturally classified as noise (-1 label)
- **Arbitrary shapes**: Sybil clusters can form non-spherical shapes
- **Robust to outliers**: A few high-quality wallets in a sea of sybils don't distort results

**Hyperparameters:**
| Parameter | Default | Tuning Range | Description |
|-----------|---------|--------------|-------------|
| `eps` | 0.3 | 0.1–0.8 | Maximum distance between neighbors |
| `min_samples` | 5 | 3–15 | Minimum points to form dense region |
| `metric` | euclidean | cosine, manhattan | Distance metric |

**Tuning strategy:**
- K-distance graph elbow method for `eps`
- Grid search over `eps` × `min_samples` with silhouette score maximization
- Domain-specific validation against known Sybil clusters from past airdrops

### 3.2 Secondary: Hierarchical (Agglomerative) Clustering

Used when:
- Dataset is small (<10K wallets) and interpretability matters
- Client requests a specific number of clusters
- Validation/ground truth data is available for dendrogram analysis

**Linkage:** Ward (minimizes within-cluster variance)
**Distance:** Euclidean on standardized features

### 3.3 Cluster Confidence Scoring

Each cluster gets a confidence score [0, 1] based on:

| Factor | Weight | Metric |
|--------|--------|--------|
| Cluster density | 25% | Mean intra-cluster distance vs inter-cluster distance |
| Timing correlation | 25% | Mean pairwise timing Jaccard similarity |
| Amount correlation | 25% | Mean pairwise amount Pearson correlation |
| Interaction overlap | 25% | Mean pairwise Jaccard similarity of counterparty sets |

Confidence ≥ 0.7 → high-confidence Sybil cluster
Confidence ≥ 0.5 → medium-confidence (flagged for review)
Confidence < 0.5 → low-confidence (unlikely Sybil)

---

## 4. Scoring Algorithm

### 4.1 Sybil Score (0–100)

Formula combining five weighted factors:

```
SybilScore = Σ(w_i × f_i)
```

| Factor (f_i) | Weight (w_i) | Range | Description |
|-------------|-------------|-------|-------------|
| Cluster size | 0.20 | 0–100 | Larger clusters → higher score |
| Funding uniqueness | 0.20 | 0–100 | Single shared funder → high score |
| Behavior correlation | 0.25 | 0–100 | High timing/amount correlation → high score |
| Wallet age | 0.15 | 0–100 | Newer wallets → higher score |
| Transaction diversity | 0.20 | 0–100 | Low diversity → higher score |

### 4.2 Risk Classification

| Score Range | Label | Action |
|-------------|-------|--------|
| 0–24 | Minimal Risk | Genuine user — no action |
| 25–49 | Low Risk | Monitor — possible false positive |
| 50–74 | Medium Risk | Probable Sybil — flag for review |
| 75–100 | High Risk | Almost certain Sybil — exclude from distribution |

### 4.3 Score Breakdown (Explainability)

Each wallet's score includes a JSON breakdown:

```json
{
  "address": "0x...",
  "sybil_score": 82,
  "factors": {
    "cluster_size": 70,
    "funding_uniqueness": 90,
    "behavior_correlation": 85,
    "wallet_age": 75,
    "transaction_diversity": 80
  },
  "cluster_id": 3,
  "cluster_size": 42,
  "confidence": 0.91
}
```

---

## 5. Validation Approach

### 5.1 Ground Truth Dataset

Built from past airdrops where Sybil clusters were publicly identified:

- **Arbitrum Airdrop (March 2023)**: 1,496 identified Sybil wallets via Nansen + internal analysis
- **Optimism Airdrop #1 (June 2022)**: 17K Sybil wallets identified by Optimism team
- **ENS Airdrop (November 2021)**: Well-documented Sybil farming patterns
- **Synthetic datasets**: Generated using Sybil behavior simulators with known ground truth

### 5.2 Validation Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| Precision | > 0.90 | Fraction of flagged wallets that are truly Sybil |
| Recall | > 0.80 | Fraction of true Sybils correctly identified |
| F1 Score | > 0.85 | Harmonic mean of precision and recall |
| AUC-ROC | > 0.95 | Area under ROC curve |
| False Positive Rate | < 0.05 | Genuine wallets incorrectly flagged |

### 5.3 Cross-Validation Strategy

5-fold stratified cross-validation on ground truth datasets:
1. Reserve 20% of known Sybil clusters as holdout
2. Train clustering + scoring pipeline on 80%
3. Evaluate on held-out clusters
4. Repeat 5 times with different splits

### 5.4 Continuous Improvement

- **Feedback loop**: False positive reports from clients are ingested as corrective labels
- **Model retraining**: Automated retraining after every 10K new labeled wallets
- **A/B testing**: New detection strategies are evaluated against production baseline before deployment

---

## 6. Limitations & Known Edge Cases

1. **CEX interaction wallets**: Wallets that interact heavily with centralized exchanges may appear "Sybil-like" due to shared deposit addresses. Mitigated by exchange address allowlisting.
2. **Smart contract wallets**: Multi-sigs and smart contract wallets have different interaction patterns. Separate feature normalization is applied.
3. **Privacy-preserving mechanisms**: Tornado Cash / RAILGUN usage reduces graph connectivity. These wallets receive "insufficient data" scores (50 by default).
4. **Cross-chain Sybils**: Wallets operating across L2s with the same pattern. Future work: cross-chain identity resolution via Lens / ENS.
5. **Small clusters (< 3 wallets)**: Not detectable by cluster-based methods. Additional pattern-of-life analysis applied.

---

## References

1. [Ethereum Transaction Graph Analysis for Sybil Detection — arXiv:2108.13472](https://arxiv.org/abs/2108.13472)
2. [DBSCAN Revisited, Revisited — ACM Transactions on Database Systems](https://dl.acm.org/doi/10.1145/3068334)
3. [Optimism's Sybil Detection Methodology](https://optimism.mirror.xyz/)
4. [Arbitrum Airdrop Sybil Analysis — Nansen](https://www.nansen.ai/)
