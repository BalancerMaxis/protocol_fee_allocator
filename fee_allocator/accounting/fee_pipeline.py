import datetime
import os
from decimal import Decimal
from typing import Dict
from typing import List

import pandas as pd
import requests
from munch import Munch
from web3 import Web3

from bal_tools import BalPoolsGauges, Subgraph
from fee_allocator.accounting import PROJECT_ROOT
from fee_allocator.accounting.collectors import collect_fee_info
from fee_allocator.accounting.distribution import calc_and_split_incentives
from fee_allocator.accounting.distribution import re_distribute_incentives
from fee_allocator.accounting.distribution import re_route_incentives
from fee_allocator.accounting.distribution import add_last_join_exit
from fee_allocator.accounting.logger import logger
from fee_allocator.accounting.settings import CORE_POOLS_URL
from fee_allocator.accounting.settings import Chains
from fee_allocator.accounting.settings import FEE_CONSTANTS_URL
from fee_allocator.accounting.settings import REROUTE_CONFIG_URL
from fee_allocator.helpers import calculate_aura_vebal_share
from fee_allocator.helpers import fetch_hh_aura_bribs
from fee_allocator.helpers import get_balancer_pool_snapshots
from fee_allocator.helpers import get_block_by_ts
from fee_allocator.helpers import get_twap_bpt_price


def run_fees(
    web3_instances: Munch[Web3],
    timestamp_now: int,
    timestamp_2_weeks_ago: int,
    output_file_name: str,
    fees_to_distribute: dict,
    mapped_pools_info: dict,
) -> dict:
    """
    This function is used to run the fee allocation process
    """
    # Fetch current core pools:
    core_pools = requests.get(CORE_POOLS_URL).json()
    # Fetch fee constants:
    fee_constants = requests.get(FEE_CONSTANTS_URL).json()
    # Fetch re-route config:
    reroute_config = requests.get(REROUTE_CONFIG_URL).json()
    target_blocks = {}
    pool_snapshots = {}
    collected_fees = {}
    incentives = {}
    bpt_twap_prices = {chain.value: {} for chain in Chains}

    # Estimate mainnet current block to calculate aura veBAL share
    _target_mainnet_block = get_block_by_ts(timestamp_now, Chains.MAINNET.value)
    aura_vebal_share = calculate_aura_vebal_share(
        web3_instances["mainnet"], _target_mainnet_block
    )
    logger.info(
        f"veBAL aura share at block {_target_mainnet_block}: {aura_vebal_share}"
    )
    existing_aura_bribs: List[Dict] = fetch_hh_aura_bribs()
    # Collect all BPT prices:
    for chain in Chains:
        print(f"Collecting BPT prices for Chain {chain.value}")
        poolutil = BalPoolsGauges(chain.value)
        listed_core_pools = core_pools.get(chain.value, None)
        pools = {}
        if listed_core_pools is None:
            continue
        ###  Remove any invalid core pools
        for pool_id, description in listed_core_pools.items():
            if poolutil.has_alive_preferential_gauge(pool_id):
                pools[pool_id] = description
            else:
                print(
                    f"Warning pool {pool_id}({description}) on chain {chain} is in the core pools list but does not have a gauge.  Skipping."
                )
        if chain.value == Chains.ZKEVM.value:
            print("SKIPPING ZKEVM DUE TO RPC ISSUES, CHANGE ME WHEN FIXED!")
            continue
        target_blocks[chain.value] = (
            get_block_by_ts(timestamp_now, chain.value),  # Block now
            get_block_by_ts(timestamp_2_weeks_ago, chain.value),  # Block 2 weeks ago
        )
        logger.info(
            f"Running fees collection for {chain.value} between blocks: "
            f"{target_blocks[chain.value]}"
        )

        logger.info(f"Collecting bpt prices for {chain.value}")
        for core_pool in pools.keys():
            _bpt_price = get_twap_bpt_price(
                core_pool,
                chain.value,
                getattr(web3_instances, chain.value),
                start_date=datetime.datetime.fromtimestamp(timestamp_2_weeks_ago),
                end_date=datetime.datetime.fromtimestamp(timestamp_now),
                block_number=target_blocks[chain.value][0],
            )
            bpt_twap_prices[chain.value][core_pool] = _bpt_price
            logger.info(
                f"Collected bpt price for {pools[core_pool]} pool on {chain.value}: {_bpt_price}"
            )
        logger.info(
            f"Collecting pool snapshots for {chain.value} between blocks: "
            f"{target_blocks[chain.value]}"
        )
        # Also, collect all pool snapshots:
        graph_url = Subgraph(chain.value).get_subgraph_url()
        pool_snapshots[chain.value] = (
            get_balancer_pool_snapshots(
                target_blocks[chain.value][0], graph_url
            ),  # now
            get_balancer_pool_snapshots(
                target_blocks[chain.value][1], graph_url
            ),  # 2 weeks ago
        )
        logger.info(
            f"Colllect fees for {chain.value} between blocks: "
            f"{target_blocks[chain.value]}"
        )
        collected_fees[chain.value] = collect_fee_info(
            core_pools[chain.value],
            chain,
            pool_snapshots[chain.value][0],
            pool_snapshots[chain.value][1],
            start_ts=timestamp_2_weeks_ago,
            end_ts=timestamp_now,
            bpt_twap_prices=bpt_twap_prices,
        )

        # Now we have all the data we need to run the fee allocation process
        logger.info(f"Running fee allocation for {chain.value}")
        _incentives = calc_and_split_incentives(
            collected_fees[chain.value],
            chain.value,
            Decimal(fees_to_distribute[chain.value]),
            Decimal(fee_constants["min_aura_incentive"]),
            Decimal(fee_constants["dao_share_pct"]),
            Decimal(fee_constants["vebal_share_pct"]),
            Decimal(fee_constants["min_existing_aura_incentive"]),
            Decimal(aura_vebal_share),
            existing_aura_bribs,
            mapped_pools_info,
        )
        re_routed_incentives = re_route_incentives(_incentives, chain, reroute_config)
        redistributed_incentives = re_distribute_incentives(
            re_routed_incentives,
            Decimal(fee_constants["min_aura_incentive"]),
            Decimal(fee_constants["min_vote_incentive_amount"]),
        )
        ## Add data about last join/exit
        incentives[chain.value] = add_last_join_exit(redistributed_incentives, chain)
    # Wrap into dataframe and sort by earned fees and store to csv
    joint_incentives_data = {
        **incentives[Chains.MAINNET.value],
        **incentives[Chains.ARBITRUM.value],
        **incentives[Chains.POLYGON.value],
        **incentives[Chains.BASE.value],
        **incentives[Chains.AVALANCHE.value],
        **incentives[Chains.GNOSIS.value],
        **incentives.get(Chains.ZKEVM.value, {}),
    }
    joint_incentives_df = pd.DataFrame.from_dict(joint_incentives_data, orient="index")

    incentives_df_sorted = joint_incentives_df.sort_values(
        by=["chain", "earned_fees"], ascending=False
    )
    allocations_file_name = os.path.join(
        PROJECT_ROOT, f"fee_allocator/allocations/{output_file_name}"
    )
    incentives_df_sorted.to_csv(allocations_file_name)
    return joint_incentives_data
