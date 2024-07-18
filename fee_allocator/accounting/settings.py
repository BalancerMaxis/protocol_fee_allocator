from enum import Enum


class Chains(Enum):
    MAINNET = "mainnet"
    ARBITRUM = "arbitrum"
    POLYGON = "polygon"
    # OPTIMISM = "optimism"
    GNOSIS = "gnosis"
    AVALANCHE = "avalanche"
    BASE = "base"
    ZKEVM = "zkevm"


FEE_CONSTANTS_URL = "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/protocol_fees_constants.json"
CORE_POOLS_URL = "https://raw.githubusercontent.com/BalancerMaxis/bal_addresses/main/outputs/core_pools.json"
REROUTE_CONFIG_URL = "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/core_pools_rerouting.json"
OVERRIDES_URL = "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/ae9cfa3d627dfb66d1fba6f824c316e4769bbf5a/config/pool_incentives_overrides.json"
