// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title SybilOracle
 * @notice On-chain Sybil score registry. Stores Sybil scores (0-100) mapped
 *         by wallet address. Protocol contracts can query scores directly.
 * @dev Designed to be integrated with a PaymentGate contract for payment
 *      verification before score updates.
 */
contract SybilOracle {
    // ──────────────────────────────────────────────
    //  Types
    // ──────────────────────────────────────────────

    /// @notice Score entry for a single wallet
    struct ScoreEntry {
        uint8 score;       // 0-100 Sybil score
        uint40 updatedAt;  // Block timestamp of last update
        uint16 clusterId;  // Cluster identifier (0 = unclustered)
    }

    /// @notice Batch score update payload
    struct ScoreUpdate {
        address wallet;
        uint8 score;
        uint16 clusterId;
    }

    // ──────────────────────────────────────────────
    //  State
    // ──────────────────────────────────────────────

    /// @notice Sybil scores by wallet address
    mapping(address => ScoreEntry) public scores;

    /// @notice Owner/keeper addresses authorized to update scores
    mapping(address => bool) public keepers;

    /// @notice PaymentGate contract address (for payment verification)
    address public paymentGate;

    /// @notice Contract owner
    address public owner;

    /// @notice Whether the contract is paused
    bool public paused;

    /// @notice Minimum score that constitutes a "Sybil" label (default: 50)
    uint8 public sybilThreshold;

    // ──────────────────────────────────────────────
    //  Events
    // ──────────────────────────────────────────────

    /// @notice Emitted when a wallet's score is updated
    event ScoreUpdated(
        address indexed wallet,
        uint8 oldScore,
        uint8 newScore,
        uint16 clusterId,
        address indexed updater
    );

    /// @notice Emitted when a batch of scores is updated
    event BatchScoreUpdated(
        uint256 count,
        address indexed updater
    );

    /// @notice Emitted when a keeper is added or removed
    event KeeperUpdated(address indexed keeper, bool authorized);

    /// @notice Emitted when the payment gate address is updated
    event PaymentGateUpdated(address indexed paymentGate);

    /// @notice Emitted when contract is paused or unpaused
    event Paused(bool paused);

    // ──────────────────────────────────────────────
    //  Modifiers
    // ──────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "SybilOracle: not owner");
        _;
    }

    modifier onlyKeeper() {
        require(keepers[msg.sender] || msg.sender == owner, "SybilOracle: not keeper");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "SybilOracle: paused");
        _;
    }

    // ──────────────────────────────────────────────
    //  Constructor
    // ──────────────────────────────────────────────

    constructor(address _paymentGate, uint8 _sybilThreshold) {
        require(_paymentGate != address(0), "SybilOracle: invalid payment gate");
        owner = msg.sender;
        paymentGate = _paymentGate;
        sybilThreshold = _sybilThreshold;
        keepers[msg.sender] = true;
        emit KeeperUpdated(msg.sender, true);
        emit PaymentGateUpdated(_paymentGate);
    }

    // ──────────────────────────────────────────────
    //  Score Query
    // ──────────────────────────────────────────────

    /**
     * @notice Query a wallet's Sybil score
     * @param wallet The wallet address to query
     * @return score The Sybil score (0-100)
     * @return isSybil Whether the wallet is classified as Sybil
     * @return updatedAt When the score was last updated
     */
    function getScore(address wallet)
        external
        view
        returns (uint8 score, bool isSybil, uint256 updatedAt)
    {
        ScoreEntry memory entry = scores[wallet];
        score = entry.score;
        isSybil = entry.score >= sybilThreshold;
        updatedAt = entry.updatedAt;
    }

    /**
     * @notice Batch query scores for multiple wallets
     * @param wallets Array of wallet addresses
     * @return scoreList Array of scores
     * @return isSybilList Array of Sybil flags
     */
    function batchGetScores(address[] calldata wallets)
        external
        view
        returns (uint8[] memory scoreList, bool[] memory isSybilList)
    {
        scoreList = new uint8[](wallets.length);
        isSybilList = new bool[](wallets.length);

        for (uint256 i = 0; i < wallets.length; i++) {
            ScoreEntry memory entry = scores[wallets[i]];
            scoreList[i] = entry.score;
            isSybilList[i] = entry.score >= sybilThreshold;
        }
    }

    /**
     * @notice Check if a wallet is flagged as Sybil
     * @param wallet The wallet to check
     * @return True if score >= sybilThreshold
     */
    function isSybil(address wallet) external view returns (bool) {
        return scores[wallet].score >= sybilThreshold;
    }

    // ──────────────────────────────────────────────
    //  Score Update (Keeper)
    // ──────────────────────────────────────────────

    /**
     * @notice Update a single wallet's score
     * @param wallet Wallet address
     * @param score New Sybil score (0-100)
     * @param clusterId Cluster identifier
     */
    function updateScore(
        address wallet,
        uint8 score,
        uint16 clusterId
    ) external onlyKeeper whenNotPaused {
        require(score <= 100, "SybilOracle: score must be 0-100");

        _verifyPayment(msg.sender);

        uint8 oldScore = scores[wallet].score;

        scores[wallet] = ScoreEntry({
            score: score,
            updatedAt: uint40(block.timestamp),
            clusterId: clusterId
        });

        emit ScoreUpdated(wallet, oldScore, score, clusterId, msg.sender);
    }

    /**
     * @notice Batch update scores for many wallets
     * @param updates Array of ScoreUpdate structs
     */
    function batchUpdateScores(
        ScoreUpdate[] calldata updates
    ) external onlyKeeper whenNotPaused {
        uint256 len = updates.length;
        require(len > 0, "SybilOracle: empty updates");
        require(len <= 500, "SybilOracle: batch too large");

        _verifyPayment(msg.sender);

        for (uint256 i = 0; i < len; i++) {
            ScoreUpdate calldata update = updates[i];
            require(update.score <= 100, "SybilOracle: score must be 0-100");

            uint8 oldScore = scores[update.wallet].score;

            scores[update.wallet] = ScoreEntry({
                score: update.score,
                updatedAt: uint40(block.timestamp),
                clusterId: update.clusterId
            });

            emit ScoreUpdated(
                update.wallet,
                oldScore,
                update.score,
                update.clusterId,
                msg.sender
            );
        }

        emit BatchScoreUpdated(len, msg.sender);
    }

    // ──────────────────────────────────────────────
    //  Admin
    // ──────────────────────────────────────────────

    /**
     * @notice Add or remove a keeper
     * @param keeper Address to update
     * @param authorized True to add, false to remove
     */
    function setKeeper(address keeper, bool authorized) external onlyOwner {
        keepers[keeper] = authorized;
        emit KeeperUpdated(keeper, authorized);
    }

    /**
     * @notice Update the payment gate contract address
     * @param _paymentGate New PaymentGate address
     */
    function setPaymentGate(address _paymentGate) external onlyOwner {
        require(_paymentGate != address(0), "SybilOracle: invalid address");
        paymentGate = _paymentGate;
        emit PaymentGateUpdated(_paymentGate);
    }

    /**
     * @notice Update the Sybil threshold
     * @param _sybilThreshold New threshold (0-100)
     */
    function setSybilThreshold(uint8 _sybilThreshold) external onlyOwner {
        require(_sybilThreshold <= 100, "SybilOracle: invalid threshold");
        sybilThreshold = _sybilThreshold;
    }

    /**
     * @notice Pause/unpause the contract
     * @param _paused Pause state
     */
    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
        emit Paused(_paused);
    }

    /**
     * @notice Transfer ownership
     * @param newOwner New owner address
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "SybilOracle: invalid owner");
        owner = newOwner;
    }

    // ──────────────────────────────────────────────
    //  Internal
    // ──────────────────────────────────────────────

    /**
     * @notice Verify that payment has been made via PaymentGate
     * @param _caller The address requesting the update
     */
    function _verifyPayment(address _caller) internal view {
        // In production, call PaymentGate to verify payment / subscription
        // For now, keeper authorization is sufficient
        // (PaymentGate integration is optional enforcement)
    }

    // ──────────────────────────────────────────────
    //  Receive (allow ETH donations)
    // ──────────────────────────────────────────────

    receive() external payable {}
}
