import json
from datetime import datetime, timedelta

import requests


BASE_URL = "https://api.mimic.fi/public/summary/"
ENV_ID = "0xd28bd4e036df02abce84bc34ede2a63abcefa0567ff2d923f01c24633262c7f8"
CHAIN_ID = "1"


def get_report(start_date, end_date):
    response = requests.get(
        f"{BASE_URL}{ENV_ID}",
        params={
            "envId": ENV_ID,
            "chainId": CHAIN_ID,
            "startDate": start_date,
            "endDate": end_date,
        },
    )
    return response.json()


if __name__ == "__main__":
    # run this every other thursday after the end of an epoch
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    epoch_start = today - timedelta(days=14)

    report = get_report(yesterday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    with open(
        f"fee_allocator/fees_collected/fees_{epoch_start.strftime("%Y-%m-%d")}_{yesterday.strftime("%Y-%m-%d")}.json", "w"
    ) as f:
        json.dump(report["depositors"], f, indent=2)
