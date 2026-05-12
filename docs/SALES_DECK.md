# Sales Deck — Sybil Detection Oracle

> **Protect your airdrop. Secure your governance. Stop Sybil farmers.**

---

## The Problem: Airdrop Farming Is Draining Millions

Every major airdrop in crypto history has been exploited by Sybil farmers:

| Airdrop | Estimated Loss to Sybils | Date |
|---------|--------------------------|------|
| Uniswap (UNI) | $15M+ | Sep 2020 |
| 1inch (1INCH) | $8M+ | Dec 2020 |
| ENS (ENS) | $5M+ | Nov 2021 |
| Optimism (OP) #1 | $15M+ | Jun 2022 |
| Arbitrum (ARB) | $40M+ | Mar 2023 |
| StarkNet (STRK) | $30M+ | Feb 2024 |

**Total estimated losses: $100M+ across major airdrops.**

### Why Existing Solutions Fail

| Approach | Limitation |
|----------|------------|
| KYC | Permissionless blockchains reject gatekeeping |
| CAPTCHA / Gitcoin Passport | Bypassed by AI and mechanical turks |
| Simple heuristics (min tx count) | Sybils adapt — they now do 20+ interactions |
| Manual review | Cannot scale beyond 1K wallets |
| Off-chain only | Can't protect on-chain distribution mechanisms |

---

## The Solution: Sybil Detection Oracle

An on-chain oracle that:
1. **Analyzes the full transaction graph** of your airdrop participants
2. **Applies ML clustering** to detect coordinated wallet groups
3. **Assigns a Sybil score (0–100)** to every wallet
4. **Publishes scores on-chain** via `SybilOracle.sol`
5. **Your distribution contract queries scores** in real-time during claiming

### Key Differentiators

- **Graph-based, not heuristic**: Most tools check wallet age and tx count. We analyze the *relationships between wallets*.
- **On-chain by default**: Scores are published to a smart contract your protocol can call during distribution.
- **Explainable AI**: Every score comes with a JSON breakdown showing *why* a wallet was flagged.
- **Multi-chain**: Ethereum, Arbitrum, Optimism, StarkNet, Base, and any EVM chain.

---

## Case Study Format

> *[This section will be populated with real client data after the first engagements]*

### Client: **[PROTOCOL NAME]**
### Chain: **[CHAIN]**
### Dataset: **[X] wallets analyzed**
### Date: **[MONTH YEAR]**

#### Results

| Metric | Value |
|--------|-------|
| Total wallets analyzed | 52,847 |
| Sybil wallets detected | 3,214 (6.1%) |
| Potential savings | $1.2M (at $400 per wallet) |
| False positive rate | < 2% |
| Analysis time | 6 hours |

#### Detection Breakdown

```
Wallet Scores Distribution:
  High Risk (75-100):   1,847 wallets  (3.5%)
  Medium Risk (50-74):  1,367 wallets  (2.6%)
  Low Risk (25-49):     2,845 wallets  (5.4%)
  Minimal Risk (0-24):  46,788 wallets (88.5%)
```

#### Top Cluster Detected

- **Cluster size**: 342 wallets
- **Funding source**: Single address funded all 342 wallets over 48 hours
- **Pattern**: Each wallet performed exactly 3 interactions, then transferred to consolidation address
- **Sybil score**: 94/100 for all 342 wallets
- **Classification**: High-confidence Sybil — coordinated farm

---

## Pricing Tiers

### One-Time Analysis

| Dataset Size | Price | Delivery Time |
|-------------|-------|---------------|
| ≤ 10K wallets | $500 | 24 hours |
| 10K – 50K wallets | $1,000 | 48 hours |
| 50K – 100K wallets | $1,500 | 72 hours |
| 100K – 500K wallets | $2,000 | 1 week |
| 500K+ wallets | Custom quote | Negotiable |

*Includes: full report (PDF + JSON), on-chain score deployment, and 30-minute results review call.*

### Subscription — Ongoing Monitoring

| Tier | Price | Features |
|------|-------|----------|
| **Starter** | $1,500/mo | Monthly analysis, 1 chain, up to 10K wallets |
| **Growth** | $3,000/mo | Weekly analysis, 3 chains, up to 50K wallets, real-time alerts |
| **Enterprise** | $5,000/mo | Daily analysis, all chains, unlimited wallets, dedicated support, SLA |

*All subscriptions include on-chain score updates via SybilOracle.sol.*

### Add-On Services

| Service | Price |
|---------|-------|
| Custom Sybil detection strategy | $3,000 flat |
| Retrospective analysis (historical airdrops) | $500 per dataset |
| Whitelabel report (your branding) | $1,000 per report |
| API integration support | $2,000 flat |

---

## ROI Calculator

**Scenario**: Protocol distributing $10M in tokens to 100K wallets.

| Without Sybil Oracle | With Sybil Oracle |
|---------------------|-------------------|
| Estimated Sybil rate: 10% | Detected Sybil rate: 6-8% |
| Sybils receive: $1M | Sybils blocked: saving $600K-800K |
| Analysis cost: $0 | Analysis cost: $1,500 |
| **Net loss**: $1M | **Net savings**: $598,500+ |

**ROI**: 39,900%+ on a $1,500 analysis investment.

---

## How to Engage

1. **Discovery Call** (30 min) — We learn about your distribution and data needs
2. **Sample Analysis** (free) — We analyze a 1K wallet sample at no cost
3. **Full Engagement** — You chose a pricing tier, we deliver results
4. **Integration** — Your protocol contracts integrate with `SybilOracle.sol`
5. **Ongoing** — Monitoring subscription (optional) keeps your distribution clean

### Contact

**Email**: sybil@nousresearch.com
**Telegram**: @noussgybilbot (coming soon)
**GitHub**: https://github.com/ghassan-gaidi/sybil-detection-oracle

---

## FAQ

**Q: What chains do you support?**
A: Ethereum mainnet, Arbitrum, Optimism, Base, Polygon, StarkNet (via API), and any EVM-compatible chain with an RPC endpoint.

**Q: How long does analysis take?**
A: A 50K-wallet analysis typically completes in 2–6 hours depending on chain RPC speed.

**Q: Can you guarantee 100% accuracy?**
A: No — no Sybil detection system can. We target >90% precision and provide confidence scores so you can calibrate your own threshold.

**Q: What about false positives?**
A: Every flagged wallet includes a score breakdown. You can review and override before publishing. Our false positive rate is <5%.

**Q: Is this audited?**
A: The Solidity contracts are open source and will be audited by a third-party firm prior to production deployment.

**Q: Can I run this myself?**
A: Yes — the entire pipeline is open source. We charge for managed analysis, support, and on-chain publishing infrastructure.
