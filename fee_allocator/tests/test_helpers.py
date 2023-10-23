from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from fee_allocator.helpers import calculate_aura_vebal_share


def test_calculate_aura_vebal_share(mocker):
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
