from enum import Enum

from munch import Munch


class Chains(Enum):
    MAINNET = "mainnet"
    ARBITRUM = "arbitrum"
    POLYGON = "polygon"
    # OPTIMISM = "optimism"
    GNOSIS = "gnosis"
    AVALANCHE = "avalanche"
    BASE = "base"
    ZKEVM = "zkevm"


FEE_CONSTANTS_URL = (
    "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/protocol_fees_constants.json"
)
CORE_POOLS_URL = "https://raw.githubusercontent.com/BalancerMaxis/bal_addresses/main/outputs/core_pools.json"

REROUTE_CONFIG_URL = (
    "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/core_pools_rerouting.json"
)
# Define constants for Arbitrum:
BALANCER_GRAPH_URLS = Munch()
BALANCER_GRAPH_URLS[
    Chains.ARBITRUM.value
] = "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-arbitrum-v2"
BALANCER_GRAPH_URLS[
    Chains.MAINNET.value
] = "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-v2"
BALANCER_GRAPH_URLS[
    Chains.POLYGON.value
] = "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-polygon-v2"
BALANCER_GRAPH_URLS[
    Chains.GNOSIS.value
] = "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-gnosis-chain-v2"
BALANCER_GRAPH_URLS[
    Chains.BASE.value
] = "https://api.studio.thegraph.com/query/24660/balancer-base-v2/version/latest"
BALANCER_GRAPH_URLS[
    Chains.AVALANCHE.value
] = "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-avalanche-v2"
BALANCER_GRAPH_URLS[
    Chains.ZKEVM.value
] = "https://api.studio.thegraph.com/query/24660/balancer-polygon-zk-v2/version/latest"
