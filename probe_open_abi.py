#!/usr/bin/env python3
import argparse, base64, json, urllib.parse, urllib.request

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USER = "F6Yt9m6YCM9dazu9XDT57LhZrGaBsYGge2uNJp4s8kM9"
META = "https://dev-prediction-markets-api.dflow.net"
TRADE = "https://dev-quote-api.dflow.net"

def get_json(url):
    req = urllib.request.Request(url, headers={"user-agent":"dflow-open-abi-probe/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def shortvec(buf, off):
    out=0; shift=0
    while True:
        b=buf[off]; off+=1
        out |= (b & 0x7f) << shift
        if not b & 0x80: return out, off
        shift += 7

def extract_open(tx_b64):
    buf=base64.b64decode(tx_b64)
    sigs,off=shortvec(buf,0); off += sigs*64
    if buf[off] & 0x80: off += 1
    off += 3
    nkeys,off=shortvec(buf,off); off += nkeys*32
    off += 32
    nix,off=shortvec(buf,off)
    found=[]
    for _ in range(nix):
        pidx=buf[off]; off+=1
        nacct,off=shortvec(buf,off); accts=list(buf[off:off+nacct]); off+=nacct
        ndata,off=shortvec(buf,off); data=bytes(buf[off:off+ndata]); off+=ndata
        if len(data)==80 and int.from_bytes(data[:8],"little")==64:
            found.append((pidx,accts,data))
    if not found:
        raise RuntimeError("no 80-byte tag-64 instruction found")
    _,_,b=found[0]
    return {
        "hex": b.hex(),
        "opcode_u64": int.from_bytes(b[0:8],"little"),
        "field_8_15_u64": int.from_bytes(b[8:16],"little"),
        "side_ascii": chr(b[16]),
        "byte17": b[17],
        "field_18_19_u16": int.from_bytes(b[18:20],"little"),
        "field_20_21_u16": int.from_bytes(b[20:22],"little"),
        "field_22_23_u16": int.from_bytes(b[22:24],"little"),
        "input_amount_u64": int.from_bytes(b[24:32],"little"),
        "output_amount_u64": int.from_bytes(b[32:40],"little"),
        "field_40_71_hex": b[40:72].hex(),
        "field_72_79_u64": int.from_bytes(b[72:80],"little"),
    }

def choose_market():
    data=get_json(META + "/api/v1/events?withNestedMarkets=true&limit=200")
    for ev in data.get("events",[]):
        for m in ev.get("markets",[]) or []:
            if m.get("status") != "active": continue
            acct=(m.get("accounts") or {}).get(USDC)
            if not acct: continue
            if acct.get("isInitialized") is False: continue
            if acct.get("yesMint") and acct.get("noMint"):
                return {"ticker":m.get("ticker"), **acct}
    raise RuntimeError("no active initialized USDC market found")

def order(output_mint, **kwargs):
    q={
      "inputMint":USDC,
      "outputMint":output_mint,
      "amount":"1000000",
      "userPublicKey":USER,
    }
    q.update({k:str(v) for k,v in kwargs.items() if v is not None})
    url=TRADE + "/order?" + urllib.parse.urlencode(q)
    obj=get_json(url)
    tx=obj.get("transaction")
    if not tx:
        raise RuntimeError("order response had no transaction: "+json.dumps(obj)[:500])
    return {"query":q, "response":{k:obj.get(k) for k in ("inAmount","outAmount","minOutAmount","executionMode","errorCode")}, "open":extract_open(tx)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out",default="reports/open-abi-probe.json"); args=ap.parse_args()
    out={"market":None,"variants":{},"errors":{}}
    try:
        m=choose_market(); out["market"]=m
    except Exception as e:
        out["errors"]["market"]=repr(e)
        open(args.out,"w").write(json.dumps(out,indent=2)); return 0
    variants={
      "yes_s50_pm200": (m["yesMint"], {"slippageBps":50,"predictionMarketSlippageBps":200}),
      "no_s50_pm200": (m["noMint"], {"slippageBps":50,"predictionMarketSlippageBps":200}),
      "yes_s120_pm200": (m["yesMint"], {"slippageBps":120,"predictionMarketSlippageBps":200}),
      "yes_s50_pm500": (m["yesMint"], {"slippageBps":50,"predictionMarketSlippageBps":500}),
      "yes_s50_pm200_fee50": (m["yesMint"], {"slippageBps":50,"predictionMarketSlippageBps":200,"platformFeeScale":50,"referralAccount":USER}),
    }
    for name,(mint,kw) in variants.items():
        try: out["variants"][name]=order(mint,**kw)
        except Exception as e: out["errors"][name]=repr(e)
    open(args.out,"w").write(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
