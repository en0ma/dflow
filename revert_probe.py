#!/usr/bin/env python3
import os,json,time,urllib.request
from pathlib import Path
RPC=os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
PAIRS=[
("62a4QxHEAxtfKbpdQggfbngQVbE5zzXu4YSqJEJzLJY8u3U7eHhK42qzbtRnNjfBTd3qpiLfnrB3k52drhAFU18z","PRiC2FWZwJUdyiQ159yVXgnHuzGz3vKQfjuWMGMEM8PbJ9i6vKpGWP4tFKNWJveUSqMFocG2SKxu77AG7umRXyX"),
("5wF9PTrGeizKrv8jnofKubcpTVMXWXH438ThYyV4Jqmq21k4DfRg8zkaHvg56QyMdSr1UEjbCwpXGgriZpiexmRV","4ui4ytB1LamFfAR1rtFFrVuT4njNYGeRKJ2d3QryfvAwApuiHu3rdeSSuUVpu6KgcgBpsuUAbb7XhwsiHwNWVQTK"),
("4CY55sJF2gmFWFbeYWcmxPuxC7Pr2gW11g1T9m9DhH4MdqperywYVne2McDjPSXKq8tRQtCvpFNDP6C5b11bXQ5L","4EvAnufHBpuE8cuWTXAAkjsjN9FtK5cqnqBMBT9SHET22wNcvqJyDgksZ5aLWy36VCRNqNEt4GpQziKn4YZaB5jL"),
("TCPa1QMaiVYUgTfqzq4QsYKjcNj6xYPoh31bXYhViE2Wc8Jc8EaX3TTSPKmyyYKq7ng4dfCPihLWJffUsrurPib","3ucLfybsTKVDmdXJgrTpmT941GGn8XQWFVMPVXwbgPmMPUpPzR12m9mJkmdr4ZhkaDj82EJ5oecaGKFUXDbtNz6h")
]
def rpc(method,params):
 req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(),headers={"content-type":"application/json"})
 for n in range(6):
  try:
   with urllib.request.urlopen(req,timeout=35) as f:x=json.load(f)
   if "error" in x:raise Exception(x["error"])
   return x.get("result")
  except Exception as e:
   if n==5:raise
   time.sleep(min(2**n,12))
def get(sig,encoding="jsonParsed"):
 return rpc("getTransaction",[sig,{"encoding":encoding,"maxSupportedTransactionVersion":0,"commitment":"finalized"}])
def summarize(sig,tx):
 if not tx:return {"signature":sig,"error":"null"}
 msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
 instr=list(msg.get("instructions") or [])
 for g in meta.get("innerInstructions") or []:
  for i in g.get("instructions") or []:instr.append(i)
 tokenix=[]
 for ix in instr:
  parsed=ix.get("parsed")
  if isinstance(parsed,dict) and parsed.get("type") in ["transfer","transferChecked","closeAccount","burn","burnChecked","mintTo","mintToChecked"]:
   tokenix.append({"programId":ix.get("programId"),"type":parsed["type"],"info":parsed.get("info")})
 return {"signature":sig,"slot":tx.get("slot"),"blockTime":tx.get("blockTime"),"err":meta.get("err"),"logs":meta.get("logMessages"),"tokenInstructions":tokenix,"tokenBalancesPre":meta.get("preTokenBalances"),"tokenBalancesPost":meta.get("postTokenBalances"),"outerInstructions":msg.get("instructions"),"innerInstructions":meta.get("innerInstructions"),"keys":msg.get("accountKeys")}
def main():
 print("[rpc] SOLANA_RPC_URL="+("SET" if os.getenv("SOLANA_RPC_URL") else "NOT SET"),flush=True)
 out=[]
 for index,(op,term) in enumerate(PAIRS,1):
  print(f"[pair] {index}/4 OPEN {op[:12]} REVERT {term[:12]}",flush=True)
  row={}
  for label,sig in [("open",op),("revert",term)]:
   try:row[label]=summarize(sig,get(sig))
   except Exception as e:row[label]={"error":str(e)}
  if isinstance(row["open"].get("slot"),int) and isinstance(row["revert"].get("slot"),int):
   row["slotDelta"]=row["revert"]["slot"]-row["open"]["slot"]
  out.append(row)
 Path("reports").mkdir(exist_ok=True)
 Path("reports/revert-pairs.json").write_text(json.dumps(out,indent=2))
 print("[pair] complete",flush=True)
if __name__=="__main__": main()
