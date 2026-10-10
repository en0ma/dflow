#!/usr/bin/env python3
"""Verify the exact deployed ELF on the runner and record executable metadata.
This is NOT a CPI execution test.
"""
import hashlib,json,os, pathlib,struct,sys
p=pathlib.Path("reports/program/predictions.so")
data=p.read_bytes()
assert data[:4]==b"\x7fELF", "wrong ELF magic"
assert len(data)>100_000, "unexpectedly short deployed program"
info=json.loads(pathlib.Path("reports/program/info.json").read_text())
assert info["elfBytes"]==len(data)
assert info["elfOffset"] in (13,45)
assert info["program"]=="pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb"
sha=hashlib.sha256(data).hexdigest()
result={"elf_sha256":sha,"elf_bytes":len(data),
 "last_deployment_slot":info["lastDeploySlot"],
 "program":info["program"],"elf_offset":info["elfOffset"],
 "execution_status":"not_executed"}
out=pathlib.Path("reports/predic-cpi/elf-verification.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2))
print("Recovered ELF verified; size",len(data),"sha256",sha)
print("No CPI has been executed by this check.")
