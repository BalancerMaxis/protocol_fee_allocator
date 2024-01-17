import json
import os
from decimal import Decimal
from typing import Optional

from web3 import Web3


def get_price(address: str) -> Optional[Decimal]:
    """
    Try to get price from config. Address can be in whatever format, this function will try to convert it to checksum
    or to .lower() format
    """
    project_root = os.path.dirname(__file__)
    pricing_config = json.load(open(os.path.join(project_root, "pricing.json")))
    price = pricing_config.get(address)
    if price is None:
        price = pricing_config.get(address.lower())

    if price is None:
        price = pricing_config.get(Web3.to_checksum_address(address))
    return price
