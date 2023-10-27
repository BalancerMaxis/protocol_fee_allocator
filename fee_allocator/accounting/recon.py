import datetime

import pandas as pd
import simplejson as json
import os
from decimal import Decimal

from web3 import Web3

from fee_allocator.accounting import PROJECT_ROOT
from fee_allocator.helpers import fetch_all_pools_info


def recon_and_validate(
    fees: dict,
    fees_to_distribute: dict,
    timestamp_now: int,
    timestamp_2_weeks_ago: int,
) -> None:
    """
    Recon fees collected from the fee pipeline. Store the summary to json file
    and raise exceptions if validation fails
    """
    # Move to separate function
    all_fees_sum = Decimal(round(sum(fees_to_distribute.values()), 2))
    all_incentives_sum = sum(
        [
            sum(
                [
                    x["fees_to_vebal"],
                    x["fees_to_dao"],
                    x["aura_incentives"],
                    x["bal_incentives"],
                ]
            )
            for x in fees.values()
        ]
    )
    # If everything is 0 - don't store the summary
    if all_incentives_sum == 0 or all_fees_sum == 0:
        return
    aura_incentives = sum([x["aura_incentives"] for x in fees.values()])
    bal_incentives = sum([x["bal_incentives"] for x in fees.values()])
    fees_to_dao = sum([x["fees_to_dao"] for x in fees.values()])
    fees_to_vebal = sum([x["fees_to_vebal"] for x in fees.values()])
    delta = all_fees_sum - all_incentives_sum
    # Make delta positive
    if delta < 0:
        delta = -delta
    assert delta < Decimal(0.1), f"Reconciliation failed. Delta: {delta}"

    # Make sure all SUM(pct) == 1
    assert (
        round(
            aura_incentives / all_incentives_sum
            + bal_incentives / all_incentives_sum
            + fees_to_dao / all_incentives_sum
            + fees_to_vebal / all_incentives_sum,
            4,
        )
        == 1
    ), "Reconciliation failed. Sum of percentages is not equal to 1"

    # Store the summary to json file
    summary = {
        "feesCollected": round(all_fees_sum, 2),
        "incentivesDistributed": round(all_incentives_sum, 2),
        "feesNotDistributed": round(delta, 2),
        "auraIncentives": round(aura_incentives, 2),
        "balIncentives": round(bal_incentives, 2),
        "feesToDao": round(fees_to_dao, 2),
        "feesToVebal": round(fees_to_vebal, 2),
        "auraIncentivesPct": round(aura_incentives / all_incentives_sum, 4),
        "balIncentivesPct": round(bal_incentives / all_incentives_sum, 4),
        "feesToDaoPct": round(fees_to_dao / all_incentives_sum, 4),
        "feesToVebalPct": round(fees_to_vebal / all_incentives_sum, 4),
        # UNIX timestamp
        "createdAt": int(datetime.datetime.now().timestamp()),
        "periodStart": timestamp_2_weeks_ago,
        "periodEnd": timestamp_now,
    }
    recon_file_name = os.path.join(PROJECT_ROOT, "fee_allocator/summaries/recon.json")
    # Append new summary to the file
    with open(recon_file_name) as f:
        existing_data = json.load(f)

    # Make sure that the summary is not already in the file
    already_in_file = False
    for item in existing_data:
        if (
            item["periodStart"] == summary["periodStart"]
            and item["periodEnd"] == summary["periodEnd"]
        ):
            # Don't append the summary if it's already in the file
            already_in_file = True
            break
    if already_in_file:
        return

    existing_data.append(summary)
    with open(recon_file_name, "w") as f:
        json.dump(existing_data, f, use_decimal=True, indent=2)


def generate_and_save_input_csv(fees: dict, period_ends: int) -> None:
    """
    Function that generates and saves csv in format:
    target_root_gauge,platform,amount_of_incentives
    """
    all_incentives_sum = sum(
        [
            sum(
                [
                    x["fees_to_vebal"],
                    x["fees_to_dao"],
                    x["aura_incentives"],
                    x["bal_incentives"],
                ]
            )
            for x in fees.values()
        ]
    )
    # Don't generate csv if there are no incentives
    if all_incentives_sum == 0:
        return
    # First, fetch all gauges info:
    pools_info = fetch_all_pools_info()
    # Then map pool_id to root gauge address
    mapped_pools_info = {}
    for pool in pools_info:
        mapped_pools_info[pool["id"]] = Web3.to_checksum_address(
            pool["gauge"]["address"]
        )
    output = []
    for pool_id, fee_item in fees.items():
        # Aura incentives
        output.append(
            {
                "target": mapped_pools_info[pool_id],
                "platform": "aura",
                "amount": round(fee_item["aura_incentives"], 2),
            }
        )
        # Bal incentives
        output.append(
            {
                "target": mapped_pools_info[pool_id],
                "platform": "balancer",
                "amount": round(fee_item["bal_incentives"], 2),
            }
        )
    # Add DAO share to the output
    dao_share = sum([x["fees_to_dao"] for x in fees.values()])
    output.append(
        {
            "target": "0x10A19e7eE7d7F8a52822f6817de8ea18204F2e4f",  # DAO msig
            "platform": "payment",
            "amount": round(dao_share, 2),
        }
    )
    # Convert to dataframe and save to csv
    df = pd.DataFrame(output)

    # Generate datetime from timestamp
    datetime_file_header = datetime.datetime.fromtimestamp(period_ends).date()
    df.to_csv(
        os.path.join(
            PROJECT_ROOT,
            f"fee_allocator/allocations/output_for_msig/{datetime_file_header}.csv",
        ),
        index=False,
    )
