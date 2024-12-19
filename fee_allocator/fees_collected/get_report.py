import json
from datetime import datetime, timedelta

import requests


BASE_URL = "https://api.mimic.fi/public/summary/"
ENV_ID = "0xd28bd4e036df02abce84bc34ede2a63abcefa0567ff2d923f01c24633262c7f8"
CHAIN_ID = "1"


def get_report(start_date, end_date):
    # docs: https://mimic-fi.notion.site/Balancer-API-explanation-1289958dbf4d80beb76ad13462898fee
    response = requests.get(
        f"{BASE_URL}{ENV_ID}",
        params={
            "envId": ENV_ID,
            "chainId": CHAIN_ID,
            "startDate": start_date,
            "endDate": end_date,
        },
    )
    response.raise_for_status()
    # breakpoint()
    report = response.json()["depositors"]
    total = 0
    for chain, amount in report.items():
        report[chain] = int(amount)
        total += int(amount)
    if total > 0:
        return report
    else:
        raise ValueError("Sum of collected fees is not > 0")


if __name__ == "__main__":
    # run this every other thursday after the end of an epoch
    today = datetime.now()

    if bool(int(today.strftime("%W")) % 2):
        # week number is uneven; there should be a new report

        yesterday = today - timedelta(days=1)
        epoch_start = today - timedelta(days=14)

        report = get_report(yesterday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        with open(
            f"fee_allocator/fees_collected/fees_{epoch_start.strftime('%Y-%m-%d')}_{today.strftime('%Y-%m-%d')}.json",
            "w",
        ) as f:
            json.dump(report, f, indent=2)
