#!/usr/bin/env python3
import base64, json, os, time, urllib.request
from pathlib import Path

RPC_URL=os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
PROGRAM="pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58d(s):
    n=0
    for ch in s: n=n*58+B58.index(ch)
    raw=n.to_bytes((n.bit_length()+7)//8,"big") if n else b""
    return b"\0"*(len(s)-len(s.lstrip("1")))+raw

def b58e(raw):
    n=int.from_bytes(raw,"big"); out=""
    while n:
        n,r=divmod(n,58); out=B58[r]+out
    return "1"*(len(raw)-len(raw.lstrip(b"\0")))+(out or "")

def rpc(payload):
    req=urllib.request.Request(RPC_URL,data=json.dumps(payload).encode(),headers={"content-type":"application/json","user-agent":"dflow-expiry-probe/1.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.loads(r.read())

def call(method,params):
    x=rpc({"jsonrpc":"2.0","id":1,"method":method,"params":params})
    if "error" in x: raise RuntimeError(x["error"])
    return x.get("result")

def signatures(max_pages=2):
    out=[]; before=None
    for _ in range(max_pages):
        cfg={"limit":1000,"commitment":"finalized"}
        if before: cfg["before"]=before
        page=call("getSignaturesForAddress",[PROGRAM,cfg]) or []
        out+=page
        if len(page)<1000: break
        before=page[-1]["signature"]
    return out

def batch_txs(sigs,batch=5):
    out={}
    for start in range(0,len(sigs),batch):
        chunk=sigs[start:start+batch]
        req=[]
        for i,s in enumerate(chunk):
            req.append({"jsonrpc":"2.0","id":i,"method":"getTransaction","params":[s,{"encoding":"json","commitment":"finalized","maxSupportedTransactionVersion":0}]})
        rows=None
        for attempt in range(7):
            try:
                rows=rpc(req)
                break
            except Exception as e:
                delay=min(2 ** attempt, 16)
                print("batch retry",start,attempt,str(e),"sleep",delay,flush=True)
                time.sleep(delay)
        if rows is not None:
            byid={x.get("id"):x for x in rows}
            for i,sig in enumerate(chunk):
                out[sig]=byid.get(i,{}).get("result")
        print(f"fetched {min(start+batch,len(sigs))}/{len(sigs)}",flush=True)
        time.sleep(0.35)
    return out

def all_ix(tx):
    msg=(tx or {}).get("transaction",{}).get("message",{})
    out=list(msg.get("instructions") or [])
    for g in (tx or {}).get("meta",{}).get("innerInstructions") or []:
        out += g.get("instructions") or []
    return out

def decode(tx):
    events=[]; opens=[]
    for ix in all_ix(tx):
        pidx=ix.get("programIdIndex")
        # json encoding uses indexes, so resolve full key list
        msg=(tx or {}).get("transaction",{}).get("message",{})
        keys=list(msg.get("accountKeys") or [])
        loaded=(tx or {}).get("meta",{}).get("loadedAddresses") or {}
        keys += list(loaded.get("writable") or [])+list(loaded.get("readonly") or [])
        pid=keys[pidx] if isinstance(pidx,int) and pidx<len(keys) else ix.get("programId")
        if pid!=PROGRAM or not isinstance(ix.get("data"),str): continue
        try: b=b58d(ix["data"])
        except: continue
        if len(b)>=48 and int.from_bytes(b[:8],"little")==240 and b[8]==2:
            events.append({"lifecycle":b[9],"userOrder":b58e(b[16:48]),"slippageBps":int.from_bytes(b[10:12],"little"),"len":len(b)})
        if len(b)==80 and int.from_bytes(b[:8],"little")==64:
            opens.append({"u16_16":int.from_bytes(b[22:24],"little"),"side":b[16],"slippageBps":int.from_bytes(b[18:20],"little"),"input":int.from_bytes(b[24:32],"little"),"quotedOut":int.from_bytes(b[32:40],"little"),"hex":b.hex()})
    return events,opens

def main():
    sigmeta=signatures(2)[:1200]
    print("signatures",len(sigmeta),flush=True)
    sigs=[x["signature"] for x in sigmeta]
    txs=batch_txs(sigs)
    opens_by={}; terms=[]; fills=0
    # oldest -> newest
    for m in reversed(sigmeta):
        sig=m["signature"]; tx=txs.get(sig)
        if not tx: continue
        evs,ops=decode(tx)
        slot=tx.get("slot")
        for ev in evs:
            row={"signature":sig,"slot":slot,"blockTime":tx.get("blockTime"),**ev}
            if ev["lifecycle"]==1:
                if ops: row.update(ops[0])
                opens_by[ev["userOrder"]]=row
            elif ev["lifecycle"]==2: fills+=1
            elif ev["lifecycle"] in (3,4): terms.append(row)
    matches=[]
    for t in terms:
        o=opens_by.get(t["userOrder"])
        if not o: continue
        d=t["slot"]-o["slot"]; u=o.get("u16_16")
        matches.append({"userOrder":t["userOrder"],"openSignature":o["signature"],"terminalSignature":t["signature"],"openSlot":o["slot"],"terminalSlot":t["slot"],"lifecycle":t["lifecycle"],"slotDelta":d,"u16_16":u,"deltaMinusU16":d-u if isinstance(u,int) else None,"side":o.get("side"),"slippageBps":o.get("slippageBps"),"input":o.get("input"),"quotedOut":o.get("quotedOut")})
    out={"signatures":len(sigmeta),"txs":sum(v is not None for v in txs.values()),"opens":len(opens_by),"fills":fills,"terminals":len(terms),"matches":matches}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/expiry-probe.json").write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
