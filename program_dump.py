#!/usr/bin/env python3
import base64, json, os, struct, urllib.request
from pathlib import Path

RPC=os.environ["SOLANA_RPC_URL"]
PROGRAM="pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58e(raw):
    n=int.from_bytes(raw,"big"); out=""
    while n:
        n,r=divmod(n,58); out=B58[r]+out
    return "1"*(len(raw)-len(raw.lstrip(b"\0")))+(out or "")

def call(method,params):
    p=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req=urllib.request.Request(RPC,data=p,headers={"content-type":"application/json","user-agent":"dflow-program-dump/1.0"})
    with urllib.request.urlopen(req,timeout=90) as r:
        body=json.loads(r.read())
    if "error" in body: raise RuntimeError(body["error"])
    return body["result"]

def account(addr):
    r=call("getAccountInfo",[addr,{"encoding":"base64","commitment":"finalized"}])
    v=r["value"]
    if v is None: raise RuntimeError("missing account "+addr)
    return v,base64.b64decode(v["data"][0])

def main():
    out=Path("reports/program"); out.mkdir(parents=True,exist_ok=True)
    pmeta,pdata=account(PROGRAM)
    if len(pdata)<36: raise RuntimeError("unexpected program account length")
    disc=struct.unpack_from("<I",pdata,0)[0]
    programdata=b58e(pdata[4:36])
    dmeta,ddata=account(programdata)
    ddisc=struct.unpack_from("<I",ddata,0)[0]
    slot=struct.unpack_from("<Q",ddata,4)[0]
    opt=struct.unpack_from("<I",ddata,12)[0]
    off=16
    authority=None
    if opt:
        authority=b58e(ddata[off:off+32]); off+=32
    elf=ddata[off:]
    (out/"program-account.bin").write_bytes(pdata)
    (out/"programdata-account.bin").write_bytes(ddata)
    (out/"predictions.so").write_bytes(elf)
    info={
      "program":PROGRAM,
      "programOwner":pmeta["owner"],
      "programExecutable":pmeta["executable"],
      "programStateDiscriminant":disc,
      "programData":programdata,
      "programDataOwner":dmeta["owner"],
      "programDataStateDiscriminant":ddisc,
      "lastDeploySlot":slot,
      "upgradeAuthority":authority,
      "programDataBytes":len(ddata),
      "elfOffset":off,
      "elfBytes":len(elf),
      "elfMagic":elf[:4].hex(),
    }
    (out/"info.json").write_text(json.dumps(info,indent=2))
    print(json.dumps(info,indent=2))
if __name__=="__main__": main()
