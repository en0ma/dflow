#!/usr/bin/env python3
"""Read-only owner and layout census for known historical OPEN account metas.
RPC only; never prints RPC URL or credentials. Closed accounts are reported missing.
"""
import json,os,urllib.request,pathlib,base64,hashlib
RPC=os.environ["SOLANA_RPC_URL"]
INPUT=pathlib.Path("reports/predic-cpi/historical-rpc.json")
def rpc(method,params):
 payload=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
 req=urllib.request.Request(RPC,data=payload,headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=30) as f: obj=json.load(f)
 if "error" in obj: raise RuntimeError(f"{method}: RPC error (details omitted)")
 return obj["result"]
samples=json.loads(INPUT.read_text())
allkeys=list(dict.fromkeys(a for x in samples for o in x["open"] for a in o["accounts"]))
value=rpc("getMultipleAccounts",[allkeys,{"encoding":"base64","commitment":"finalized"}])["value"]
lookup={}
for k,v in zip(allkeys,value):
 if v is None:
  lookup[k]={"exists_now":False}
 else:
  raw=base64.b64decode(v["data"][0])
  lookup[k]={"exists_now":True,"owner":v["owner"],"executable":v["executable"],"lamports":v["lamports"],"data_len":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
report=[]
for x in samples:
 for o in x["open"]:
  report.append({"signature_prefix":x["signature_prefix"],"slot":x["slot"],
  "accounts":[{"index":i,"address":k,**lookup[k]} for i,k in enumerate(o["accounts"])]})
dest=pathlib.Path("reports/predic-cpi/account-census.json")
dest.write_text(json.dumps(report,indent=2))
for record in report:
 print("Historical OPEN",record["signature_prefix"])
 for a in record["accounts"]:
  print(f"  {a['index']:2} owner={a.get('owner','CLOSED')} len={a.get('data_len','-')} executable={a.get('executable','-')}")
print("Caution: these are CURRENT owner/layout snapshots, not historical at transaction slot.")
