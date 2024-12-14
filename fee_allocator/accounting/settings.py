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


MAX_INCENTIVES_AS_PCT_OF_EARNED = (
    1  # TODO move this to PROTOCOL_FEE_CONSTANTS in multisig ops
)
FEE_CONSTANTS_URL = "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/protocol_fees_constants.json"
CORE_POOLS_URL = "https://raw.githubusercontent.com/BalancerMaxis/bal_addresses/main/outputs/core_pools.json"
REROUTE_CONFIG_URL = "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/core_pools_rerouting.json"
OVERRIDES_URL = "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/ae9cfa3d627dfb66d1fba6f824c316e4769bbf5a/config/pool_incentives_overrides.json"
#  Various distribution logic run one after the next can result in a state where there is a very small veBAL bribe and
#  a sizable vlAURA bribe.  If there is less than this amount allocated to veBAL markets on a single gauge, move it over to vlAURA to save gass
MIN_VERBAL_BRIBE_AFTER_ALL_REDISTRIBUTIONS = 75  # USDC
