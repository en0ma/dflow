# Obtaining a valid DFlow OPEN construction

## Verified source of construction data

DFlow's current developer recipes use **GET /order** to request a quote and
a prebuilt Solana transaction. The older GET /quote endpoint is deprecated.
A 0x40 OPEN message is **not** safely produced by combining arbitrary amounts
with historical opaque bytes.

1. Select an **active** prediction market using DFlow metadata
   (`GET /api/v1/markets?status=active` or `/api/v1/market/by-mint/{mint}`).
2. Obtain its **YES or NO outcome mint**, not the USDC mint or the market ledger.
3. Request `GET /order` with `inputMint=USDC`, `outputMint=<outcome>`,
   `amount=<base units>`, `userPublicKey=<PUBLIC wallet>`, and
   `slippageBps=<tolerance>`.
4. Keep the **entire transaction** returned by the quote service as the
   construction source. The service determines any opaque route/quote fields.
   The read-only helper below **does not sign, simulate, or submit**.
5. Decode all instructions and address lookup tables before trying to adapt
   the quote to an on-chain CPI. Determine whether the output actually contains
   an OPEN for pReDic, what signers are required, and whether the full transaction
   includes preparation or initialization instructions. Do not assume a direct
   `/order` transaction's signature scheme works unchanged under CPI.
6. Use our historically verified `userOrderEscrow` PDA formula as a check
   against the transaction's order account (wallet + ledger + nonce LE).
7. Only after the quote/account authorization is coherent should the *same*
   order be simulated under `ProgramTest` and the resulting order account,
   input token debit, and event logs checked.

## Read-only quote fetch

```bash
python3 predic-cpi-probe/fetch_order_quote.py \
  --output-mint <CURRENT_OUTCOME_MINT> \
  --wallet <PUBLIC_WALLET> \
  --amount 1000000 --slippage-bps 100
```

The dev quote endpoint is keyless but rate-limited; production may require
`DFLOW_API_KEY`. Never put a secret key in `--wallet`; do not commit quote
responses containing private information.

The returned `transaction` is base64 and may be versioned or use address
lookup tables. The present helper saves the full server response for offline
parsing only; it does not assert that it is a pReDic OPEN or CPI-compatible.

## Known uncertainties

- The server may supply a different instruction route, not pReDic 0x40.
- The 80-byte historical layout is empirically observed, not a stable
  published client construction ABI.
- A PDA signer in a custom Solana program needs proper `invoke_signed`
  semantics; a previously wallet-signed transaction is not equivalent.
- KYC/Proof and venue-specific restrictions can apply.
- The currently stored market snapshots do not establish that the market
  accepts fresh OPENs.

Official references:
- https://dflow.mintlify.app/build/recipes/prediction-markets/decrease-position
- https://dflow.mintlify.app/build/recipes/prediction-markets/monitor-market-lifecycle
- https://dflow.mintlify.app/build/prediction-markets/onchain-trade-parsing
- https://dflow.mintlify.app/build/trading-api/imperative/quote
