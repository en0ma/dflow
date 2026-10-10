#!/usr/bin/env python3
"""Read-only batch check of documented candidate ledgers and USDC vaults.
Flags potential fixtures; does not assert a market is tradable.
"""
import base64,json,os,pathlib,urllib.request
pairs=[
("CPy9eaGECdD7W8ZhWdaJ3vhfp2711QLtStRKYGnPAjrx","34B4vfFAj3Yy5RYVo6PonLYnWB6dTWqXznUV74vJgPNp"),
("6xdVnEEjUh4fTAN1hGtsDbcim8CdvwCWvw3xGmNZrPF5","6hMekFWbfmDJkquTQhZfnL245haPyL6MR6qJUT7JDroB"),
("CT91GupQzfM35qyVdb5Rk4NG4AYNoS43ET9cqzdJbtaU","74WKSuo6BM2iKYsdcZzZKACdB9fZRhmLbEKXYSsXrCYj"),
("hQ5abQ1karPbvbPhKLEp3U3Jf1jdNTtp7QEdVvtML5u","BGm7pU57p8wM1uVf2hYcbahFAZDF5nMQXNMpunZrLkbh"),
("EdWBKGV8hKcpyR4Nu1bx3nkG4ScepKa8UWz1HS4bNxhx","FazSpJpU9gtEDskQhtV9t3PtEX35EDsBRdLptq9JgvDj"),
("EocEe9dzW8hSjvcTA9NbQyfamTAQPL7eWeTUBECkm7P3","7tYraATSFTzKJJroZunCfARGfBzznZoFgJ3WRaT3XdJm"),
("6pQTyrpa1i3EaBq1p2LPJr6q6QjqugX7DxqWkzWyVnK5","2Gc3p2Chj2pbnNYkiY8hTjRG9K6qBPEy1FNyC1JD4avq"),
("D6ugpVCWWU78VdRoa6MXkuPEB24b7ceW3sgMCrfTrHYX","8ygFugdckK4kB3KGysN3Fukdrq5KHTPtjFSfBZ7PA6oj"),
]
def b58(b):
 a="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
 n=int.from_bytes(b,"big");s=""
 while n:n,r=divmod(n,58);s=a[r]+s
 return "1"*(len(b)-len(b.lstrip(bytes([0]))))+s
addresses=[k for pair in pairs for k in pair]
body=json.dumps({"jsonrpc":"2.0","id":1,"method":"getMultipleAccounts",
"params":[addresses,{"encoding":"base64","commitment":"finalized"}]}).encode()
req=urllib.request.Request(os.environ["SOLANA_RPC_URL"],data=body,headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=40) as f:result=json.load(f)
if "error" in result:raise RuntimeError("Candidate RPC error (details omitted)")
values=result["result"]["value"]
report=[]
for i,(ledger,vault) in enumerate(pairs):
 lm,va=values[2*i:2*i+2]
 row={"ledger":ledger,"vault":vault,"ledger_exists":lm is not None,"vault_exists":va is not None}
 if lm and va:
  ld=base64.b64decode(lm["data"][0]);vd=base64.b64decode(va["data"][0])
  row.update({"ledger_len":len(ld),"ledger_owner":lm["owner"],
   "status_raw_byte_564":ld[564] if len(ld)>564 else None,
   "vault_len":len(vd),"vault_owner":va["owner"],
   "vault_mint":b58(vd[:32]) if len(vd)>=32 else None,
   "vault_authority":b58(vd[32:64]) if len(vd)>=64 else None,
   "vault_balance":int.from_bytes(vd[64:72],"little") if len(vd)>=72 else None})
  row["relationships_valid"]=(len(ld)==568 and len(vd)==165 and
   lm["owner"]=="pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb" and
   va["owner"]=="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA" and
   row["vault_mint"]=="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and
   row["vault_authority"]==ledger)
 report.append(row)
 print("CANDIDATE",i+1,"ledger",ledger,"status",row.get("status_raw_byte_564"),
 "vault_balance",row.get("vault_balance"),"relationships_valid",row.get("relationships_valid",False))
dest=pathlib.Path("reports/predic-cpi/candidate-market-census.json")
dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps({"note":"Current snapshots; checks do not prove active market or executable quote.","candidates":report},indent=2))
