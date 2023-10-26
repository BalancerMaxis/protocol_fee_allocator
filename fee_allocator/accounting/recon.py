import datetime

import simplejson as json
import os
from decimal import Decimal

from fee_allocator.accounting import PROJECT_ROOT


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
    aura_incentives = sum([x["aura_incentives"] for x in fees.values()])
    bal_incentives = sum([x["bal_incentives"] for x in fees.values()])
    fees_to_dao = sum([x["fees_to_dao"] for x in fees.values()])
    fees_to_vebal = sum([x["fees_to_vebal"] for x in fees.values()])
    delta = all_fees_sum - all_incentives_sum
    # Make delta positive
    if delta < 0:
        delta = -delta
    assert delta < Decimal(0.1), f"Reconciliation failed. Delta: {delta}"

    # Store the summary to json file
    summary = {
        "feesCollected": all_fees_sum,
        "incentivesDistributed": all_incentives_sum,
        "feesNotDistributed": delta,
        "auraIncentives": aura_incentives,
        "balIncentives": bal_incentives,
        "feesToDao": fees_to_dao,
        "feesToVebal": fees_to_vebal,
        "auraIncentivesPct": round(aura_incentives / all_incentives_sum, 4),
        "balIncentivesPct": round(bal_incentives / all_incentives_sum, 4),
        "feesToDaoPct": round(fees_to_dao / all_incentives_sum, 4),
        "feesToVebalPct": round(fees_to_vebal / all_incentives_sum, 4),
        # UNIX timestamp
        "createdAt": int(datetime.datetime.now().timestamp()),
        "periodStart": timestamp_2_weeks_ago,
        "periodEnd": timestamp_now,
    }
    # If everything is 0 - don't store the summary
    if all_incentives_sum == 0 or all_fees_sum == 0:
        return
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
