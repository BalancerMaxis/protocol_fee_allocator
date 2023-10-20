import datetime
import os

from dotenv import load_dotenv
from munch import Munch
from web3 import Web3
from web3.middleware import geth_poa_middleware
from fee_allocator.accounting.fee_pipeline import run_fees
from fee_allocator.accounting.settings import Chains


def main() -> None:
    """
    This function is used only to initialize the web3 instances and run main function
    """
    load_dotenv()
    web3_instances = Munch()
    web3_instances[Chains.MAINNET.value] = Web3(Web3.HTTPProvider(os.environ["ETHNODEURL"]))
    poly_web3 = Web3(Web3.HTTPProvider(os.environ["POLYNODEURL"]))
    poly_web3.middleware_onion.inject(geth_poa_middleware, layer=0)
    web3_instances[Chains.POLYGON.value] = poly_web3
    web3_instances[Chains.ARBITRUM.value] = Web3(
        Web3.HTTPProvider(os.environ["ARBNODEURL"])
    )
    web3_instances[Chains.GNOSIS.value] = Web3(
        Web3.HTTPProvider(os.environ["GNOSISNODEURL"], request_kwargs={
            "headers": {
                "Authorization": f"Bearer {os.environ['GNOSIS_API_KEY']}"
            }
        })
    )
    web3_instances[Chains.BASE.value] = Web3(Web3.HTTPProvider(os.environ["BASENODEURL"]))
    web3_instances[Chains.AVALANCHE.value] = Web3(
        Web3.HTTPProvider(os.environ["AVALANCHENODEURL"])
    )
    timestamp_now = 1697148000
    timestamp_2_weeks_ago = timestamp_now - (2 * 7 * 24 * 60 * 60)

    run_fees(web3_instances, timestamp_now, timestamp_2_weeks_ago)


if __name__ == '__main__':
    main()
