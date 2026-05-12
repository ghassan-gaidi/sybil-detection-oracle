# Sybil Detection Oracle

**On-chain Sybil detection oracle using graph analysis and ML clustering to identify coordinated Sybil farmers in airdrop distributions and governance systems.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Solidity ^0.8.20](https://img.shields.io/badge/solidity-%5E0.8.20-lightgrey)](https://docs.soliditylang.org/)

---

## Problem

Airdrop farming and Sybil attacks cost protocols **tens of millions of dollars** per distribution. Coordinated actors control hundreds of wallets, all funded from a single source, executing identical interaction patterns to extract disproportionate rewards. Traditional KYC and CAPTCHA solutions fail in permissionless environments.

## Solution

The Sybil Detection Oracle ingests on-chain transaction data, constructs interaction graphs, applies ML clustering (DBSCAN, hierarchical), and produces a **Sybil score (0–100)** for every wallet in a dataset. Scores are published on-chain via a Solidity oracle contract, making them directly consumable by protocol distribution contracts.

## Architecture

```
┌──────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│     On-Chain Data     │─────▶│   Graph Builder      │─────▶│  Cluster Detector    │
│  (RPC / Explorer APIs) │      │  (NetworkX graphs)   │      │  (DBSCAN / HDBSCAN)  │
└──────────────────────┘      └─────────────────────┘      └─────────────────────┘
                                                                    │
                                                                    ▼
┌──────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│  Protocol Contracts   │◀────│  SybilOracle.sol     │◀────│  Score Calculator    │
│  (query scores)       │      │  (on-chain registry)  │      │  (0–100 scoring)    │
└──────────────────────┘      └─────────────────────┘      └─────────────────────┘
         │                           ▲
         ▼                           │
┌──────────────────────┐      ┌─────────────────────┐
│  PaymentGate.sol      │──────│  Client Dashboard    │
│  (ETH/ERC20 payments) │      │  (reports, metrics)   │
└──────────────────────┘      └─────────────────────┘
```

## How It Works

1. **Data Ingestion** — Fetch wallet transaction histories from Ethereum RPCs and block explorer APIs.
2. **Graph Construction** — Build directed transaction graphs linking wallets by fund flows. Identify common funding sources (same deposit address) and token transfer chains (farm-to-dump).
3. **Feature Engineering** — Extract feature vectors per wallet: timing correlation, amount correlation, interaction overlap, wallet age, transaction diversity.
4. **ML Clustering** — Apply DBSCAN and hierarchical clustering to detect coordinated wallet groups. Confidence metrics quantify cluster reliability.
5. **Score Calculation** — Compute a Sybil score (0 = genuine, 100 = almost certainly Sybil) based on cluster size, funding source uniqueness, behavior correlation, wallet age, and transaction diversity.
6. **On-Chain Publishing** — Scores are written to the `SybilOracle.sol` contract, accessible by protocol distribution contracts.
7. **Report Delivery** — Comprehensive analysis reports delivered to clients.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/ghassan-gaidi/sybil-detection-oracle.git
cd sybil-detection-oracle

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your RPC endpoints and API keys

# Run a sample analysis
python analysis/graph_builder.py --target-wallet 0x742d35Cc6634C0532925a3b844Bc454e4438f44e
python analysis/cluster_detector.py --graph data/current_graph.gpickle
python analysis/score_calculator.py --clusters data/clusters.json --output reports/output/scores.json
```

## Revenue Model

| Service | Price | Description |
|---------|-------|-------------|
| **Per-Analysis Fee** | $500–$2,000 | One-time analysis of up to 100K wallets. Price depends on dataset size and chain complexity. |
| **Subscription — Monthly Monitoring** | $3,000/mo | Ongoing surveillance: weekly report + real-time alerts for new Sybil clusters. |
| **Subscription — Quarterly Audit** | $5,000/quarter | Deep-dive analysis with full report, methodology review, and on-chain score updates. |

### Revenue Targets

| Milestone | Target | Timeline |
|-----------|--------|----------|
| M2 | $2,000 MRR | Month 2 |
| M4 | $8,000 MRR | Month 4 |
| M6 | $15,000 MRR | Month 6 |

## Project Structure

```
sybil-detection-oracle/
├── analysis/                 # Core analysis pipeline
│   ├── graph_builder.py      # Transaction graph construction
│   ├── cluster_detector.py   # ML clustering (DBSCAN, hierarchical)
│   └── score_calculator.py   # Sybil score computation
├── contracts/                # Solidity smart contracts
│   ├── SybilOracle.sol       # On-chain score registry
│   └── PaymentGate.sol       # Payment handling
├── docs/                     # Documentation & sales
│   ├── METHODOLOGY.md        # Detection methodology deep-dive
│   ├── CASE_STUDIES.md       # Real-world analysis examples
│   └── SALES_DECK.md         # Pitch deck for protocols
├── metrics/                  # Business metrics
│   ├── daily-revenue.csv     # Revenue tracking
│   └── client-roster.csv     # Client management
├── reports/                  # Client deliverables
│   └── template_analysis.md  # Analysis report template
├── models/                   # Trained ML models (gitignored)
├── data/                     # Raw and processed data
└── .github/workflows/        # CI/CD
    └── analyze.yml           # Automated analysis workflow
```

## Smart Contracts

### SybilOracle.sol

Stores Sybil scores mapped by wallet address. Allows protocol contracts to query scores on-chain. Features owner/keeper update mechanism and events for score changes.

### PaymentGate.sol

Handles client payments in ETH and ERC-20 tokens. Tracks client analysis requests and releases payments upon report delivery.

## Contributing

Contributions welcome. Please open an issue first to discuss proposed changes.

## License

MIT
