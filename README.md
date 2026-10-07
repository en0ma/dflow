# DFlow on-chain forensics

This repository is a reproducible Solana-RPC investigation of DFlow/Kalshi outcome tokens.

The goal is to answer with **on-chain evidence**, not product documentation:

1. Do the published YES/NO addresses exist as Solana mint accounts?
2. Are they owned by the classic SPL Token program or Token-2022?
3. What are their current mint authority and freeze authority?
4. What Token-2022 extensions, if any, are enabled?
5. What is the oldest transaction visible to the configured RPC?
6. Which transaction initialized each mint?
7. Which program was the outer caller when the token program executed `InitializeMint`, `MintTo`, or `Burn`?
8. Is there evidence of actual issuance and burning/redemption?
9. What program owns the corresponding market ledger?
10. Does the evidence support the statement "DFlow mints the outcome token", or does a separate CLP/market program control minting?

## Run in GitHub Actions

Open **Actions → DFlow on-chain forensics → Run workflow**.

The workflow writes its Markdown findings to the GitHub Actions job summary and uploads:

- `reports/report.md`
- `reports/report.json`

as a workflow artifact.

### Recommended: archival Solana RPC

The default public Solana endpoint may rate-limit requests or prune old transaction history. For conclusive historical evidence, add a repository Actions secret named:

`SOLANA_RPC_URL`

Set it to an archival/mainnet Solana RPC endpoint that supports:

- `getAccountInfo`
- `getSignaturesForAddress`
- `getTransaction`

No RPC key is committed to this repository.

With an archival provider, manually rerun the workflow with a larger `max_signature_pages` if a target has more than 10,000 signatures.

## Run locally

```bash
SOLANA_RPC_URL="https://your-mainnet-rpc.example" \
MAX_SIGNATURE_PAGES=20 \
SCAN_TX_LIMIT=5000 \
python analyze.py
```

Python 3.10+ is sufficient. There are no third-party dependencies.

## Targets

`targets.json` currently contains the known DFlow/Kalshi addresses we want to verify, including the initialized Arsenal market pair and the earlier tie-market candidate pair. It also includes a previously published redemption transaction signature for independent decoding.

Add more market ledgers or outcome mints to `accounts` as we discover them. Add transaction signatures to `evidenceTransactions` when we want a full decoded instruction trace included in every run.

## How to read the evidence

For a mint, the strongest chain of proof is:

```text
mint account exists
  → token-program owner identified
  → initializeMint/initializeMint2 found
  → mint authority identified
  → MintTo/MintToChecked found
  → outer CPI parent program identified
  → Burn/BurnChecked or redemption transaction found
```

A token-program `MintTo` instruction alone does **not** prove that the DFlow program itself is the issuer. The relevant issuer/control evidence is the mint authority plus the outer program/PDA responsible for invoking the token program.

## Limitations

Solana's standard RPC API lists signatures newest-to-oldest. This collector paginates backward and reports whether the configured window exhausted available history. If `historyExhausted` is false, the reported "oldest visible" transaction is only the oldest transaction reached within the configured page limit.

Parsed RPC data also depends on provider support. The JSON report retains program IDs, transaction signatures, token balances, and parsed instructions so any important transaction can subsequently be decoded at the raw-message level if needed.
