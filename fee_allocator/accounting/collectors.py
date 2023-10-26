from collections import defaultdict
from decimal import Decimal
from typing import Dict

from fee_allocator.accounting.settings import Chains
from fee_allocator.helpers import fetch_token_price_balgql_timerange


def collect_fee_info(
    pools: list[str],
    chain: Chains,
    pools_now: list[dict],
    pools_shifted: list[Dict],
    start_ts: int,
    end_ts: int,
    bpt_twap_prices: Dict[str, Dict],
) -> Dict[str, Dict]:
    """
    Collects fee info for all pools in the list.
    Returns dictionary with pool id as key and fee info as value
    """
    fees = {}
    token_fees = defaultdict(list)
    for pool in pools:
        current_fees_snapshots = [x for x in pools_now if x["pool"]["id"] == pool]
        current_fees_snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
        fees_2_weeks_ago = [x for x in pools_shifted if x["pool"]["id"] == pool]
        fees_2_weeks_ago.sort(key=lambda x: x["timestamp"], reverse=True)
        # If pools doesn't have current fees it means it was not created yet, so we skip it
        if not current_fees_snapshots:
            continue
        pool_snapshot_now = current_fees_snapshots[0]
        pool_snapshot_2_weeks_ago = (
            fees_2_weeks_ago[0] if len(fees_2_weeks_ago) > 0 else {}
        )
        # Now we need to collect token fee info. Let's start with BPT tokens,
        # which is Balancer pool token. Notice that totalProtocolFeePaidInBPT can be null,
        # so we need to check for that
        bpt_token_fee = 0
        token_fees_in_usd = 0
        bpt_price_usd = bpt_twap_prices[chain.value][pool] or 0
        if pool_snapshot_now["pool"]["totalProtocolFeePaidInBPT"] is not None:
            if pool_snapshot_2_weeks_ago:
                bpt_token_fee = float(
                    pool_snapshot_now["pool"]["totalProtocolFeePaidInBPT"]
                ) - float(
                    pool_snapshot_2_weeks_ago["pool"]["totalProtocolFeePaidInBPT"] or 0
                )  # If 2 weeks ago is null, set to 0
            else:
                bpt_token_fee = float(
                    pool_snapshot_now["pool"]["totalProtocolFeePaidInBPT"]
                )
        else:
            # Collect fee info about fees paid in pool tokens.
            # Pool tokens fee info is in pool.tokens dictionary. This will be separate dictionary
            for token_data in pool_snapshot_now["pool"]["tokens"]:
                if pool_snapshot_2_weeks_ago:
                    token_data_2_weeks_ago = [
                        t
                        for t in pool_snapshot_2_weeks_ago["pool"]["tokens"]
                        if t["address"] == token_data["address"]
                    ][0]
                    token_fee = float(token_data.get("paidProtocolFees", None)) - float(
                        token_data_2_weeks_ago.get("paidProtocolFees", None) or 0
                    )
                else:
                    token_fee = float(token_data.get("paidProtocolFees", None))
                # Get twap token price from Balancer API
                token_price = (
                    fetch_token_price_balgql_timerange(
                        token_data["address"], chain.value, start_ts, end_ts
                    )
                    or 0
                )
                token_fees_in_usd += Decimal(token_fee) * Decimal(token_price)
        fees[pool_snapshot_now["pool"]["id"]] = {
            "symbol": pool_snapshot_now["pool"]["symbol"],
            "pool_addr": pool_snapshot_now["pool"]["address"],
            "bpt_token_fee": round(bpt_token_fee, 2),
            # One of two fields below should always be 0 because
            # fees are taken in either BPT or pool tokens
            "bpt_token_fee_in_usd": round(Decimal(bpt_token_fee) * bpt_price_usd, 2),
            "token_fees_in_usd": round(token_fees_in_usd, 2),
            "chain": chain.value,
            "token_fees": token_fees[pool_snapshot_now["pool"]["symbol"]],
        }
    return fees
