#!/usr/bin/env python3
"""Snapshot public currently-live historical OPEN accounts for offline ProgramTest.
Missing/closed accounts are explicit; never fabricate historical state.
"""
import base64,json,os,pathlib,urllib.request
src=json.loads(pathlib.Path("reports/predic-cpi/historical-rpc.json").read_text())
addresses=src[-1]["open"][0]["accounts"]
url=os.environ["SOLANA_RPC_URL"]
payload=json.dumps({"jsonrpc":"2.0","id":1,"method":"getMultipleAccounts",
 "params":[addresses,{"encoding":"base64","commitment":"finalized"}]}).encode()
req=urllib.request.Request(url,data=payload,headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=30) as f:response=json.load(f)
if "error" in response:raise RuntimeError("RPC account snapshot failed")
out={"snapshot_type":"current_finalized_not_historical",
     "accounts":[{"index":i,"address":address,"value":value} for i,(address,value)
                 in enumerate(zip(addresses,response["result"]["value"]))]}
p=pathlib.Path("predic-cpi-runtime-smoke/tests/fixtures/live_accounts.json")
p.parent.mkdir(parents=True,exist_ok=True)
# Get full successful OPEN instruction bytes from the known historical transaction.
from historical_rpc import b58decode, CASES, PROGRAM
# historical_rpc.py already validated and fetched the same transaction.
tx_payload=json.dumps({"jsonrpc":"2.0","id":2,"method":"getTransaction",
 "params":[CASES[-1][0],{"encoding":"jsonParsed","maxSupportedTransactionVersion":0,"commitment":"confirmed"}]}).encode()
with urllib.request.urlopen(urllib.request.Request(url,data=tx_payload,headers={"Content-Type":"application/json"}),timeout=30) as f:
 transaction=json.load(f)["result"]
message=transaction["transaction"]["message"]
data_candidates=[b58decode(ix["data"]) for ix in message["instructions"]
                 if ix.get("programId")==PROGRAM and "data" in ix]
matching=[d for d in data_candidates if len(d)==80 and int.from_bytes(d[:8],"little")==64]
if len(matching)!=1:raise RuntimeError("Exactly one historical OPEN payload required")
out["historical_open_hex"]=matching[0].hex()
p.write_text(json.dumps(out,indent=2))
(p.parent/"historical_open.hex").write_text(out["historical_open_hex"])
print("Recorded live account records for",sum(x["value"] is not None for x in out["accounts"]),"of",len(addresses),"positions")
print("Index 1 and 4 may be closed; do not treat these as historical snapshots")
