import argparse
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
import pytz

from dotenv import load_dotenv
from web3 import Web3
from bal_tools import Web3RpcByChain

from fee_allocator.accounting.fee_pipeline import run_fees
from fee_allocator.accounting.recon import generate_and_save_input_csv
from fee_allocator.accounting.recon import recon_and_validate
from fee_allocator.accounting.settings import Chains
from fee_allocator.helpers import fetch_all_pools_info
from fee_allocator.tx_builder.tx_builder import generate_payload
from fee_allocator.helpers import get_block_by_ts
from fee_allocator.helpers import calculate_aura_vebal_share


DRPC_KEY = os.getenv("DRPC_KEY")


def get_last_thursday_odd_week():
    # Use the current UTC date and time
    current_datetime = datetime.utcnow().replace(tzinfo=pytz.utc)

    # Calculate the difference between the current weekday and Thursday (where Monday is 0 and Sunday is 6)
    days_since_thursday = (current_datetime.weekday() - 3) % 7

    # Calculate the date of the most recent Thursday
    most_recent_thursday = current_datetime - timedelta(days=days_since_thursday)

    # Check if the week of the most recent Thursday is odd
    is_odd_week = most_recent_thursday.isocalendar()[1] % 2 == 1

    # If it's not an odd week or we are exactly on Thursday but need to check if the week before was odd
    if not is_odd_week or (
        days_since_thursday == 0
        and (most_recent_thursday - timedelta(weeks=1)).isocalendar()[1] % 2 == 1
    ):
        # Go back one more week if it's not an odd week
        most_recent_thursday -= timedelta(weeks=1)

    # Ensure the Thursday chosen is in an odd week
    if most_recent_thursday.isocalendar()[1] % 2 == 0:
        most_recent_thursday -= timedelta(weeks=1)

    # Calculate the timestamp of the last Thursday at 00:00 UTC
    last_thursday_odd_utc = most_recent_thursday.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return last_thursday_odd_utc


now = datetime.utcnow()
DELTA = 7200  # delay to deal with slow subgraphs
# TS_NOW = 1704326400
# TS_2_WEEKS_AGO = 1703116800
TS_NOW = int(now.timestamp()) - DELTA
TS_2_WEEKS_AGO = int(get_last_thursday_odd_week().timestamp())

parser = argparse.ArgumentParser()
parser.add_argument("--ts_now", help="Current timestamp", type=int, required=False)
parser.add_argument(
    "--ts_in_the_past", help="Timestamp in the past", type=int, required=False
)
parser.add_argument(
    "--output_file_name", help="Output file name", type=str, required=False
)
parser.add_argument("--fees_file_name", help="Fees file name", type=str, required=False)

ROOT = os.path.dirname(__file__)


def main() -> None:
    """
    This function is used only to initialize the web3 instances and run main function
    """
    load_dotenv()
    # Get from input params or use default
    ts_now = parser.parse_args().ts_now or TS_NOW
    ts_in_the_past = parser.parse_args().ts_in_the_past or TS_2_WEEKS_AGO
    print(
        f"\n\n\n------\nRunning  from timestamps {ts_in_the_past} to {ts_now}\n------\n\n\n"
    )
    output_file_name = parser.parse_args().output_file_name or "current_fees.csv"
    fees_file_name = parser.parse_args().fees_file_name or "current_fees_collected.json"
    fees_path = f"fee_allocator/fees_collected/{fees_file_name}"
    # If WEI, translate to float in order to handle mimic imports for now

    with open(fees_path) as f:
        fees_to_distribute = json.load(f)
    if type(fees_to_distribute["mainnet"]) == int:
        fees_to_distribute = {
            k: float(Decimal(v) / Decimal(1e6)) for k, v in fees_to_distribute.items()
        }
    pools_info = fetch_all_pools_info()
    # Then map pool_id to root gauge address
    mapped_pools_info = {}

    for pool in pools_info:
        # Check if the gauge is not killed
        if pool["gauge"]["isKilled"]:
            print(f'{pool["id"]} gauge:{pool["gauge"]["address"]} is killed, skipping')
            continue
        mapped_pools_info[pool["id"]] = Web3.to_checksum_address(
            pool["gauge"]["address"]
        )
    web3_instances = Web3RpcByChain(DRPC_KEY)

    collected_fees = run_fees(
        web3_instances,
        ts_now,
        ts_in_the_past,
        output_file_name,
        fees_to_distribute,
        mapped_pools_info,
    )
    _target_mainnet_block = get_block_by_ts(ts_now, Chains.MAINNET.value)
    target_aura_vebal_share = calculate_aura_vebal_share(
        web3_instances["mainnet"], _target_mainnet_block
    )
    recon_and_validate(
        collected_fees,
        fees_to_distribute,
        ts_now,
        ts_in_the_past,
        target_aura_vebal_share,
    )
    csvfile = generate_and_save_input_csv(collected_fees, ts_now, mapped_pools_info)
    if output_file_name != "current_fees.csv":
        generate_payload(web3_instances["mainnet"], csvfile)


if __name__ == "__main__":
    main()
