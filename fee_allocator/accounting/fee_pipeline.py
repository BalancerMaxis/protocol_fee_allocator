import datetime
import json
from collections import defaultdict
from decimal import Decimal
from typing import Dict

import pandas as pd
import requests
from munch import Munch
from web3 import Web3

from fee_allocator.accounting.logger import logger
from fee_allocator.accounting.settings import BALANCER_GRAPH_URLS
from fee_allocator.accounting.settings import CORE_POOLS_URL
from fee_allocator.accounting.settings import Chains
from fee_allocator.accounting.settings import FEE_CONSTANTS_URL
from fee_allocator.accounting.settings import REROUTE_CONFIG_URL
from fee_allocator.helpers import calculate_aura_vebal_share
from fee_allocator.helpers import fetch_token_price_balgql
from fee_allocator.helpers import get_balancer_pool_snapshots
from fee_allocator.helpers import get_block_by_ts
from fee_allocator.helpers import get_twap_bpt_price


# Let's calculate share of fees paid by each pool on each chain
def calc_and_split_incentives(
        fees: Dict, chain: str, fees_to_distribute: Decimal,
        min_aura_incentive: Decimal, dao_share: Decimal, vebal_share: Decimal,
        aura_vebal_share: Decimal
) -> Dict[str, Dict]:
    pool_incentives = {}
    # Calculate pool share in fees
    fees_to_distr_wo_dao_vebal = fees_to_distribute - (fees_to_distribute * dao_share) - (
            fees_to_distribute * vebal_share)
    # Calculate totals
    bpt_fees = sum([data['bpt_token_fee_in_usd'] for pool, data in fees.items()])
    token_fees = sum([data['token_fees_in_usd'] for pool, data in fees.items()])
    total_fees = bpt_fees + token_fees
    if not total_fees:
        return {}
    aura_bal_switch = True
    for pool, data in fees.items():
        pool_fees = data['bpt_token_fee_in_usd'] + data['token_fees_in_usd']
        pool_share = pool_fees / Decimal(total_fees)
        # If aura incentives is less than 500 USDC, we pay all incentives to balancer
        aura_incentives = round(pool_share * fees_to_distr_wo_dao_vebal * aura_vebal_share, 2)
        if aura_incentives <= min_aura_incentive:
            if aura_bal_switch:
                aura_incentives = Decimal(0)
                bal_incentives = round(pool_share * fees_to_distr_wo_dao_vebal, 2)
                aura_bal_switch = not aura_bal_switch
            else:
                aura_incentives = round(pool_share * fees_to_distr_wo_dao_vebal, 2)
                bal_incentives = Decimal(0)
                aura_bal_switch = not aura_bal_switch

        else:
            bal_incentives = round(pool_share * fees_to_distr_wo_dao_vebal * (1 - aura_vebal_share),
                                   2)
        fees_to_dao = round(pool_share * fees_to_distribute * dao_share, 2)
        fees_to_vebal = round(pool_share * fees_to_distribute * vebal_share, 2)
        # Split fees between aura and bal fees
        pool_incentives[pool] = {
            "chain": chain,
            "symbol": data['symbol'],
            "earned_fees": pool_fees,
            "fees_to_vebal": fees_to_vebal,
            "fees_to_dao": fees_to_dao,
            "total_incentives": aura_incentives + bal_incentives,
            "aura_incentives": aura_incentives,
            "bal_incentives": bal_incentives,
            "redirected_incentives": Decimal(0),
            "reroute_incentives": Decimal(0),
        }
    return pool_incentives


def re_route_incentives(
        incentives: Dict[str, Dict], chain: Chains, reroute: Dict
) -> Dict[str, Dict]:
    """
    If pool is in re-route configuration,
        all incentives from that pool should be distributed to destination pool
      Ex: {source_pool: destination_pool}
    """
    if chain.value not in reroute:
        return incentives
    for pool_id, _data in incentives.items():
        if pool_id in reroute[chain.value]:
            # Re route everything to destination pool and set source pool incentives to 0
            incentives[reroute[chain.value][pool_id]]['aura_incentives'] += _data['aura_incentives']
            incentives[reroute[chain.value][pool_id]]['bal_incentives'] += _data['bal_incentives']
            # Increase total incentives by aura and bal incentives
            _total_incentives = _data['aura_incentives'] + _data['bal_incentives']
            incentives[reroute[chain.value][pool_id]]['total_incentives'] += _total_incentives
            # Mark source pool incentives as rerouted
            incentives[reroute[chain.value][pool_id]]['reroute_incentives'] += _data[
                'total_incentives']
            incentives[pool_id]['aura_incentives'] = 0
            incentives[pool_id]['bal_incentives'] = 0
    return incentives


def re_distribute_incentives(
        incentives: Dict[str, Dict], min_aura_incentive: Decimal, min_incentive_amount: Decimal,
) -> Dict[str, Dict]:
    """
    If some pools received < min_vote_incentive_amount all incentives from that pool
        should be distributed to pools that received > min_vote_incentive_amount by weight
    """
    # Collect pools that received < min_vote_incentive_amount
    pools_to_redistribute = {}
    for pool_id, _data in incentives.items():
        if _data['total_incentives'] < Decimal(min_incentive_amount):
            pools_to_redistribute[pool_id] = _data
    # Collect pools that received > min_vote_incentive_amount
    pools_to_receive = {}
    for pool_id, _data in incentives.items():
        if _data['total_incentives'] > Decimal(min_incentive_amount):
            pools_to_receive[pool_id] = _data
    # Redistribute incentives
    for pool_id, _data in pools_to_redistribute.items():
        # Calculate incentives to redistribute
        incentives_to_redistribute = _data['total_incentives']
        incentives_to_redistribute_aura = _data['aura_incentives']
        incentives_to_redistribute_bal = _data['bal_incentives']
        # Set incentives to redistribute to 0
        incentives[pool_id]['total_incentives'] = 0
        incentives[pool_id]['aura_incentives'] = 0
        incentives[pool_id]['bal_incentives'] = 0
        # Mark incentives as redistributed
        incentives[pool_id]['redirected_incentives'] = -incentives_to_redistribute
        # Redistribute incentives
        _pool_weights = {
            pool_id_to_receive: _data_to_receive['earned_fees'] / sum(
                [x['earned_fees'] for x in pools_to_receive.values()])
            for pool_id_to_receive, _data_to_receive in pools_to_receive.items()
        }
        for pool_id_to_receive, _data_to_receive in pools_to_receive.items():
            # Calculate pool weight:
            pool_weight = _pool_weights[pool_id_to_receive]
            # Calculate incentives to receive
            to_receive = round(incentives_to_redistribute * pool_weight, 2)
            to_receive_aura = round(incentives_to_redistribute_aura * pool_weight, 2)
            to_receive_bal = round(incentives_to_redistribute_bal * pool_weight, 2)
            # Need to check if aura or bal incentives
            # are less than min aura incentive and distribute accordingly
            if _data_to_receive['aura_incentives'] + to_receive_aura < min_aura_incentive:
                incentives[pool_id_to_receive]['bal_incentives'] += to_receive
            elif _data_to_receive['bal_incentives'] + to_receive_bal < min_aura_incentive:
                incentives[pool_id_to_receive]['aura_incentives'] += to_receive
            else:
                # In case both are > min aura incentive, we distribute evenly
                incentives[pool_id_to_receive]['aura_incentives'] += to_receive_aura
                incentives[pool_id_to_receive]['bal_incentives'] += to_receive_bal
            incentives[pool_id_to_receive]['total_incentives'] += to_receive
            incentives[pool_id_to_receive]['redirected_incentives'] += to_receive

    return incentives


def _collect_fee_info(
        pools: list[str],
        chain: Chains,
        pools_now: list[dict],
        pools_shifted: list[Dict],
        start_date: datetime.datetime,
        bpt_twap_prices: Dict[str, Dict]
) -> Dict[str, Dict]:
    """
    Collects fee info for all pools in the list.
    Returns dictionary with pool id as key and fee info as value
    """
    fees = {}
    token_fees = defaultdict(list)
    for pool in pools:
        current_fees_snapshots = [x for x in pools_now if x['pool']['id'] == pool]
        current_fees_snapshots.sort(key=lambda x: x['timestamp'], reverse=True)
        fees_2_weeks_ago = [x for x in pools_shifted if x['pool']['id'] == pool]
        fees_2_weeks_ago.sort(key=lambda x: x['timestamp'], reverse=True)
        # If pools doesn't have current fees it means it was not created yet, so we skip it
        if not current_fees_snapshots:
            continue
        pool_snapshot_now = current_fees_snapshots[0]
        pool_snapshot_2_weeks_ago = fees_2_weeks_ago[0] if len(fees_2_weeks_ago) > 0 else {}
        # Now we need to collect token fee info. Let's start with BPT tokens,
        # which is Balancer pool token. Notice that totalProtocolFeePaidInBPT can be null,
        # so we need to check for that
        bpt_token_fee = 0
        token_fees_in_usd = 0
        bpt_price_usd = bpt_twap_prices[chain.value][pool] or 0
        if pool_snapshot_now['pool']['totalProtocolFeePaidInBPT'] is not None:
            if pool_snapshot_2_weeks_ago:
                bpt_token_fee = float(
                    pool_snapshot_now['pool']['totalProtocolFeePaidInBPT']) - float(
                    pool_snapshot_2_weeks_ago['pool'][
                        'totalProtocolFeePaidInBPT'] or 0)  # If 2 weeks ago is null, set to 0
            else:
                bpt_token_fee = float(pool_snapshot_now['pool']['totalProtocolFeePaidInBPT'])
        else:
            # Collect fee info about fees paid in pool tokens.
            # Pool tokens fee info is in pool.tokens dictionary. This will be separate dictionary
            for token_data in pool_snapshot_now['pool']['tokens']:
                if pool_snapshot_2_weeks_ago:
                    token_data_2_weeks_ago = \
                        [t for t in pool_snapshot_2_weeks_ago['pool']['tokens'] if
                         t['address'] == token_data['address']][0]
                    token_fee = float(token_data.get('paidProtocolFees', None)) - float(
                        token_data_2_weeks_ago.get('paidProtocolFees', None) or 0)
                else:
                    token_fee = float(token_data.get('paidProtocolFees', None))
                # Get twap token price from Balancer API
                token_price = fetch_token_price_balgql(token_data['address'], chain.value,
                                                       start_date) or 0
                token_fees_in_usd += Decimal(token_fee) * Decimal(token_price)
        fees[pool_snapshot_now['pool']['id']] = {
            'symbol': pool_snapshot_now['pool']['symbol'],
            'pool_addr': pool_snapshot_now['pool']['address'],
            'bpt_token_fee': round(bpt_token_fee, 2),
            # One of two fields below should always be 0 because
            # fees are taken in either BPT or pool tokens
            'bpt_token_fee_in_usd': round(Decimal(bpt_token_fee) * bpt_price_usd, 2),
            'token_fees_in_usd': round(token_fees_in_usd, 2),
            'chain': chain.value,
            'token_fees': token_fees[pool_snapshot_now['pool']['symbol']]
        }
    return fees


def run_fees(web3_instances: Munch[Web3], timestamp_now: int,
             timestamp_2_weeks_ago: int) -> None:
    """
    This function is used to run the fee allocation process
    """

    datetime_now = datetime.datetime.fromtimestamp(timestamp_now)
    two_weeks_ago = datetime.datetime.fromtimestamp(timestamp_2_weeks_ago)
    with open(f'../fees_collected/fees_{two_weeks_ago.date()}_{datetime_now.date()}.json') as f:
        fees_to_distribute = json.load(f)
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
        web3_instances.mainnet, _target_mainnet_block
    )
    logger.info(f"veBAL aura share at block {_target_mainnet_block}: {aura_vebal_share}")
    # Collect all BPT prices:
    for chain in Chains:
        pools = core_pools.get(chain.value, None)
        if pools is None:
            continue
        target_blocks[chain.value] = (
            get_block_by_ts(timestamp_now, chain.value),  # Block now
            get_block_by_ts(timestamp_2_weeks_ago, chain.value)  # Block 2 weeks ago
        )
        logger.info(
            f"Running fees collection for {chain.value} between blocks: "
            f"{target_blocks[chain.value]}"
        )

        logger.info(f"Collecting bpt prices for {chain.value}")
        for core_pool in pools.keys():
            _bpt_price = get_twap_bpt_price(
                core_pool, chain.value, getattr(web3_instances, chain.value),
                start_date=datetime.datetime.fromtimestamp(timestamp_now),
                block_number=target_blocks[chain.value][0]
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
        pool_snapshots[chain.value] = (
            get_balancer_pool_snapshots(target_blocks[chain.value][0],
                                        BALANCER_GRAPH_URLS[chain.value]),  # now
            get_balancer_pool_snapshots(target_blocks[chain.value][1],
                                        BALANCER_GRAPH_URLS[chain.value]),  # 2 weeks ago
        )
        logger.info(f"Colllect fees for {chain.value} between blocks: "
                    f"{target_blocks[chain.value]}")
        collected_fees[chain.value] = _collect_fee_info(core_pools[chain.value], chain,
                                                        pool_snapshots[chain.value][0],
                                                        pool_snapshots[chain.value][1],
                                                        datetime_now, bpt_twap_prices)

        # Now we have all the data we need to run the fee allocation process
        logger.info(f"Running fee allocation for {chain.value}")
        _incentives = calc_and_split_incentives(
            collected_fees[chain.value],
            chain.value,
            Decimal(fees_to_distribute[chain.value]),
            Decimal(fee_constants['min_aura_incentive']),
            Decimal(fee_constants['dao_share_pct']),
            Decimal(fee_constants['vebal_share_pct']),
            aura_vebal_share=Decimal(aura_vebal_share)
        )
        re_routed_incentives = re_route_incentives(
            _incentives, chain, reroute_config
        )
        incentives[chain.value] = re_distribute_incentives(
            re_routed_incentives,
            Decimal(fee_constants['min_aura_incentive']),
            Decimal(fee_constants['min_vote_incentive_amount'])
        )
    # Wrap into dataframe and sort by earned fees and store to csv
    joint_incentives_data = {**incentives[Chains.MAINNET.value],
                             **incentives[Chains.ARBITRUM.value],
                             **incentives[Chains.POLYGON.value], **incentives[Chains.BASE.value],
                             **incentives[Chains.AVALANCHE.value],
                             **incentives.get(Chains.GNOSIS.value)}
    joint_incentives_df = pd.DataFrame.from_dict(joint_incentives_data, orient='index')
    incentives_df_sorted = joint_incentives_df.sort_values(
        by=['chain', 'earned_fees'], ascending=False
    )
    incentives_df_sorted.to_csv(
        f'../allocations/incentives_{two_weeks_ago.date()}_{datetime_now.date()}.csv')

    # Reconcile
    all_fees_sum = Decimal(round(sum(fees_to_distribute.values()), 2))

    all_incentives_sum = sum(
        [sum([x['fees_to_vebal'], x['fees_to_dao'], x['aura_incentives'], x['bal_incentives']]) for
         x in
         joint_incentives_data.values()])
    # Asert almost equal considering that result can be negative
    delta = all_fees_sum - all_incentives_sum
    # Make delta positive
    if delta < 0:
        delta = -delta
    assert delta < Decimal(0.01), f"Reconciliation failed. Delta: {delta}"
