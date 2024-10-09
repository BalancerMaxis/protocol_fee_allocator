import datetime
import os
from decimal import Decimal
from typing import Dict
from typing import Optional

import pandas as pd
import simplejson as json

from fee_allocator.accounting import PROJECT_ROOT


def recon_and_validate(
    fees: dict,
    fees_to_distribute: dict,
    timestamp_now: int,
    timestamp_2_weeks_ago: int,
    target_aura_vebal_share: Decimal,
) -> None:
    """
    Recon fees collected from the fee pipeline. Store the summary to json file
    and raise exceptions if validation fails
    """
    # Move to separate function
    all_fees_sum = Decimal(round(sum(fees_to_distribute.values()), 4))
    all_incentives_sum = round(
        sum(
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
        ),
        4,
    )
    # If everything is 0 - don't store the summary
    if all_incentives_sum == 0 or all_fees_sum == 0:
        return
    delta = all_fees_sum - all_incentives_sum
    abs_delta = abs(delta)

    aura_incentives = 0
    bal_incentives = 0
    fees_to_dao = 0
    fees_to_vebal = 0
    # Sum up all incentives and verify there are no negative numbers.
    for fee_info in fees.values():
        assert (
            fee_info["aura_incentives"] >= 0
        ), f"Recon Failed: {fee_info['pool_id???']} Aura incentives of {fee_info['aura_incentives']}should be >= 0"
        aura_incentives += fee_info["aura_incentives"]
        assert (
            fee_info["bal_incentives"] >= 0
        ), f"Recon Failed: {fee_info['pool_id???']} Balancer incentives of {fee_info['bal_incentives']}should be >= 0"
        bal_incentives += fee_info["bal_incentives"]
        assert (
            fee_info["fees_to_dao"] >= 0
        ), f"Recon Failed: {fee_info['pool_id???']} Balancer incentives of {fee_info['fees_to_dao']}should be >= 0"
        fees_to_dao += fee_info["fees_to_dao"]
        assert (
            fee_info["fees_to_vebal"] >= 0
        ), f"Recon Failed: {fee_info['pool_id???']} Balancer incentives of {fee_info['fees_to_vebal']}should be >= 0"
        fees_to_vebal += fee_info["fees_to_vebal"]
        assert (
            fee_info["total_incentives"] >= 0
        ), f"Recon Failed: {fee_info['pool_id???']} Balancer incentives of {fee_info['total_incentives']}should be >= 0"

    assert abs_delta < Decimal(0.15), f"Reconciliation failed. Delta: {delta}"
    print(f"During recon found a delta of {delta}")
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
    # calvulate aura veBAL share
    aura_vebal_share = round(aura_incentives / (aura_incentives + bal_incentives), 4)
    if target_aura_vebal_share:
        # check that aura_vebal_share is within 5% of target
        assert (
            abs(aura_vebal_share - target_aura_vebal_share) < 0.05
        ), f"Reconciliation failed. Aura veBAL share is not within 5% of target. Aura veBAL share: {aura_vebal_share}, Target: {target_aura_vebal_share}"

    # Store the summary to json file
    summary = {
        "feesCollected": round(all_fees_sum, 2),
        "incentivesDistributed": round(all_incentives_sum, 2),
        "feesNotDistributed": round(delta, 2),
        "auraIncentives": round(aura_incentives, 2),
        "balIncentives": round(bal_incentives, 2),
        "feesToDao": round(fees_to_dao, 2),
        "feesToVebal": round(fees_to_vebal, 2),
        "auravebalShare": round(aura_vebal_share, 2),
        "auraIncentivesPct": round(aura_incentives / all_incentives_sum, 4),
        "auraIncentivesPctTotal": round(
            aura_incentives / (aura_incentives + bal_incentives), 4
        ),
        "balIncentivesPct": round(bal_incentives / all_incentives_sum, 4),
        "balIncentivesPctTotal": round(
            bal_incentives / (aura_incentives + bal_incentives), 4
        ),
        "feesToDaoPct": round(fees_to_dao / all_incentives_sum, 4),
        "feesToVebalPct": round(
            fees_to_vebal / all_incentives_sum, 4
        ),  # UNIX timestamp
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


def generate_and_save_input_csv(
    fees: dict, period_ends: int, mapped_pools_info: Dict, fees_to_gyro: Decimal
) -> str:
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

    output = []
    for pool_id, fee_item in fees.items():
        # Aura incentives
        output.append(
            {
                "target": mapped_pools_info[pool_id],
                "platform": "aura",
                "amount": round(fee_item["aura_incentives"], 4),
            }
        )
        # Bal incentives
        output.append(
            {
                "target": mapped_pools_info[pool_id],
                "platform": "balancer",
                "amount": round(fee_item["bal_incentives"], 4),
            }
        )
    # Add DAO share to the output
    dao_share = sum([x["fees_to_dao"] for x in fees.values()])
    output.append(
        {
            "target": "0x10A19e7eE7d7F8a52822f6817de8ea18204F2e4f",  # DAO msig
            "platform": "payment",
            "amount": round(dao_share, 4),
        }
    )
    # Add gyro share to the output
    output.append(
        {
            "target": "",  # gyro fee recipient
            "platform": "payment",
            "amount": round(fees_to_gyro, 4),
        }
    )
    # Convert to dataframe and save to csv
    df = pd.DataFrame(output)

    # Generate datetime from timestamp
    datetime_file_header = datetime.datetime.fromtimestamp(period_ends).date()
    filename = f"fee_allocator/allocations/output_for_msig/{datetime_file_header}.csv"

    df.to_csv(
        os.path.join(
            PROJECT_ROOT,
            filename,
        ),
        index=False,
    )
    return filename
