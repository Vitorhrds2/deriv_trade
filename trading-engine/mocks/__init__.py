"""Trading Engine High-Fidelity Mock Infrastructure."""

try:
    from mocks.kalshi_fix_mock import (
        KalshiFixMockServer,
        KalshiFixClient,
        BinaryContractOrderBook,
        FixMessage,
        build_fix_message,
        parse_fix_message,
    )
    from mocks.hyperliquid_mempool_mock import (
        HyperliquidMempoolEmulator,
        MempoolTransaction,
        CommittedBlock,
    )
except ImportError:
    from trading_engine.mocks.kalshi_fix_mock import (
        KalshiFixMockServer,
        KalshiFixClient,
        BinaryContractOrderBook,
        FixMessage,
        build_fix_message,
        parse_fix_message,
    )
    from trading_engine.mocks.hyperliquid_mempool_mock import (
        HyperliquidMempoolEmulator,
        MempoolTransaction,
        CommittedBlock,
    )

__all__ = [
    "KalshiFixMockServer",
    "KalshiFixClient",
    "BinaryContractOrderBook",
    "FixMessage",
    "build_fix_message",
    "parse_fix_message",
    "HyperliquidMempoolEmulator",
    "MempoolTransaction",
    "CommittedBlock",
]
