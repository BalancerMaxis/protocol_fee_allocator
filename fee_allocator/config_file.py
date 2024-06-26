import os
from decimal import Decimal
from enum import Enum

import requests
from munch import Munch
from web3 import Web3
from web3.middleware import geth_poa_middleware

# Copied from https://raw.githubusercontent.com/BalancerMaxis/bal_addresses/main/extras/chains.json
FEES_CONSTANTS = requests.get(
    "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/protocol_fees_constants.json"
).json()

CORE_POOLS = requests.get(
    "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/core_pools.json"
).json()

REROUTE_CONFIG = requests.get(
    "https://raw.githubusercontent.com/BalancerMaxis/multisig-ops/main/config/core_pools_rerouting.json"
).json()


class Chains(Enum):
    POLYGON = "polygon"
    MAINNET = "mainnet"
    ARBITRUM = "arbitrum"
    # OPTIMISM = "optimism"
    GNOSIS = "gnosis"
    AVALANCHE = "avalanche"
    BASE = "base"


WEB3_INSTANCES = Munch()
WEB3_INSTANCES[Chains.MAINNET.value] = Web3(Web3.HTTPProvider(os.environ["ETHNODEURL"]))
# poly_web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
poly_web3 = Web3(Web3.HTTPProvider(os.environ["POLYNODEURL"]))
poly_web3.middleware_onion.inject(geth_poa_middleware, layer=0)
WEB3_INSTANCES[Chains.POLYGON.value] = poly_web3
WEB3_INSTANCES[Chains.ARBITRUM.value] = Web3(
    Web3.HTTPProvider(os.environ["ARBNODEURL"])
)
GNOSIS_PARAMS = {"headers": {"Authorization": f"Bearer {os.environ['GNOSIS_API_KEY']}"}}
WEB3_INSTANCES[Chains.GNOSIS.value] = Web3(
    Web3.HTTPProvider(os.environ["GNOSISNODEURL"], request_kwargs=GNOSIS_PARAMS)
)
WEB3_INSTANCES[Chains.BASE.value] = Web3(Web3.HTTPProvider(os.environ["BASENODEURL"]))
WEB3_INSTANCES[Chains.AVALANCHE.value] = Web3(
    Web3.HTTPProvider(os.environ["AVALANCHENODEURL"])
)

# Define constants for Arbitrum:
BALANCER_GRAPH_URLS = Munch()
BALANCER_GRAPH_URLS[Chains.ARBITRUM.value] = (
    "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-arbitrum-v2"
)
BALANCER_GRAPH_URLS[Chains.MAINNET.value] = (
    "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-v2"
)
BALANCER_GRAPH_URLS[Chains.POLYGON.value] = (
    "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-polygon-v2"
)
BALANCER_GRAPH_URLS[Chains.GNOSIS.value] = (
    "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-gnosis-chain-v2"
)
BALANCER_GRAPH_URLS[Chains.BASE.value] = (
    "https://api.studio.thegraph.com/query/24660/balancer-base-v2/version/latest"
)
BALANCER_GRAPH_URLS[Chains.AVALANCHE.value] = (
    "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-avalanche-v2"
)
