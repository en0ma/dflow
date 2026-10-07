#!/usr/bin/env python3
"""
Solana outcome-token forensic collector.

Goals:
- prove whether configured DFlow/Kalshi YES/NO mint addresses exist on-chain
- identify SPL Token vs Token-2022 ownership
- report mint/freeze authorities, decimals, supply, extensions
- locate the oldest signature visible to the RPC for each account
- decode initialization, MintTo, Burn and related token instructions
- show the outer program responsible for token-program CPIs
- decode explicitly supplied evidence transactions
- emit machine-readable JSON and a human-readable Markdown report

No third-party Python packages are required.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "SPL Token",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022",
}
KNOWN_PROGRAMS = {
    "11111111111111111111111111111111": "System Program",
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token Program",
    **TOKEN_PROGRAMS,
}

INTERESTING_TOKEN_TYPES = {
    "initializeMint",
    "initializeMint2",
    "mintTo",
    "mintToChecked",
    "burn",
    "burnChecked",
    "setAuthority",
    "closeAccount",
    "transfer",
    "transferChecked",
}


class Rpc:
    def __init__(self, url: str, timeout: int = 45):
        self.url = url
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self._id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params,
        }).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"content-type": "application/json", "user-agent": "dflow-forensics/1.0"},
            method="POST",
        )
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read())
                if "error" in body:
                    err = body["error"]
                    # Common public-RPC rate limiting.
                    if err.get("code") in (-32005, 429) and attempt < 5:
                        time.sleep(2 ** attempt)
                        continue
                    raise RuntimeError(f"{method}: RPC error: {err}")
                return body.get("result")
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                if attempt == 5:
                    raise RuntimeError(f"{method}: {exc}") from exc
                time.sleep(2 ** attempt)
        raise AssertionError("unreachable")


def get_account(rpc: Rpc, address: str) -> dict[str, Any]:
    result = rpc.call("getAccountInfo", [
        address,
        {"encoding": "jsonParsed", "commitment": "finalized"},
    ])
    value = result.get("value") if result else None
    if value is None:
        return {"exists": False, "address": address}

    owner = value.get("owner")
    data = value.get("data")
    parsed = data.get("parsed") if isinstance(data, dict) else None
    out: dict[str, Any] = {
        "exists": True,
        "address": address,
        "owner": owner,
        "ownerName": KNOWN_PROGRAMS.get(owner),
        "lamports": value.get("lamports"),
        "executable": value.get("executable"),
        "space": value.get("space"),
    }
    if parsed:
        out["parsedType"] = parsed.get("type")
        out["program"] = data.get("program")
        out["info"] = parsed.get("info")
    else:
        out["dataEncoding"] = data[1] if isinstance(data, list) and len(data) > 1 else None
        out["dataLengthBase64"] = len(data[0]) if isinstance(data, list) and data else None
    return out


def signatures_for_address(rpc: Rpc, address: str, max_pages: int) -> tuple[list[dict[str, Any]], bool]:
    all_sigs: list[dict[str, Any]] = []
    before = None
    exhausted = False
    for _ in range(max_pages):
        cfg: dict[str, Any] = {"limit": 1000, "commitment": "finalized"}
        if before:
            cfg["before"] = before
        page = rpc.call("getSignaturesForAddress", [address, cfg]) or []
        if not page:
            exhausted = True
            break
        all_sigs.extend(page)
        before = page[-1]["signature"]
        if len(page) < 1000:
            exhausted = True
            break
    return all_sigs, exhausted



def find_user_open_candidates(rpc: Rpc, wallet: str, usdc_account: str, before_signature: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    cfg: dict[str, Any] = {"limit": limit, "commitment": "finalized"}
    if before_signature:
        cfg["before"] = before_signature
    sigs = rpc.call("getSignaturesForAddress", [wallet, cfg]) or []
    out = []
    for meta in sigs:
        tx = get_transaction(rpc, meta["signature"])
        if tx is None:
            continue
        keys = account_keys(tx)
        if wallet not in keys:
            continue
        # Wallet must be a signer in accountKeys.
        signer = False
        for k in tx.get("transaction", {}).get("message", {}).get("accountKeys", []):
            if isinstance(k, dict) and k.get("pubkey") == wallet and k.get("signer"):
                signer = True
                break
        if not signer:
            continue
        summary = summarize_transaction(meta["signature"], tx)
        # Prefer transactions touching the user's USDC account and a DFlow program.
        touches_usdc = usdc_account in keys
        dflow_programs = [p["address"] for p in summary.get("programIds", []) if p.get("address") in (
            "pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb",
            "DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH",
        )]
        if touches_usdc and dflow_programs:
            out.append({
                "signature": meta["signature"],
                "slot": tx.get("slot"),
                "blockTime": tx.get("blockTime"),
                "programs": dflow_programs,
                "outerInstructions": summary.get("outerInstructions"),
                "preTokenBalances": summary.get("preTokenBalances"),
                "postTokenBalances": summary.get("postTokenBalances"),
            })
    return out

def get_transaction_resilient(rpc: Rpc, signature: str, raw: bool = False, attempts: int = 12) -> dict[str, Any] | None:
    fn = get_transaction_raw if raw else get_transaction
    last = None
    for i in range(attempts):
        try:
            last = fn(rpc, signature)
            if last is not None:
                return last
        except Exception:
            if i == attempts - 1:
                raise
        time.sleep(min(1 + i, 5))
    return last

def get_transaction_raw(rpc: Rpc, signature: str) -> dict[str, Any] | None:
    return rpc.call("getTransaction", [
        signature,
        {
            "encoding": "json",
            "commitment": "finalized",
            "maxSupportedTransactionVersion": 0,
        },
    ])

def get_transaction(rpc: Rpc, signature: str) -> dict[str, Any] | None:
    return rpc.call("getTransaction", [
        signature,
        {
            "encoding": "jsonParsed",
            "commitment": "finalized",
            "maxSupportedTransactionVersion": 0,
        },
    ])


def instruction_program_id(ix: dict[str, Any]) -> str | None:
    return ix.get("programId")


def account_keys(tx: dict[str, Any]) -> list[str]:
    keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
    out = []
    for k in keys:
        out.append(k.get("pubkey") if isinstance(k, dict) else k)
    return out


def flatten_instructions(tx: dict[str, Any]) -> list[dict[str, Any]]:
    msg = tx.get("transaction", {}).get("message", {})
    outer = msg.get("instructions", []) or []
    events: list[dict[str, Any]] = []

    for index, ix in enumerate(outer):
        events.append({
            "level": "outer",
            "index": index,
            "parentProgramId": None,
            "instruction": ix,
        })

    by_index = {
        g.get("index"): g.get("instructions", [])
        for g in (tx.get("meta", {}).get("innerInstructions") or [])
    }
    for index, inner in by_index.items():
        parent = outer[index] if isinstance(index, int) and index < len(outer) else {}
        parent_pid = instruction_program_id(parent)
        for j, ix in enumerate(inner):
            events.append({
                "level": "inner",
                "index": index,
                "innerIndex": j,
                "parentProgramId": parent_pid,
                "instruction": ix,
            })
    return events


def parsed_instruction_event(event: dict[str, Any]) -> dict[str, Any] | None:
    ix = event["instruction"]
    parsed = ix.get("parsed")
    pid = instruction_program_id(ix)
    if not isinstance(parsed, dict):
        return None
    typ = parsed.get("type")
    info = parsed.get("info")
    return {
        "level": event["level"],
        "index": event["index"],
        "innerIndex": event.get("innerIndex"),
        "programId": pid,
        "programName": KNOWN_PROGRAMS.get(pid) or ix.get("program"),
        "parentProgramId": event.get("parentProgramId"),
        "parentProgramName": KNOWN_PROGRAMS.get(event.get("parentProgramId")),
        "type": typ,
        "info": info,
    }



def raw_instruction_dump(tx: dict[str, Any]) -> dict[str, Any]:
    msg = tx.get("transaction", {}).get("message", {}) or {}
    key_details = msg.get("accountKeys", []) or []

    def enrich(ix: dict[str, Any]) -> dict[str, Any]:
        by_pk = {}
        for k in key_details:
            if isinstance(k, dict) and k.get("pubkey"):
                by_pk[k["pubkey"]] = {
                    "pubkey": k.get("pubkey"),
                    "signer": bool(k.get("signer")),
                    "writable": bool(k.get("writable")),
                    "source": k.get("source"),
                }
        accounts = []
        for a in ix.get("accounts") or []:
            if isinstance(a, str):
                accounts.append(by_pk.get(a, {"pubkey": a}))
            elif isinstance(a, dict):
                pk = a.get("pubkey")
                base = by_pk.get(pk, {"pubkey": pk}) if pk else {}
                accounts.append({**base, **a})
            else:
                accounts.append({"value": a})
        return {
            "programId": ix.get("programId"),
            "program": ix.get("program"),
            "accounts": accounts,
            "data": ix.get("data"),
            "parsed": ix.get("parsed"),
            "stackHeight": ix.get("stackHeight"),
        }

    return {
        "header": msg.get("header"),
        "accountKeys": key_details,
        "signatures": tx.get("transaction", {}).get("signatures", []),
        "outerInstructions": [
            {"index": i, **enrich(ix)}
            for i, ix in enumerate(msg.get("instructions", []) or [])
        ],
        "innerInstructionGroups": [
            {
                "outerIndex": g.get("index"),
                "instructions": [
                    {"innerIndex": j, **enrich(ix)}
                    for j, ix in enumerate(g.get("instructions", []) or [])
                ],
            }
            for g in (tx.get("meta", {}).get("innerInstructions") or [])
        ],
        "logMessages": tx.get("meta", {}).get("logMessages", []),
        "preBalances": tx.get("meta", {}).get("preBalances", []),
        "postBalances": tx.get("meta", {}).get("postBalances", []),
        "preTokenBalances": tx.get("meta", {}).get("preTokenBalances", []),
        "postTokenBalances": tx.get("meta", {}).get("postTokenBalances", []),
        "loadedAddresses": tx.get("meta", {}).get("loadedAddresses"),
        "fee": tx.get("meta", {}).get("fee"),
        "err": tx.get("meta", {}).get("err"),
        "computeUnitsConsumed": tx.get("meta", {}).get("computeUnitsConsumed"),
    }


def raw_compiled_dump(raw_tx: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw_tx:
        return None
    msg = raw_tx.get("transaction", {}).get("message", {}) or {}
    keys = msg.get("accountKeys", []) or []
    loaded = raw_tx.get("meta", {}).get("loadedAddresses") or {}
    full_keys = list(keys) + list(loaded.get("writable") or []) + list(loaded.get("readonly") or [])

    def norm(ix: dict[str, Any]) -> dict[str, Any]:
        pidx = ix.get("programIdIndex")
        account_indexes = ix.get("accounts") or []
        return {
            "programIdIndex": pidx,
            "programId": full_keys[pidx] if isinstance(pidx, int) and pidx < len(full_keys) else None,
            "accountIndexes": account_indexes,
            "accounts": [
                full_keys[i] if isinstance(i, int) and i < len(full_keys) else None
                for i in account_indexes
            ],
            "dataBase58": ix.get("data"),
            "stackHeight": ix.get("stackHeight"),
        }

    return {
        "accountKeys": keys,
        "loadedAddresses": loaded,
        "outerInstructions": [norm(ix) for ix in (msg.get("instructions") or [])],
        "innerInstructionGroups": [
            {
                "outerIndex": g.get("index"),
                "instructions": [norm(ix) for ix in (g.get("instructions") or [])],
            }
            for g in (raw_tx.get("meta", {}).get("innerInstructions") or [])
        ],
    }


def summarize_transaction(signature: str, tx: dict[str, Any] | None) -> dict[str, Any]:
    if tx is None:
        return {"signature": signature, "available": False}
    keys = account_keys(tx)
    parsed_events = []
    all_programs: set[str] = set()
    for event in flatten_instructions(tx):
        ix = event["instruction"]
        pid = instruction_program_id(ix)
        if pid:
            all_programs.add(pid)
        if event.get("parentProgramId"):
            all_programs.add(event["parentProgramId"])
        p = parsed_instruction_event(event)
        if p:
            parsed_events.append(p)

    token_events = [
        p for p in parsed_events
        if p.get("programId") in TOKEN_PROGRAMS and p.get("type") in INTERESTING_TOKEN_TYPES
    ]

    # Preserve the raw outer instruction envelope for custom programs. For
    # jsonParsed transactions, custom program instructions remain encoded as
    # base58 data + account pubkeys, which is exactly what we need to identify
    # the first on-chain program hit and its wire payload.
    outer_raw = []
    for index, ix in enumerate(tx.get("transaction", {}).get("message", {}).get("instructions", []) or []):
        outer_raw.append({
            "index": index,
            "programId": ix.get("programId"),
            "programName": KNOWN_PROGRAMS.get(ix.get("programId")) or ix.get("program"),
            "accounts": ix.get("accounts"),
            "data": ix.get("data"),
            "parsed": ix.get("parsed"),
            "stackHeight": ix.get("stackHeight"),
        })

    return {
        "signature": signature,
        "available": True,
        "slot": tx.get("slot"),
        "blockTime": tx.get("blockTime"),
        "err": tx.get("meta", {}).get("err"),
        "fee": tx.get("meta", {}).get("fee"),
        "accountKeys": keys,
        "messageHeader": tx.get("transaction", {}).get("message", {}).get("header"),
        "accountKeyDetails": tx.get("transaction", {}).get("message", {}).get("accountKeys", []),
        "transactionSignatures": tx.get("transaction", {}).get("signatures", []),
        "logMessages": tx.get("meta", {}).get("logMessages", []),
        "innerInstructionsRaw": tx.get("meta", {}).get("innerInstructions", []),
        "wireDump": raw_instruction_dump(tx),
        "programIds": [
            {"address": p, "name": KNOWN_PROGRAMS.get(p)}
            for p in sorted(all_programs)
        ],
        "parsedInstructions": parsed_events,
        "interestingTokenInstructions": token_events,
        "outerInstructions": outer_raw,
        "preTokenBalances": tx.get("meta", {}).get("preTokenBalances"),
        "postTokenBalances": tx.get("meta", {}).get("postTokenBalances"),
    }


def event_mentions_address(event: dict[str, Any], address: str) -> bool:
    info = event.get("info")
    if isinstance(info, dict):
        return address in json.dumps(info, sort_keys=True)
    return False


def analyze_address(rpc: Rpc, label: str, address: str, max_pages: int, scan_limit: int) -> dict[str, Any]:
    account = get_account(rpc, address)
    sigs, exhausted = signatures_for_address(rpc, address, max_pages)
    result: dict[str, Any] = {
        "label": label,
        "address": address,
        "account": account,
        "history": {
            "signaturesFetched": len(sigs),
            "historyExhausted": exhausted,
            "maxPages": max_pages,
        },
    }
    if not sigs:
        result["history"]["oldestVisible"] = None
        return result

    oldest_meta = sigs[-1]
    newest_meta = sigs[0]
    result["history"]["newestVisible"] = newest_meta
    result["history"]["oldestVisible"] = oldest_meta
    oldest_tx = get_transaction(rpc, oldest_meta["signature"])
    result["oldestTransaction"] = summarize_transaction(oldest_meta["signature"], oldest_tx)

    # Scan oldest-to-newest so initialization/first issuance tends to surface first.
    candidates = list(reversed(sigs))
    if scan_limit > 0:
        candidates = candidates[:scan_limit]

    evidence: dict[str, list[dict[str, Any]]] = {
        "initializeMint": [],
        "mintTo": [],
        "burn": [],
        "setAuthority": [],
        "closeAccount": [],
    }
    tx_scanned = 0
    for meta in candidates:
        tx = get_transaction(rpc, meta["signature"])
        tx_scanned += 1
        if tx is None:
            continue
        summary = summarize_transaction(meta["signature"], tx)
        for ev in summary.get("interestingTokenInstructions", []):
            if not event_mentions_address(ev, address):
                continue
            typ = ev.get("type")
            if typ in ("initializeMint", "initializeMint2"):
                bucket = "initializeMint"
            elif typ in ("mintTo", "mintToChecked"):
                bucket = "mintTo"
            elif typ in ("burn", "burnChecked"):
                bucket = "burn"
            elif typ == "setAuthority":
                bucket = "setAuthority"
            elif typ == "closeAccount":
                bucket = "closeAccount"
            else:
                continue
            if len(evidence[bucket]) < 20:
                evidence[bucket].append({
                    "signature": meta["signature"],
                    "slot": tx.get("slot"),
                    "blockTime": tx.get("blockTime"),
                    "instruction": ev,
                    "programIds": summary.get("programIds"),
                })

        # Once we have the crucial lifecycle evidence, avoid hammering RPC unnecessarily.
        if evidence["initializeMint"] and evidence["mintTo"] and evidence["burn"]:
            break

    result["history"]["transactionsScannedForEvidence"] = tx_scanned
    result["evidence"] = evidence
    return result


def md_account(a: dict[str, Any]) -> str:
    if not a.get("exists"):
        return "**Account does not currently exist.**"
    info = a.get("info") or {}
    lines = [
        f"- Owner program: \`{a.get('owner')}\` ({a.get('ownerName') or a.get('program') or 'unknown'})",
        f"- Parsed type: \`{a.get('parsedType')}\`",
        f"- Lamports: \`{a.get('lamports')}\`",
    ]
    if a.get("parsedType") == "mint":
        lines += [
            f"- Supply: \`{info.get('supply')}\`",
            f"- Decimals: \`{info.get('decimals')}\`",
            f"- Mint authority: \`{info.get('mintAuthority')}\`",
            f"- Freeze authority: \`{info.get('freezeAuthority')}\`",
            f"- Is initialized: \`{info.get('isInitialized')}\`",
        ]
        if "extensions" in info:
            lines.append(f"- Token-2022 extensions: \`{json.dumps(info.get('extensions'), sort_keys=True)}\`")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# DFlow / Kalshi Solana forensic report",
        "",
        f"RPC: \`{report['rpcDisplay']}\`",
        "",
        "This report is generated from Solana JSON-RPC data. Treat DFlow/API documentation as context; the evidence below is the on-chain portion.",
        "",
    ]
    for target in report["targets"]:
        lines += [
            f"## {target['label']}",
            "",
            f"Address: \`{target['address']}\`",
            "",
            md_account(target["account"]),
            "",
        ]
        hist = target["history"]
        oldest = hist.get("oldestVisible")
        if oldest:
            lines += [
                f"- Signatures fetched: **{hist['signaturesFetched']}** (history exhausted: **{hist['historyExhausted']}**)",
                f"- Oldest visible signature: \`{oldest.get('signature')}\` at slot \`{oldest.get('slot')}\`",
                "",
            ]
        evidence = target.get("evidence") or {}
        for bucket in ("initializeMint", "mintTo", "burn", "setAuthority", "closeAccount"):
            evs = evidence.get(bucket) or []
            lines.append(f"### {bucket} evidence ({len(evs)})")
            lines.append("")
            if not evs:
                lines.append("_No matching parsed instruction found in the scanned transaction window._")
                lines.append("")
                continue
            for ev in evs[:5]:
                ix = ev["instruction"]
                lines += [
                    f"- tx \`{ev['signature']}\` — slot \`{ev.get('slot')}\`",
                    f"  - token program: \`{ix.get('programId')}\`",
                    f"  - outer/CPI parent program: \`{ix.get('parentProgramId')}\`",
                    f"  - info: \`{json.dumps(ix.get('info'), sort_keys=True)}\`",
                ]
            lines.append("")

    if report.get("evidenceTransactions"):
        lines += ["# Explicit evidence transactions", ""]
        for tx in report["evidenceTransactions"]:
            lines += [
                f"## \`{tx['signature']}\`",
                "",
                f"- Available: **{tx.get('available')}**",
                f"- Slot: \`{tx.get('slot')}\`",
                f"- Error: \`{tx.get('err')}\`",
                "",
            ]
            for ev in tx.get("interestingTokenInstructions", []):
                lines.append(
                    f"- \`{ev.get('type')}\` via \`{ev.get('programId')}\`, "
                    f"outer/CPI parent \`{ev.get('parentProgramId')}\`: "
                    f"\`{json.dumps(ev.get('info'), sort_keys=True)}\`"
                )
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--targets", default="targets.json")
    p.add_argument("--out-dir", default="reports")
    p.add_argument("--max-pages", type=int, default=int(os.getenv("MAX_SIGNATURE_PAGES", "10")))
    p.add_argument("--scan-limit", type=int, default=int(os.getenv("SCAN_TX_LIMIT", "1000")))
    args = p.parse_args()

    rpc_url = os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
    rpc = Rpc(rpc_url)

    cfg = json.loads(Path(args.targets).read_text())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    for item in cfg.get("accounts", []):
        print(f"Analyzing {item['label']}: {item['address']}", flush=True)
        try:
            targets.append(analyze_address(
                rpc, item["label"], item["address"], args.max_pages, args.scan_limit
            ))
        except Exception as exc:
            targets.append({
                "label": item["label"],
                "address": item["address"],
                "error": str(exc),
                "account": {"exists": False, "address": item["address"]},
                "history": {},
            })

    open_candidates = []
    discovery = cfg.get("openOrderDiscovery") or {}

    # Auto-infer the buyer from the latest evidence transaction when explicit
    # discovery config is absent. We identify the owner of a token account
    # whose balance increases from zero, then locate that same owner's stablecoin
    # account in the transaction and scan backward from the fill signature.
    if (not discovery.get("wallet") or not discovery.get("usdcAccount")) and cfg.get("evidenceTransactions"):
        fill_sig = cfg["evidenceTransactions"][-1]
        try:
            fill_tx = get_transaction(rpc, fill_sig)
            if fill_tx:
                s = summarize_transaction(fill_sig, fill_tx)
                pre = {b.get("accountIndex"): b for b in (s.get("preTokenBalances") or [])}
                post = {b.get("accountIndex"): b for b in (s.get("postTokenBalances") or [])}
                wallet = None
                usdc_account = None

                # Find the owner of an account that goes from absent/zero to nonzero.
                for idx, pb in post.items():
                    pre_amt = 0
                    if idx in pre:
                        try:
                            pre_amt = int((pre[idx].get("uiTokenAmount") or {}).get("amount") or "0")
                        except Exception:
                            pre_amt = 0
                    try:
                        post_amt = int((pb.get("uiTokenAmount") or {}).get("amount") or "0")
                    except Exception:
                        post_amt = 0
                    if post_amt > pre_amt and pb.get("owner"):
                        wallet = pb.get("owner")
                        break

                # Among that owner's other token accounts in the fill tx, select
                # the classic stablecoin-looking account: 6 decimals and unchanged
                # balance across pre/post.
                keys = s.get("accountKeys") or []
                if wallet:
                    for idx, pb in post.items():
                        if pb.get("owner") != wallet:
                            continue
                        ui = pb.get("uiTokenAmount") or {}
                        if ui.get("decimals") != 6:
                            continue
                        if idx in pre:
                            pre_ui = pre[idx].get("uiTokenAmount") or {}
                            if pre_ui.get("amount") == ui.get("amount"):
                                if isinstance(idx, int) and idx < len(keys):
                                    usdc_account = keys[idx]
                                    break

                if wallet and usdc_account:
                    discovery = {
                        "wallet": wallet,
                        "usdcAccount": usdc_account,
                        "beforeSignature": fill_sig,
                        "limit": 200,
                    }
        except Exception as exc:
            open_candidates = [{"error": f"fill inference failed: {exc}"}]

    if discovery.get("wallet") and discovery.get("usdcAccount"):
        print("Searching for user-signed open-order candidates", flush=True)
        try:
            open_candidates = find_user_open_candidates(
                rpc,
                discovery["wallet"],
                discovery["usdcAccount"],
                discovery.get("beforeSignature"),
                int(discovery.get("limit", 200)),
            )
        except Exception as exc:
            open_candidates = [{"error": str(exc)}]

    explicit = []
    wire_dumps = {}
    for signature in cfg.get("evidenceTransactions", []):
        print(f"Decoding evidence transaction {signature}", flush=True)
        try:
            parsed_tx = get_transaction_resilient(rpc, signature, raw=False)
            if parsed_tx is None:
                explicit.append({"signature": signature, "available": False, "error": "RPC returned null after retries"})
                continue
            s = summarize_transaction(signature, parsed_tx)
            raw_tx = get_transaction_resilient(rpc, signature, raw=True)
            s["rawCompiled"] = raw_compiled_dump(raw_tx)
            explicit.append(s)
            wire_dumps[signature] = {
                "parsed": s.get("wireDump"),
                "rawCompiled": s.get("rawCompiled"),
            }
        except Exception as exc:
            explicit.append({"signature": signature, "available": False, "error": str(exc)})

    if cfg.get("evidenceTransactions"):
        available_explicit = [x for x in explicit if x and x.get("available") is True]
        if not available_explicit:
            raise RuntimeError(
                "All known historical evidence transactions were unavailable from RPC after retries; refusing to emit false-negative report"
            )

    report = {
        "rpcDisplay": "SOLANA_RPC_URL" if (os.getenv("SOLANA_RPC_URL") or "").strip() else "public mainnet-beta RPC",
        "targets": targets,
        "evidenceTransactions": explicit,
        "openOrderCandidates": open_candidates,
    }
    (out_dir / "wire-transactions.json").write_text(json.dumps(wire_dumps, indent=2, sort_keys=False))
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    md = render_markdown(report)
    (out_dir / "report.md").write_text(md)

    # Make the key findings visible directly in GitHub Actions.
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text(md)

    print(f"Wrote {out_dir / 'report.json'} and {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
