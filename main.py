import argparse
import json
import os
from datetime import datetime, timedelta
import pytz

from dotenv import load_dotenv
from munch import Munch
from web3 import Web3
from web3.middleware import geth_poa_middleware

from fee_allocator.accounting.fee_pipeline import run_fees
from fee_allocator.accounting.recon import generate_and_save_input_csv
from fee_allocator.accounting.recon import recon_and_validate
from fee_allocator.accounting.settings import Chains
from fee_allocator.helpers import fetch_all_pools_info
from fee_allocator.tx_builder.tx_builder import generate_payload

def get_last_thursday_odd_week():
    # Get the current UTC date and time
    current_datetime = datetime.utcnow().replace(tzinfo=pytz.utc)

    # Calculate the difference between the current weekday and Thursday (where Monday is 0 and Sunday is 6)
    days_until_thursday = (current_datetime.weekday() - 3) % 7

    # Check if the current week is odd
    is_odd_week = current_datetime.isocalendar()[1] % 2 == 1

    # Calculate the final timedelta to go back to the last Thursday on an odd week
    weeks_until_next_odd_week = 0 if is_odd_week else 1
    timedelta_to_last_thursday = timedelta(days=days_until_thursday + 7 * weeks_until_next_odd_week)

    # Calculate the timestamp of the last Thursday at 00:00 UTC
    last_thursday_timestamp = (current_datetime - timedelta_to_last_thursday).replace(hour=0, minute=0, second=0, microsecond=0)

    return last_thursday_timestamp.timestamp()

now = datetime.utcnow()
DELTA = 1000
# TS_NOW = 1704326400
# TS_2_WEEKS_AGO = 1703116800
TS_NOW = int(now.timestamp()) - DELTA
TS_2_WEEKS_AGO = get_last_thursday_odd_week().timestamp()

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
    print(f"\n\nRunning  from timestamps {ts_in_the_past} to {ts_now}")
    output_file_name = parser.parse_args().output_file_name or "current_fees.csv"
    fees_file_name = parser.parse_args().fees_file_name or "current_fees_collected.json"
    fees_path = os.path.join(ROOT, "fee_allocator", "fees_collected", fees_file_name)
    with open(fees_path) as f:
        fees_to_distribute = json.load(f)
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
    web3_instances = Munch()
    web3_instances[Chains.MAINNET.value] = Web3(
        Web3.HTTPProvider(os.environ["ETHNODEURL"])
    )
    poly_web3 = Web3(Web3.HTTPProvider(os.environ["POLYNODEURL"]))
    poly_web3.middleware_onion.inject(geth_poa_middleware, layer=0)
    web3_instances[Chains.POLYGON.value] = poly_web3
    web3_instances[Chains.ARBITRUM.value] = Web3(
        Web3.HTTPProvider(os.environ["ARBNODEURL"])
    )
    web3_instances[Chains.GNOSIS.value] = Web3(
        Web3.HTTPProvider(
            os.environ["GNOSISNODEURL"],
            request_kwargs={
                "headers": {"Authorization": f"Bearer {os.environ['GNOSIS_API_KEY']}"}
            },
        )
    )
    web3_instances[Chains.BASE.value] = Web3(
        Web3.HTTPProvider(os.environ["BASENODEURL"])
    )
    web3_instances[Chains.AVALANCHE.value] = Web3(
        Web3.HTTPProvider(os.environ["AVALANCHENODEURL"])
    )
    web3_instances[Chains.ZKEVM.value] = Web3(
        Web3.HTTPProvider(os.environ["POLYZKEVMNODEURL"])
    )
    collected_fees = run_fees(
        web3_instances, ts_now, ts_in_the_past, output_file_name, fees_to_distribute,
        mapped_pools_info,
    )
    recon_and_validate(collected_fees, fees_to_distribute, ts_now, ts_in_the_past)
    csvfile = generate_and_save_input_csv(collected_fees, ts_now, mapped_pools_info)
    if output_file_name != "current_fees.csv":
        generate_payload(web3_instances["mainnet"], csvfile)

if __name__ == "__main__":
    main()
