#!/usr/bin/env python3
"""Inspect live OPEN-market prerequisites before interpreting rejected CPI calls.
Read-only analysis of current snapshots; status mapping is not assumed.
"""
import base64,json,pathlib
p=pathlib.Path("predic-cpi-runtime-smoke/tests/fixtures/live_accounts.json")
data=json.loads(p.read_text())
entries={x["index"]:x for x in data["accounts"]}
def blob(index):
 a=entries[index]["value"]
 return base64.b64decode(a["data"][0]) if a else None
market=blob(2); vault=blob(3); mint=blob(5); user=blob(6)
if not all(x is not None for x in (market,vault,mint,user)):
 raise RuntimeError("Essential OPEN account snapshot unavailable")
if (len(market),len(vault),len(mint),len(user))!=(568,165,82,165):
 raise RuntimeError("Unexpected market/token/mint byte lengths")
def b58(v):
 alphabet="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
 n=int.from_bytes(v,"big")
 s=""
 while n:n,r=divmod(n,58);s=alphabet[r]+s
 return "1"*(len(v)-len(v.lstrip(b"\\x00")))+s
market_key=entries[2]["address"]
mint_key=entries[5]["address"]
wallet=entries[7]["address"]
facts={
 "market_status_raw_byte_564":market[564],
 "market_ledger_owner":entries[2]["value"]["owner"],
 "vault_mint":b58(vault[:32]),
 "vault_token_authority":b58(vault[32:64]),
 "user_token_mint":b58(user[:32]),
 "user_token_authority":b58(user[32:64]),
 "vault_balance":int.from_bytes(vault[64:72],"little"),
 "user_token_balance":int.from_bytes(user[64:72],"little"),
 "expected_market_ledger":market_key,
 "expected_mint":mint_key,
 "historical_wallet":wallet,
 "vault_mint_matches":b58(vault[:32])==mint_key,
 "vault_authority_matches_ledger":b58(vault[32:64])==market_key,
 "user_token_mint_matches":b58(user[:32])==mint_key,
 "user_token_owner_matches_historical_wallet":b58(user[32:64])==wallet
}
out=pathlib.Path("reports/predic-cpi/current-market-prerequisites.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({"snapshot":"current, not historical","facts":facts},indent=2))
for k,v in facts.items():print("MARKET_PRECHECK",k,v)
print("Raw market status is not evidence of an open market without a verified status mapping.")
