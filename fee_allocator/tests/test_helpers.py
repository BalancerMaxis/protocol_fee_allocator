from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from fee_allocator.helpers import calculate_aura_vebal_share
from fee_allocator.helpers import fetch_all_pools_info


def test_calculate_aura_vebal_share():
    total_supply = 100_000_000e18
    balance = 50_000_000e18
    web3 = MagicMock(
        eth=MagicMock(
            contract=MagicMock(
                return_value=MagicMock(
                    functions=MagicMock(
                        totalSupply=MagicMock(
                            return_value=MagicMock(
                                call=MagicMock(return_value=total_supply)
                            )
                        ),
                        balanceOf=MagicMock(
                            return_value=MagicMock(call=MagicMock(return_value=balance))
                        ),
                    )
                )
            )
        )
    )
    share = calculate_aura_vebal_share(web3, 0)
    # Assert approx equal
    assert share == pytest.approx(Decimal(balance / total_supply))


def test_fetch_all_pools_info(mocker):
    # Patch gql client
    mocker.patch(
        "fee_allocator.helpers.Client",
        return_value=MagicMock(
            execute=MagicMock(
                return_value={
                    "veBalGetVotingList": [
                        {
                            "id": "0x01536b22ea06e4a315e3daaf05a12683ed4dc14c0000000000000000000005fc",
                            "address": "0x01536b22ea06e4a315e3daaf05a12683ed4dc14c",
                            "chain": "MAINNET",
                            "type": "PHANTOM_STABLE",
                            "symbol": "e-cs-kp-usd",
                            "gauge": {
                                "address": "0x3c8502e60ebd1e036e1d3906fc34e9616218b6e5",
                                "isKilled": False,
                                "relativeWeightCap": "0.02",
                                "addedTimestamp": 1699356239,
                                "childGaugeAddress": None,
                            },
                            "tokens": [
                                {
                                    "address": "0x571f54d23cdf2211c83e9a0cbd92aca36c48fa02",
                                    "symbol": "paUSD",
                                    "weight": None,
                                },
                                {
                                    "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                                    "symbol": "USDC",
                                    "weight": None,
                                },
                                {
                                    "address": "0xaf4ce7cd4f8891ecf1799878c3e9a35b8be57e09",
                                    "symbol": "wUSK",
                                    "weight": None,
                                },
                            ],
                        }
                    ],
                }
            )
        ),
    )

    all_pools = fetch_all_pools_info()
    assert len(all_pools) == 1
    assert all_pools[0]["type"] == "PHANTOM_STABLE"
    assert all_pools[0]["chain"] == "MAINNET"
