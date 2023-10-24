import argparse
import os

from dotenv import load_dotenv
from munch import Munch
from web3 import Web3
from web3.middleware import geth_poa_middleware

from fee_allocator.accounting.fee_pipeline import run_fees
from fee_allocator.accounting.settings import Chains

# TS_NOW = 1697148000
# TS_2_WEEKS_AGO = TS_NOW - (2 * 7 * 24 * 60 * 60)
# TODO: Should inject current timestamp here
TS_NOW = 1698070408
TS_2_WEEKS_AGO = 1697148000


parser = argparse.ArgumentParser()
parser.add_argument("--ts_now", help="Current timestamp", type=int, required=False)
parser.add_argument(
    "--ts_in_the_past", help="Timestamp in the past", type=int, required=False
)


def main() -> None:
    """
    This function is used only to initialize the web3 instances and run main function
    """
    # Get from input params or use default
    ts_now = parser.parse_args().ts_now or TS_NOW
    ts_in_the_past = parser.parse_args().ts_in_the_past or TS_2_WEEKS_AGO
    load_dotenv()
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

    run_fees(
        web3_instances,
        ts_now,
        ts_in_the_past,
        "current_fees.csv",
        "current_fees_collected.json",
    )


if __name__ == "__main__":
    main()
