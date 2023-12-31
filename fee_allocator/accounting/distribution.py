from decimal import Decimal
from typing import Dict

from fee_allocator.accounting.settings import Chains


def calc_and_split_incentives(
        fees: Dict, chain: str, fees_to_distribute: Decimal,
        min_aura_incentive: Decimal, dao_share: Decimal, vebal_share: Decimal,
        aura_vebal_share: Decimal
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
        bal_incentives_pct = _bal_incentives / _total_incentives
        # If aura incentives percentage is less than aura_vebal_share, we need to increase bal incentives
        if aura_incentives_pct >= aura_vebal_share:
            # Calculate how much we need to increase bal incentives
            bal_incentives_to_increase = round(
                _total_incentives * (aura_incentives_pct - aura_vebal_share), 2)
            # Increase bal incentives
            incentives[pool_id]['bal_incentives'] += bal_incentives_to_increase
            # Decrease aura incentives
            incentives[pool_id]['aura_incentives'] -= bal_incentives_to_increase
        # If aura incentives percentage is more than aura_vebal_share, we need to increase aura incentives
        else:
            # Calculate how much we need to increase aura incentives
            aura_incentives_to_increase = round(
                _total_incentives * (aura_vebal_share - aura_incentives_pct), 2)
            # Increase aura incentives
            incentives[pool_id]['aura_incentives'] += aura_incentives_to_increase
            # Decrease bal incentives
            incentives[pool_id]['bal_incentives'] -= aura_incentives_to_increase
    return incentives
