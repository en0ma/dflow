#!/usr/bin/env python3
"""Fetch a server-constructed DFlow order for offline inspection; NEVER submit/sign.
Requires a current outcome mint and a PUBLIC wallet key. Do not use private keys.
The returned transaction is an opaque quote artifact, not automatically CPI-safe.
"""
import argparse,json,os,pathlib,urllib.parse,urllib.request,urllib.error
p=argparse.ArgumentParser()
p.add_argument("--output-mint",required=True,help="Currently active prediction outcome mint")
p.add_argument("--wallet",required=True,help="Public key only; no secret keys")
p.add_argument("--amount",type=int,required=True,help="USDC base units")
p.add_argument("--slippage-bps",type=int,default=100)
p.add_argument("--api-base",default="https://dev-quote-api.dflow.net")
p.add_argument("--output",default="reports/predic-cpi/quoted-order.json")
args=p.parse_args()
if args.amount<=0 or not 0<=args.slippage_bps<=10000: p.error("Invalid amount or slippage")
if args.api_base not in ("https://dev-quote-api.dflow.net","https://quote-api.dflow.net"):
 p.error("Unsupported API host")
params={"inputMint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "outputMint":args.output_mint,"amount":str(args.amount),
        "userPublicKey":args.wallet,"slippageBps":str(args.slippage_bps)}
url=args.api_base+"/order?"+urllib.parse.urlencode(params)
headers={"Accept":"application/json"}
if os.environ.get("DFLOW_API_KEY"):headers["x-api-key"]=os.environ["DFLOW_API_KEY"]
try:
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as r:
  result=json.load(r)
except urllib.error.HTTPError as exc:
 print("Quote request rejected: HTTP",exc.code,"(no funds moved)")
 raise SystemExit(2)
dest=pathlib.Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps({"request":params,"response":result},indent=2))
tx=result.get("transaction") if isinstance(result,dict) else None
print("Quote response saved:",dest)
print("Built transaction supplied:",isinstance(tx,str) and bool(tx))
print("Quote response code:",result.get("code") if isinstance(result,dict) else None)
print("No transaction signed, simulated, or submitted.")
