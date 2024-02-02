import argparse
import json
import os
from datetime import datetime

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

DELTA = 1000
# TS_NOW = 1704326400
# TS_2_WEEKS_AGO = 1703116800
TS_NOW = int(datetime.now().timestamp()) - DELTA
TS_2_WEEKS_AGO = 1705536000

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
    generate_payload(web3_instances["mainnet"], csvfile)


if __name__ == "__main__":
    main()
