#!/usr/bin/env python3
import base64, json, urllib.parse, urllib.request
from pathlib import Path

META="https://dev-prediction-markets-api.dflow.net"
TRADE="https://dev-quote-api.dflow.net"
USER="F6Yt9m6YCM9dazu9XDT57LhZrGaBsYGge2uNJp4s8kM9"
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
FEE_ACCOUNT="3rK93MHEXP2qx5yKFr2VJx7uBiN21Monp2GfX6x6tmwx"

def get_json(url):
    req=urllib.request.Request(url, headers={"user-agent":"dflow-abi-probe/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read())

def shortvec(buf, off):
    v=0; shift=0
    while True:
        b=buf[off]; off+=1
        v |= (b & 0x7f) << shift
        if not b & 0x80: return v, off
        shift += 7

def b58(b):
    A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n=int.from_bytes(b,"big")
    s=""
    while n:
        n,r=divmod(n,58); s=A[r]+s
    pad=len(b)-len(b.lstrip(b"\0"))
    return "1"*pad + (s or ("" if pad else "1"))

def parse_tx(raw):
    off=0
    nsig,off=shortvec(raw,off); off += nsig*64
    version=None
    if raw[off] & 0x80:
        version=raw[off]&0x7f; off+=1
    header=raw[off:off+3]; off+=3
    nkeys,off=shortvec(raw,off)
    keys=[]
    for _ in range(nkeys):
        keys.append(b58(raw[off:off+32])); off+=32
    off += 32
    nix,off=shortvec(raw,off)
    ixs=[]
    for i in range(nix):
        pididx=raw[off]; off+=1
        na,off=shortvec(raw,off)
        accts=list(raw[off:off+na]); off+=na
        nd,off=shortvec(raw,off)
        data=raw[off:off+nd]; off+=nd
        pid=keys[pididx] if pididx < len(keys) else None
        ixs.append({"index":i,"programId":pid,"programIdIndex":pididx,"accounts":accts,"data":data})
    return {"version":version,"keys":keys,"instructions":ixs}

def decode_open(d):
    if len(d)!=80 or int.from_bytes(d[:8],"little")!=64:
        return None
    return {
      "hex":d.hex(),
      "opcode":int.from_bytes(d[0:8],"little"),
      "orderIdCandidate":int.from_bytes(d[8:16],"little"),
      "sideByte":d[16],
      "sideAscii": chr(d[16]) if 32 <= d[16] < 127 else None,
      "byte17":d[17],
      "u16_18":int.from_bytes(d[18:20],"little"),
      "u16_20":int.from_bytes(d[20:22],"little"),
      "u16_22":int.from_bytes(d[22:24],"little"),
      "inputAmount":int.from_bytes(d[24:32],"little"),
      "quotedOutAmount":int.from_bytes(d[32:40],"little"),
      "pubkey40_71":b58(d[40:72]) if any(d[40:72]) else None,
      "u64_72":int.from_bytes(d[72:80],"little"),
    }

markets=get_json(META+"/api/v1/markets?status=active&limit=50").get("markets",[])
chosen=None
for m in markets:
    accounts=m.get("accounts") or {}
    acct=accounts.get(USDC)
    if acct and acct.get("yesMint"):
        chosen={"ticker":m.get("ticker"),"yesMint":acct["yesMint"],"noMint":acct.get("noMint")}
        break
if not chosen:
    raise SystemExit("no active USDC prediction market found")

variants=[
 ("base50", {"slippageBps":"50"}),
 ("slip100", {"slippageBps":"100"}),
 ("slip250", {"slippageBps":"250"}),
 ("auto", {"slippageBps":"auto"}),
 ("fee50", {"slippageBps":"50","platformFeeBps":"50","feeAccount":FEE_ACCOUNT}),
 ("fee120", {"slippageBps":"50","platformFeeBps":"120","feeAccount":FEE_ACCOUNT}),
]
out={"market":chosen,"variants":[]}
for name,extra in variants:
    q={"inputMint":USDC,"outputMint":chosen["yesMint"],"amount":"1000000","userPublicKey":USER,**extra}
    url=TRADE+"/order?"+urllib.parse.urlencode(q)
    item={"name":name,"params":q}
    try:
        j=get_json(url)
        item["responseSummary"]={k:j.get(k) for k in ("inAmount","outAmount","minOutAmount","executionMode","slippageBps","errorCode","msg") if k in j}
        tx64=j.get("transaction")
        if tx64:
            tx=parse_tx(base64.b64decode(tx64))
            opens=[]
            for ix in tx["instructions"]:
                dec=decode_open(ix["data"])
                if dec:
                    dec["programId"]=ix["programId"]
                    dec["instructionIndex"]=ix["index"]
                    opens.append(dec)
            item["openInstructions"]=opens
            item["staticPrograms"]=[k for k in tx["keys"] if k in ("pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb","DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH")]
        else:
            item["response"]=j
    except Exception as e:
        item["error"]=repr(e)
    out["variants"].append(item)

Path("reports").mkdir(exist_ok=True)
Path("reports/api-probe.json").write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
