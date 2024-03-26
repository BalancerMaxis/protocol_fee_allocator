import math
import datetime
from decimal import Decimal
from typing import Dict
from typing import List
from typing import Optional

from bal_addresses import BalPoolsGauges
from fee_allocator.accounting.settings import Chains


def calc_and_split_incentives(
        fees: Dict, chain: str, fees_to_distribute: Decimal,
        min_aura_incentive: Decimal, dao_share: Decimal, vebal_share: Decimal,
        min_existing_aura_incentive: Decimal, aura_vebal_share: Decimal,
        existing_aura_bribs: List[Dict],
        mapped_pools_info: Dict,
) -> Dict[str, Dict]:
    """
    Calculate and split incentives between aura and balancer pools
    """
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
    for pool, data in fees.items():
        pool_fees = data['bpt_token_fee_in_usd'] + data['token_fees_in_usd']
        pool_share = pool_fees / Decimal(total_fees)
        # If aura incentives is less than 500 USDC, we pay all incentives to balancer
        total_incentive = pool_share * fees_to_distr_wo_dao_vebal
        aura_incentives = round(total_incentive * aura_vebal_share, 2)
        # If pool has already existing X aura incentives, then it gets precise split of incentives between aura and bal
        # as aura_bal_ratio
        cumulative_aura_incentives = Decimal(0)
        for aura_brib in existing_aura_bribs:
            if aura_brib['proposal'] == mapped_pools_info.get(pool, "N/A").lower():
                # Calculate cumulative aura incentives for this pool
                cumulative_aura_incentives = Decimal(sum([x['value'] for x in aura_brib['bribes']]))
        # If cumulative aura incentives are more than X USDC, we distribute precisely between aura and bal
        if cumulative_aura_incentives >= min_existing_aura_incentive:
            print(f'Pool {pool} has {cumulative_aura_incentives} aura incentives! Allocating precisely...')
            bal_incentives = round(total_incentive - aura_incentives, 2)
        else:
            if aura_incentives <= min_aura_incentive:
                aura_incentives = Decimal(0)
                bal_incentives = round(total_incentive, 2)
            else:
                # All goes to aura in this case
                aura_incentives = round(total_incentive, 2)
                bal_incentives = Decimal(0)
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


def re_distribute_incentives(
        incentives: Dict[str, Dict], min_aura_incentive: Decimal, min_incentive_amount: Decimal,
        aura_vebal_share: Decimal
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

    # Now, go through each pool once again and redistribute aura and bal incentives considering aura_vebal_share
    for pool_id, _data in incentives.items():
        _aura_incentives = _data['aura_incentives']
        _bal_incentives = _data['bal_incentives']
        _total_incentives = _data['total_incentives']
        # Ignore pools with 0 incentives
        if _total_incentives == 0:
            continue
        # Calculate aura and bal incentives percentage
        aura_incentives_pct = _aura_incentives / _total_incentives
        # If aura incentives pct is approx equal to aura_vebal_share, we don't need to do anything
        if math.isclose(aura_incentives_pct, aura_vebal_share, rel_tol=1e-03, abs_tol=1e-03):
            print(f"Pool {pool_id} aura incentives pct is approx equal to aura_vebal_share, skipping...")
            continue
        # If aura incentives percentage is less than aura_vebal_share, we need to increase bal incentives
        if aura_incentives_pct >= aura_vebal_share:
            # Calculate how much we need to increase bal incentives
            bal_incentives_to_increase = round(
                _total_incentives * (aura_incentives_pct - aura_vebal_share), 2)
            # Calculate how much we need to decrease aura incentives but not to go below min aura incentive
            if _aura_incentives - bal_incentives_to_increase <= min_aura_incentive:
                # If aura incentives are less than min aura incentive after decreasing, we need to calculate
                # how much we need to decrease aura incentives to min aura incentive
                aura_incentives_to_decrease = _aura_incentives - min_aura_incentive
                # Decrease aura incentives to min aura incentive
                incentives[pool_id]['aura_incentives'] -= aura_incentives_to_decrease
                incentives[pool_id]['bal_incentives'] += aura_incentives_to_decrease
            else:
                # Increase bal incentives
                incentives[pool_id]['bal_incentives'] += bal_incentives_to_increase
                # Decrease aura incentives
                incentives[pool_id]['aura_incentives'] -= bal_incentives_to_increase
        # If aura incentives percentage is more than aura_vebal_share, we need to increase aura incentives
        else:
            # Calculate how much we need to increase aura incentives
            aura_incentives_to_increase = round(
                _total_incentives * (aura_vebal_share - aura_incentives_pct), 2)
            # Only increase aura incentives if it's more than min aura incentive
            if _aura_incentives + aura_incentives_to_increase < min_aura_incentive:
                continue
            # Increase aura incentives
            incentives[pool_id]['aura_incentives'] += aura_incentives_to_increase
            # Decrease bal incentives
            incentives[pool_id]['bal_incentives'] -= aura_incentives_to_increase
    return incentives

def add_last_join_exit(incentives: Dict[str, Dict], chain: Chains, alertTimeStamp: Optional[int] = None) -> Dict[str, Dict]:
    """
    adds last_join_exit for each pool in the incentives list for reporting.
    Returns the same thing as inputed with the additional field added for each line
    """
    q = BalPoolsGauges(chain.value)
    results = {}
    for pool_id, incentive_data in incentives.items():
        results[pool_id] = incentive_data
        timestamp = q.get_last_join_exit(pool_id)
        try:
            timestamp = q.get_last_join_exit(pool_id)
        except:
            results[pool_id]["last_join_exit"] = "Error fetching"
            continue
        gmt_time = datetime.datetime.utcfromtimestamp(timestamp)
        human_time = gmt_time.strftime('%Y-%m-%d %H:%M:%S')+"+00:00"
        if alertTimeStamp and timestamp < alertTimeStamp:
            human_time = f"!!!{human_time}"
        results[pool_id]["last_join_exit"] = human_time
    return results


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
        ## Note that pools may be added to the reroute config before their gauges are added.
        ## Note that they may need to be added to the core whitelist if they are  under the AUM limit for rerouting to work
        if pool_id in reroute[chain.value] and reroute[chain.value][pool_id] in incentives.keys():
            # Reroute everything to destination pool
            incentives[reroute[chain.value][pool_id]]['aura_incentives'] += _data['aura_incentives']
            incentives[reroute[chain.value][pool_id]]['bal_incentives'] += _data['bal_incentives']
            # Increase total incentives by aura and bal incentives
            _total_incentives = _data['aura_incentives'] + _data['bal_incentives']
            if _total_incentives != _data['total_incentives']:
                raise Exception(f"Total Incentive from data {_data['total_incentives']} does not match aura + bal incentives {_total_incentives}")
            incentives[reroute[chain.value][pool_id]]['total_incentives'] += _total_incentives
            # Mark source pool incentives as rerouted
            incentives[reroute[chain.value][pool_id]]['reroute_incentives'] += _total_incentives
            # Move earned fees allocations for rerouting logic
            incentives[reroute[chain.value][pool_id]]['earned_fees'] += incentives[pool_id]['earned_fees']
            # Zero out source pool
            incentives[pool_id]['aura_incentives'] = 0
            incentives[pool_id]['bal_incentives'] = 0
            incentives[pool_id]['total_incentives'] = 0
            incentives[pool_id]['reroute_incentives'] -= _total_incentives
            incentives[pool_id]['earned_fees'] = 0
    return incentives
