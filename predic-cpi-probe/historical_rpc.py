#!/usr/bin/env python3
"""Read-only pReDic historical OPEN replay checks against configured RPC.
No transactions are sent and no credentials are logged.
"""
import json, os, sys, urllib.request
RPC=os.environ.get("SOLANA_RPC_URL")
if not RPC: raise SystemExit("SOLANA_RPC_URL missing")
PROGRAM="pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb"
CASES=[
 ("4HG2x8c9XgRBUCjprDo1EVKZfqC6tXziYi3dmmCTEFVbtoEh6C1tW8cV7m4tmZKPFJceT2UeCyTUAo7Goc9fRG5Y",
  "E6RHT33UpybNumSJPxXMiqGCGaEdhn8Y3h2rAUFaTb7"),
 ("4Y9mDkjoX1SkKgx1WTirQvJmecnyVUJvwScuGnWDwXKC3qHABKpLmXpbB7rYsLq2mWaF6Q5p5uLKB8iZyy1Dopea",
  "5wX9x4a8dvS6NyhdDPNCyRrXvMh5TJu48Qc2s37wDWxF"),
]
ALPH="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58decode(s):
 n=0
 for c in s:n=n*58+ALPH.index(c)
 return b"\\x00"*(len(s)-len(s.lstrip("1")))+n.to_bytes((n.bit_length()+7)//8,"big")
def call(method,params):
 body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
 req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=25) as resp: v=json.load(resp)
 if "error" in v:raise RuntimeError("RPC returned an error for "+method+" (details suppressed)")
 return v.get("result")
report=[]
for sig,expected in CASES:
 t=call("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0,"commitment":"confirmed"}])
 if not t: raise RuntimeError("historical transaction not served by RPC")
 message=t["transaction"]["message"]
 keys=[x["pubkey"] if isinstance(x,dict) else x for x in message["accountKeys"]]
 ix_matches=[]
 for ix in message["instructions"]:
  pid=ix.get("programId") or keys[ix["programIdIndex"]]
  if pid!=PROGRAM:continue
  d=b58decode(ix["data"])
  if len(d)==80 and int.from_bytes(d[:8],"little")==64:
   accounts=ix["accounts"]
   accounts=[keys[a] if isinstance(a,int) else a for a in accounts]
   assert len(accounts)==12,"Unexpected account count"
   assert accounts[4]==expected,"Order account mismatch"
   assert accounts[0]==PROGRAM,"Executable slot mismatch"
   assert accounts[7]==accounts[8]==accounts[9],"Signer alias mismatch"
   ix_matches.append({"nonce":int.from_bytes(d[8:16],"little"),
      "side":chr(d[16]),"unknown16":int.from_bytes(d[22:24],"little"),
      "accounts":accounts,
      "transaction_flags":[{"signer":next((x.get("signer") for x in message["accountKeys"] if isinstance(x,dict) and x["pubkey"]==a),None),
          "writable":next((x.get("writable") for x in message["accountKeys"] if isinstance(x,dict) and x["pubkey"]==a),None)} for a in accounts]})
 assert ix_matches,"OPEN not found"
 report.append({"signature_prefix":sig[:12],"slot":t["slot"],"success":t["meta"]["err"] is None,"open":ix_matches})
os.makedirs("reports/predic-cpi",exist_ok=True)
with open("reports/predic-cpi/historical-rpc.json","w") as f:json.dump(report,f,indent=2)
for r in report:
 print("Historical OPEN verified:",r["signature_prefix"],"slot",r["slot"],"success",r["success"])
print("NOTE: Transaction account flags are NOT minimal instruction metas; external CPI untested.")
