# Sybil Analysis Report

**Prepared for:** [Client Name]
**Date:** [Report Date]
**Analysis ID:** [UUID]
**Classification:** Confidential

---

## 1. Executive Summary

This report presents the results of a Sybil analysis of **[X]** wallet addresses submitted by **[Client Name]** for the **[Protocol Name]** distribution. The analysis was performed using the Sybil Detection Oracle pipeline, which constructs transaction graphs, applies ML clustering (DBSCAN), and assigns Sybil scores (0–100) to each wallet.

**Key Findings**

| Metric | Value |
|--------|-------|
| Total wallets analyzed | [X] |
| High-confidence Sybil wallets (score 75–100) | [X] ([Y]%) |
| Medium-confidence Sybil wallets (score 50–74) | [X] ([Y]%) |
| Low-confidence / genuine wallets (score < 50) | [X] ([Y]%) |
| Total clusters detected | [X] |
| Largest cluster size | [X] wallets |
| Estimated value at risk | $[X] |

**Recommendation:** [Brief recommendation, e.g., "Exclude the 847 high-confidence Sybil wallets from the distribution, saving approximately $340K in token value."]

---

## 2. Methodology

The analysis uses a four-stage pipeline:

### Stage 1: Data Collection
- Wallet list provided by client: [X] addresses
- Transaction histories fetched from: [Chain] RPC / Block Explorer API
- Time range: [Start Block / Date] → [End Block / Date]
- Total transactions analyzed: [X]

### Stage 2: Graph Construction
- Directed transaction graph built with [X] nodes and [X] edges
- Undirected funding graph built linking wallets by shared funders
- [X] common funding sources identified (funding ≥ 2 wallets)
- [X] token transfer chains detected (farm-to-dump patterns)

### Stage 3: ML Clustering
- Algorithm: DBSCAN (eps=[X], min_samples=[X])
- Feature dimensions: 9 (degree centrality, clustering coefficient, avg_neighbor_degree, eccentricity, tx_count, total_value, unique_counterparties, timing_entropy, amount_entropy)
- Clusters detected: [X]
- Silhouette score: [X]
- Noise wallets (unclustered): [X]

### Stage 4: Scoring
- Sybil score = weighted combination of 5 factors
- Confidence threshold for Sybil labeling: ≥ 50 (medium) / ≥ 75 (high)
- Scoring factors and weights:
  - Cluster size (20%)
  - Funding source uniqueness (20%)
  - Behavioral correlation (25%)
  - Wallet age (15%)
  - Transaction diversity (20%)

---

## 3. Results Overview

### 3.1 Score Distribution

```
Score Range          Count     Percentage
─────────────────────────────────────────────
  High Risk (75–100)   [X]       [Y]%
  Medium Risk (50–74)  [X]       [Y]%
  Low Risk (25–49)     [X]       [Y]%
  Minimal Risk (0–24)  [X]       [Y]%
─────────────────────────────────────────────
  Total                [X]      100%
```

### 3.2 Top 10 Highest Scoring Wallets

| Rank | Address | Score | Cluster | Key Factor |
|------|---------|-------|---------|------------|
| 1 | 0x... | [X] | [ID] | Single funder, cluster of 42 |
| 2 | 0x... | [X] | [ID] | Single funder, cluster of 42 |
| 3 | 0x... | [X] | [ID] | Single funder, cluster of 42 |
| 4 | 0x... | [X] | [ID] | Timing correlation 0.95 |
| 5 | 0x... | [X] | [ID] | Timing correlation 0.95 |
| 6 | 0x... | [X] | [ID] | Wallet age 2 days |
| 7 | 0x... | [X] | [ID] | Wallet age 2 days |
| 8 | 0x... | [X] | [ID] | Zero diversity, single interaction |
| 9 | 0x... | [X] | [ID] | Zero diversity, single interaction |
| 10 | 0x... | [X] | [ID] | Cluster of 28, high amount correlation |

### 3.3 Largest Clusters

| Cluster ID | Size | Avg Score | Confidence | Top Funder |
|------------|------|-----------|------------|------------|
| [1] | [X] | [X] | [X] | 0x... |
| [2] | [X] | [X] | [X] | 0x... |
| [3] | [X] | [X] | [X] | 0x... |
| ... | ... | ... | ... | ... |

---

## 4. Detailed Cluster Analysis

### Cluster [ID]: [X] wallets, Score [X]

**Funding Source:** `0x...` funded all [X] wallets within a [X]-hour window.

**Behavior Pattern:**
- Each wallet performed exactly [X] interactions
- Interactions occurred within [X] blocks of each other
- All wallets used identical interaction sequences
- Funds consolidated to: `0x...` (exchange deposit address)

**Confidence:** [X] (high-confidence Sybil)

**Score Breakdown (for representative wallet `0x...`):**

| Factor | Score | Contribution |
|--------|-------|-------------|
| Cluster size | [X] | [X]% |
| Funding uniqueness | [X] | [X]% |
| Behavior correlation | [X] | [X]% |
| Wallet age | [X] | [X]% |
| Transaction diversity | [X] | [X]% |
| **Total** | **[X]** | **100%** |

---

## 5. Wallet Score Table

> *Full wallet scores are provided as a separate CSV/JSON attachment (`scores_full.csv` and `scores_full.json`).*

### Sample (first 20 wallets)

| Address | Score | Cluster | Age (days) | Txs | Counterparties | Funding Sources | Flagged |
|---------|-------|---------|-----------|-----|---------------|----------------|---------|
| 0x... | [X] | [ID] | [X] | [X] | [X] | [X] | Yes/No |
| 0x... | [X] | [ID] | [X] | [X] | [X] | [X] | Yes/No |
| ... | ... | ... | ... | ... | ... | ... | ... |

---

## 6. Recommendations

### Immediate Actions

1. **[Primary recommendation]**: Exclude the [X] high-confidence Sybil wallets from the distribution, saving approximately $[X] in token value.
2. **[Secondary recommendation]**: Flag the [X] medium-confidence wallets for manual review. Approximately [X]% may be false positives.
3. **[Tertiary recommendation]**: Implement on-chain score checking via `SybilOracle.sol` in your distribution contract to prevent Sybil wallets from claiming.

### Long-Term Recommendations

1. **Ongoing monitoring**: Subscribe to weekly Sybil monitoring to catch new clusters forming between snapshot and TGE.
2. **Sybil-resistant design**: Incorporate Sybil detection early in your points/activity program, not just at distribution.
3. **Cross-chain analysis**: If your protocol operates on multiple chains, consider a combined analysis to detect cross-chain Sybils.
4. **Periodic audits**: Quarterly deep-dive audits catch evolving Sybil strategies.

### Technical Integration

To integrate with `SybilOracle.sol`:

```solidity
// In your distribution contract:
ISybilOracle oracle = ISybilOracle(SYBIL_ORACLE_ADDRESS);

function claim(bytes32[] memory proof, address recipient) external {
    // Check Sybil score before allowing claim
    (uint8 score, bool isSybil,) = oracle.getScore(recipient);
    require(!isSybil, "Sybil wallet detected");
    
    // ... existing claim logic ...
}
```

---

## 7. Appendix

### A. Algorithm Configuration

| Parameter | Value |
|-----------|-------|
| DBSCAN eps | [X] |
| DBSCAN min_samples | [X] |
| Feature scaling | StandardScaler |
| Confidence threshold | 0.7 |
| Scoring factor weights | 0.20 / 0.20 / 0.25 / 0.15 / 0.20 |

### B. Data Sources

| Source | Usage |
|--------|-------|
| [RPC URL] | Native ETH transactions |
| [Explorer API] | Historical ERC-20 transfers |
| [Additional source] | [Description] |

### C. Glossary

| Term | Definition |
|------|------------|
| Sybil wallet | A wallet controlled by an operator as part of a coordinated group to extract disproportionate rewards |
| Funding source | An address that sent funds to establish a wallet |
| Cluster | A group of wallets identified as likely Sybil by ML algorithms |
| Sybil score | 0–100 score indicating likelihood of Sybil behavior (higher = more likely) |
| Confidence | 0–1 metric quantifying cluster detection reliability |
| Farm-to-dump | Pattern where Sybils accumulate tokens and consolidate them to a single selling wallet |

---

**Report generated by Sybil Detection Oracle**
https://github.com/ghassan-gaidi/sybil-detection-oracle

*Questions about this report? Contact sybil@nousresearch.com*
