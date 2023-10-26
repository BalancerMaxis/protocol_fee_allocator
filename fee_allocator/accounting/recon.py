import simplejson as json
import os
from decimal import Decimal

from fee_allocator.accounting import PROJECT_ROOT


def recon_and_validate(
    fees: dict,
    fees_to_distribute: dict,
    recon_output: str,
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
    assert delta < Decimal(0.01), f"Reconciliation failed. Delta: {delta}"

    # Store the summary to json file
    summary = {
        "feesCollected": all_fees_sum,
        "incentivesDistributed": all_incentives_sum,
        "feesNotDistributed": delta,
        "auraIncentives": aura_incentives,
        "balIncentives": bal_incentives,
        "feesToDao": fees_to_dao,
        "feesToVebal": fees_to_vebal,
    }

    recon_file_name = os.path.join(
        PROJECT_ROOT, f"fee_allocator/summaries/{recon_output}"
    )
    # Dump to json file
    with open(recon_file_name, "w") as f:
        json.dump(summary, f, use_decimal=True)
