#!/usr/bin/env python3
"""Check whether the local runtime OPEN fixture is coherent with successful on-chain OPENs.
Read-only, deterministic: mismatches are evidence, not values to brute-force.
"""
import json,pathlib
base=pathlib.Path("reports/predic-cpi")
historical=json.loads((base/"historical-construction.json").read_text())["transactions"]
fixture=json.loads(pathlib.Path("predic-cpi-runtime-smoke/tests/fixtures/live_accounts.json").read_text())
live=[a["address"] for a in fixture["accounts"]]
payload=bytes.fromhex(fixture["historical_open_hex"])
assert len(payload)==80
report=[]
for tx in historical:
 for case in tx["cases"]:
  h=[a["address"] for a in case["accounts"]]
  checks={
   "same_market_ledger":live[2]==h[2],
   "same_market_vault":live[3]==h[3],
   "same_input_mint":live[5]==h[5],
   "same_source_token_account":live[6]==h[6],
   "same_wallet":live[7]==h[7],
   "same_event_authority":live[1]==h[1],
   "same_payload":payload.hex()==case["instruction_hex"],
   "same_nonce_as_runtime_test":case["nonce"]==123456789,
  }
  report.append({"signature_prefix":tx["signature"][:12],
                 "slot":tx["slot"],"checks":checks,
                 "coherent_historical_replay":all(checks.values())})
  print("FIXTURE_COHERENCE",tx["signature"][:12],
        "matches",sum(checks.values()),"of",len(checks),
        "mismatch_fields",",".join(k for k,v in checks.items() if not v))
dest=base/"fixture-coherence.json"
dest.write_text(json.dumps({"note":"Current snapshots and a replaced wallet/nonce are NOT an archival replay.","results":report},indent=2))
assert not any(x["coherent_historical_replay"] for x in report), (
 "The fixture unexpectedly matches a historical replay; reassess test assumptions"
)
print("Confirmed: existing synthetic runtime fixture is not a byte-and-account exact historical replay.")
