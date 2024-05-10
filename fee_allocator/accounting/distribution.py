import math
import datetime
from decimal import Decimal
from typing import Dict
from typing import List
from typing import Optional

from bal_addresses import BalPoolsGauges
from fee_allocator.accounting.settings import Chains


# TODO remove existing existing_aura_bribs from function.  Perhaps find another way to count aura votes already placed
#   when considering routing bribs away from Aura
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
        aura_incentives = round(total_incentive * aura_vebal_share, 4)


        # Distribute precisely now, redistribution will happen later.
        bal_incentives = round(total_incentive - aura_incentives, 4)
        fees_to_dao = round(pool_share * fees_to_distribute * dao_share, 4)
        fees_to_vebal = round(pool_share * fees_to_distribute * vebal_share, 4)
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
    Redistribute all incentives away from pools that are < min_vote_incentive amount
    Insure that all pools receive at least min_aura_incentive, if not, distribute to BAL
    Maintain the AURA/BAL split systemwide by redistributing value from the BAL to AURA market on the largest pools
        in order to compensate for pools that surredered value to the BAL market.
    """
    # Collect pools that received < min_vote_incentive_amount
    pools_to_redistribute = {}
    for pool_id, _data in incentives.items():
        if _data['total_incentives'] < Decimal(min_incentive_amount):
            pools_to_redistribute[pool_id] = _data
    # Collect pools that received > min_vote_incentive_amount
    pools_to_receive = {}
    for pool_id, _data in incentives.items():
        if _data['total_incentives'] >= Decimal(min_incentive_amount):
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
            to_receive = round(incentives_to_redistribute * pool_weight, 4)
            to_receive_aura = round(incentives_to_redistribute_aura * pool_weight, 4)
            to_receive_bal = round(incentives_to_redistribute_bal * pool_weight, 4)
            incentives[pool_id_to_receive]['aura_incentives'] += to_receive_aura
            incentives[pool_id_to_receive]['bal_incentives'] += to_receive_bal
            incentives[pool_id_to_receive]['total_incentives'] += to_receive
            incentives[pool_id_to_receive]['redirected_incentives'] += to_receive
    ## Now after everything is done, we need to make sure that all pools have at least min_aura_incentive
    ## if not we need to redistribute all aura_incentives to bal_incentives for that pool and keep track of how much has been reallocated
    debt_to_aura_market = 0
    for pool_id, _data in incentives.items():
        if _data['aura_incentives'] < min_aura_incentive:
            # Calculate incentives to redistribute
            incentives_to_redistribute = _data['aura_incentives']
            # Set incentives to redistribute to 0
            incentives[pool_id]['aura_incentives'] = 0
            incentives[pool_id]['bal_incentives'] += incentives_to_redistribute
            debt_to_aura_market += incentives_to_redistribute

    if debt_to_aura_market:
        ## Find how many pools ever could be over min_aura_incentive
        pools_over_aura_min = [pool_id for pool_id, _data in incentives.items() if _data['total_incentives'] >= min_aura_incentive]
        num_pools_over_min = len(pools_over_aura_min)
        amount_per_pool =  round(debt_to_aura_market / pools_over_aura_min, 4)
        # Create an array of the top 6 pools that received the most total_incentives
        # Distribute  1/6th of incentives_taken_from_aura_market to each of the top 6 pools, while subtracting the same amount from bal_incentives
        for pool_id, _data in pools_over_aura_min:
            if _data['total_incentives'] > 0:
                # TODO:  Need to think about edge cases here and watch them.
                incentives[pool_id]['aura_incentives'] += min(amount_per_pool, _data['bal_incentives'])
                incentives[pool_id]['bal_incentives'] -= min(amount_per_pool, _data['bal_incentives'])
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
