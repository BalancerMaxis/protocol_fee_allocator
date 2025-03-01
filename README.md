# protocol_fee_allocator

## 1. Review Mimic PR

As a result from https://github.com/BalancerMaxis/protocol_fee_allocator/blob/main/.github/workflows/get_mimic_report.yaml, a PR will appear bi-weekly Thursday ~9am UTC. It merges the newest fees json into `fee_allocator/fees_collected/fees_***.json`. Checklist is posted automatically in the PR.

## 2. Run the Allocator with New Mimic Data

Manual for now via dispatch: https://github.com/BalancerMaxis/protocol_fee_allocator/blob/main/.github/workflows/collect_fees_v2.yaml

Can be automated to trigger on successful merge of step 1. above (https://github.com/BalancerMaxis/protocol_fee_allocator/issues/330)

## 3. Review Fee Allocations PR

Checklist is included in the PR

## 4. Load the Payload

Assuming the results check out, load the payload into the [mainnnet fee sweeper multisig](https://app.safe.global/balances?safe=eth:0x7c68c42De679ffB0f16216154C996C354cF1161B). Run tenderly and make sure it sims, and that the total USDC out matches everything else. Do a quick check, we can review more later, and sign it/load it.

## 5. Prepare a `multisig-ops` Payload for Review

Checkout/open the `BalancerMaxis/multisig-ops` github repo. Pull the newest main and create a new branch from it.

Tritium tends to use fees-yyyy-mm-dd with the end date, but anything is fine.

copy the artifacts generated by the fee_allocation PR above (in this repo) into the `MaxiOps/feeDistribution/YYYY-MM-DD` folder where the date is the end date used to run the action.

there should be 3 input artifacts in the following subdirectories of the fee_allocator directory: `fees_colected`, `allocations`, `tx_builder/transactions`. note that fees collected is the json file you built above.

Commit and push the 3 files, and generate a PR. Here is an [example PR](https://github.com/BalancerMaxis/multisig-ops/pull/785) that may be easier to copy than following the instructions listed here.

Make sure you include the following in the PR Description:

- A link to the payload in the safe to sign
- A link to the tab on the sheet that you prepaired
- A link to the fee allocator PR where everything was generated

Wait about 5-10 minutes for the report to finish, which should generate another view of what is paid where. Once this is done, ask Sigops to check everything, and if you have the energy recheck what you signed against the sheet and the report.

Note that allocator PR's don't have a great review process right now so it is unclear when/how to merge this PR. In the end, what is reviewed is in msig ops so this PR can be merged once the tx is executed, or even at the end of this process if you've checked everything well.
