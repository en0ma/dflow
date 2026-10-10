#!/usr/bin/env python3
"""Audit successful historical OPEN construction without replay or mutation.
Outputs byte-exact instructions, account-role relationships, and explicitly
labels transaction-wide privileges as upper bounds (not minimum CPI metas).
"""
import json, os, pathlib, urllib.request
from historical_rpc import CASES, PROGRAM, b58decode
RPC=os.environ["SOLANA_RPC_URL"]
def rpc(method,params):
 body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
 req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=30) as resp: data=json.load(resp)
 if "error" in data: raise RuntimeError(f"{method} RPC error (details suppressed)")
 return data["result"]
records=[]
for signature, expected_order in CASES:
 tx=rpc("getTransaction",[signature,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0,"commitment":"confirmed"}])
 if not tx or tx["meta"]["err"] is not None: raise RuntimeError("successful historical transaction unavailable")
 msg=tx["transaction"]["message"]
 keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
 flags={k["pubkey"]:{"signer":k.get("signer"),"writable":k.get("writable")}
        for k in msg["accountKeys"] if isinstance(k,dict)}
 candidates=[]
 for ins in msg["instructions"]:
  pid=ins.get("programId") or keys[ins["programIdIndex"]]
  if pid!=PROGRAM or "data" not in ins:continue
  payload=b58decode(ins["data"])
  if len(payload)!=80 or int.from_bytes(payload[:8],"little")!=64:continue
  addresses=[keys[i] if isinstance(i,int) else i for i in ins["accounts"]]
  if len(addresses)!=12 or addresses[4]!=expected_order:raise RuntimeError("Account/order invariant mismatch")
  if addresses[7]!=addresses[8] or addresses[8]!=addresses[9]:raise RuntimeError("Authority aliases unexpected")
  nonce=int.from_bytes(payload[8:16],"little")
  candidates.append({"instruction_hex":payload.hex(),
    "nonce":nonce,"side":chr(payload[16]),
    "input_amount":int.from_bytes(payload[24:32],"little"),
    "quoted_output":int.from_bytes(payload[32:40],"little"),
    "accounts":[{"index":i,"address":addr,"transaction_flags":flags.get(addr,{})}
       for i,addr in enumerate(addresses)],
    "account_1_equals_documented_event_authority":
       addresses[1]=="ATZQPakBrumxMrSyuEmrt6NcxBbTR1Ucs99dnPFpBUuM",
    "data_length":len(payload)})
 if not candidates:raise RuntimeError("No matching historical OPEN found")
 records.append({"signature":signature,"slot":tx["slot"],"cases":candidates})
out=pathlib.Path("reports/predic-cpi/historical-construction.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({"note":"Transaction flags are not minimum CPI privileges; no live OPEN attempted.","transactions":records},indent=2))
for r in records:
 for x in r["cases"]:
  print("CONSTRUCTION",r["signature"][:12],
        "event_authority_match",x["account_1_equals_documented_event_authority"],
        "input",x["input_amount"],"output",x["quoted_output"],
        "account1",x["accounts"][1]["address"],
        "side",x["side"])
print("Wrote",out)
