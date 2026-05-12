// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PaymentGate
 * @notice Handles client payments in ETH/ERC-20 for Sybil analysis services.
 *         Tracks analysis requests and releases payments on report delivery.
 * @dev Supports both one-time analysis fees and subscription billing.
 */
contract PaymentGate {
    // ──────────────────────────────────────────────
    //  Types
    // ──────────────────────────────────────────────

    /// @notice Client details
    struct Client {
        string name;
        address wallet;
        uint256 totalPaid;
        uint256 analysisCount;
        uint256 lastPaymentAt;
        bool active;
    }

    /// @notice Analysis request from a client
    struct AnalysisRequest {
        address client;
        string datasetDescription;  // e.g., "Arbitrum Airdrop Round 2 - 50K wallets"
        uint256 walletCount;
        uint256 fee;               // Fee in wei (ETH) or token units
        address token;             // address(0) for ETH, token address for ERC-20
        uint256 requestedAt;
        bool fulfilled;
        bool paidOut;              // Whether payment was released to operator
    }

    /// @notice Pricing tier
    struct PricingTier {
        uint256 minWallets;
        uint256 maxWallets;
        uint256 price;             // Price in wei (ETH)
    }

    // ──────────────────────────────────────────────
    //  State
    // ──────────────────────────────────────────────

    /// @notice Contract owner (operator)
    address public owner;

    /// @notice SybilOracle contract address
    address public sybilOracle;

    /// @notice Maintenance fee percentage (basis points, e.g., 250 = 2.5%)
    uint16 public maintenanceFeeBps;

    /// @notice Client registry
    mapping(address => Client) public clients;

    /// @notice Analysis request counter
    uint256 public requestCounter;

    /// @notice Analysis requests by ID
    mapping(uint256 => AnalysisRequest) public requests;

    /// @notice Pricing tiers
    PricingTier[] public pricingTiers;

    /// @notice Whether contract is paused
    bool public paused;

    /// @notice Withdrawable balance for operator
    uint256 public operatorBalance;

    // ──────────────────────────────────────────────
    //  Events
    // ──────────────────────────────────────────────

    event ClientRegistered(address indexed client, string name);
    event AnalysisRequested(
        uint256 indexed requestId,
        address indexed client,
        string description,
        uint256 walletCount,
        uint256 fee,
        address token
    );
    event AnalysisFulfilled(uint256 indexed requestId);
    event PaymentReleased(uint256 indexed requestId, uint256 amount);
    event OperatorWithdrawn(address indexed to, uint256 amount);
    event PricingTierSet(uint256 index, uint256 minWallets, uint256 maxWallets, uint256 price);

    // ──────────────────────────────────────────────
    //  Modifiers
    // ──────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "PaymentGate: not owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "PaymentGate: paused");
        _;
    }

    // ──────────────────────────────────────────────
    //  Constructor
    // ──────────────────────────────────────────────

    constructor(address _sybilOracle, uint16 _maintenanceFeeBps) {
        require(_sybilOracle != address(0), "PaymentGate: invalid oracle address");
        require(_maintenanceFeeBps <= 1000, "PaymentGate: fee too high"); // max 10%
        owner = msg.sender;
        sybilOracle = _sybilOracle;
        maintenanceFeeBps = _maintenanceFeeBps;
    }

    // ──────────────────────────────────────────────
    //  Pricing
    // ──────────────────────────────────────────────

    /**
     * @notice Set pricing tiers
     * @param minWallets Minimum wallet count for tier
     * @param maxWallets Maximum wallet count for tier
     * @param price Price in wei
     */
    function setPricingTier(
        uint256 minWallets,
        uint256 maxWallets,
        uint256 price
    ) external onlyOwner {
        pricingTiers.push(PricingTier({
            minWallets: minWallets,
            maxWallets: maxWallets,
            price: price
        }));
        emit PricingTierSet(pricingTiers.length - 1, minWallets, maxWallets, price);
    }

    /**
     * @notice Remove a pricing tier
     * @param index Index of tier to remove
     */
    function removePricingTier(uint256 index) external onlyOwner {
        require(index < pricingTiers.length, "PaymentGate: invalid index");
        pricingTiers[index] = pricingTiers[pricingTiers.length - 1];
        pricingTiers.pop();
    }

    /**
     * @notice Get the price for a given wallet count
     * @param walletCount Number of wallets to analyze
     * @return price Price in wei
     * @return tokenToken Address (address(0) = ETH)
     */
    function getPrice(uint256 walletCount)
        external
        view
        returns (uint256 price, address tokenToken)
    {
        for (uint256 i = 0; i < pricingTiers.length; i++) {
            PricingTier memory tier = pricingTiers[i];
            if (walletCount >= tier.minWallets && walletCount <= tier.maxWallets) {
                return (tier.price, address(0));
            }
        }
        revert("PaymentGate: no matching tier");
    }

    // ──────────────────────────────────────────────
    //  Client Registration
    // ──────────────────────────────────────────────

    /**
     * @notice Register as a client
     * @param name Client name/organization
     */
    function registerClient(string calldata name) external whenNotPaused {
        require(bytes(name).length > 0, "PaymentGate: name required");
        clients[msg.sender] = Client({
            name: name,
            wallet: msg.sender,
            totalPaid: 0,
            analysisCount: 0,
            lastPaymentAt: 0,
            active: true
        });
        emit ClientRegistered(msg.sender, name);
    }

    // ──────────────────────────────────────────────
    //  Request Analysis (Payment)
    // ──────────────────────────────────────────────

    /**
     * @notice Request a new analysis (pay with ETH)
     * @param datasetDescription Description of the dataset
     * @param walletCount Number of wallets to analyze
     */
    function requestAnalysis(
        string calldata datasetDescription,
        uint256 walletCount
    ) external payable whenNotPaused {
        require(clients[msg.sender].active, "PaymentGate: not registered");
        require(walletCount > 0, "PaymentGate: invalid wallet count");

        // Find matching pricing tier
        uint256 fee = 0;
        bool found = false;
        for (uint256 i = 0; i < pricingTiers.length; i++) {
            PricingTier memory tier = pricingTiers[i];
            if (walletCount >= tier.minWallets && walletCount <= tier.maxWallets) {
                fee = tier.price;
                found = true;
                break;
            }
        }
        require(found, "PaymentGate: no matching tier");
        require(msg.value == fee, "PaymentGate: incorrect payment");

        // Update client record
        Client storage client = clients[msg.sender];
        client.totalPaid += fee;
        client.analysisCount += 1;
        client.lastPaymentAt = block.timestamp;

        // Create request
        requestCounter++;
        uint256 requestId = requestCounter;
        requests[requestId] = AnalysisRequest({
            client: msg.sender,
            datasetDescription: datasetDescription,
            walletCount: walletCount,
            fee: fee,
            token: address(0),
            requestedAt: block.timestamp,
            fulfilled: false,
            paidOut: false
        });

        // Add to operator balance (minus maintenance fee)
        uint256 maintenanceFee = (fee * maintenanceFeeBps) / 10000;
        operatorBalance += fee - maintenanceFee;

        emit AnalysisRequested(requestId, msg.sender, datasetDescription, walletCount, fee, address(0));
    }

    /**
     * @notice Request analysis paid with ERC-20 (simplified interface)
     * @param datasetDescription Description of dataset
     * @param walletCount Number of wallets
     * @param token ERC-20 token address
     * @param amount Amount of tokens
     */
    function requestAnalysisERC20(
        string calldata datasetDescription,
        uint256 walletCount,
        address token,
        uint256 amount
    ) external whenNotPaused {
        // In production, implement ERC-20 transferFrom
        // For now, placeholder
        require(clients[msg.sender].active, "PaymentGate: not registered");

        requestCounter++;
        requests[requestCounter] = AnalysisRequest({
            client: msg.sender,
            datasetDescription: datasetDescription,
            walletCount: walletCount,
            fee: amount,
            token: token,
            requestedAt: block.timestamp,
            fulfilled: false,
            paidOut: false
        });

        emit AnalysisRequested(requestCounter, msg.sender, datasetDescription, walletCount, amount, token);
    }

    // ──────────────────────────────────────────────
    //  Fulfillment
    // ──────────────────────────────────────────────

    /**
     * @notice Mark an analysis request as fulfilled (called by keeper/owner)
     * @param requestId ID of the request to fulfill
     */
    function fulfillRequest(uint256 requestId) external onlyOwner whenNotPaused {
        AnalysisRequest storage req = requests[requestId];
        require(req.client != address(0), "PaymentGate: request not found");
        require(!req.fulfilled, "PaymentGate: already fulfilled");

        req.fulfilled = true;
        emit AnalysisFulfilled(requestId);
    }

    /**
     * @notice Release payment for a fulfilled request
     * @param requestId ID of the request
     */
    function releasePayment(uint256 requestId) external onlyOwner {
        AnalysisRequest storage req = requests[requestId];
        require(req.fulfilled, "PaymentGate: not fulfilled");
        require(!req.paidOut, "PaymentGate: already paid out");

        req.paidOut = true;
        operatorBalance -= req.fee;

        // Release to operator (or split with analysts)
        payable(owner).transfer(req.fee);
        emit PaymentReleased(requestId, req.fee);
    }

    // ──────────────────────────────────────────────
    //  Operator Functions
    // ──────────────────────────────────────────────

    /**
     * @notice Withdraw operator balance
     */
    function withdraw() external onlyOwner {
        uint256 amount = operatorBalance;
        require(amount > 0, "PaymentGate: nothing to withdraw");
        operatorBalance = 0;
        payable(owner).transfer(amount);
        emit OperatorWithdrawn(owner, amount);
    }

    // ──────────────────────────────────────────────
    //  Admin
    // ──────────────────────────────────────────────

    function setSybilOracle(address _sybilOracle) external onlyOwner {
        require(_sybilOracle != address(0), "PaymentGate: invalid address");
        sybilOracle = _sybilOracle;
    }

    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "PaymentGate: invalid owner");
        owner = newOwner;
    }

    // ──────────────────────────────────────────────
    //  Receive
    // ──────────────────────────────────────────────

    receive() external payable {
        operatorBalance += msg.value;
    }
}
