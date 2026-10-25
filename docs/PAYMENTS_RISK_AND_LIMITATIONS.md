# v0.6 architecture notes — simulated financial events

## Payment state machine

```text
Order: PENDING -> PAID   -> exactly one OrderCard / gift issue event
       PENDING -> FAILED -> (explicit user Retry) -> PENDING

Intent: PENDING -> SUCCEEDED or FAILED (terminal)
Provider demo event: one immutable event_reference + intent_id + outcome
```

- The buyer creates an order and a payment intent. `buyer_id + idempotency_key` is unique.
- Simulated provider events capture one intent. Compare-and-swap on `gift_orders.status=PENDING` permits only one successful transition for a pending order. `order_cards.order_id` is unique.
- One order can have multiple attempts after failures, but a successful order has one issued card. Replayed **identical** events return ALREADY_PROCESSED; reused references with different payloads are rejected.
- The sandbox demonstration has no actual account debit or external gateway. Status SUCCESS is a simulated test condition, not a real financial confirmation.

### API endpoints

| Operation | Endpoint | Permission |
|---|---|---|
| Create intent | `POST /api/payments/intents` | Order buyer |
| Intent status | `GET /api/payments/intents/{id}` | Buyer/admin |
| Simulate provider result | `POST /api/payments/intents/{id}/simulate` | Buyer, demo enabled |
| Example signed sandbox callback | `POST /api/payments/webhook/sandbox` | HMAC header + timestamp; disabled by default |
| Reconciliation | `GET /api/admin/reconciliation` | Admin |
| Recent sandbox intents | `GET /api/admin/payment-activity` | Admin |
| Fraud alert queue | `GET /api/admin/fraud-alerts` | Admin |
| Alert review | `POST /api/admin/fraud-alerts/{id}/review` | Admin |

Use `/docs` for exact OpenAPI schemas. `idempotency_key` must be generated per user action and reused for retries of the **same action**, never reused for a different order or channel.

## Example of the signed *sandbox-only* callback

The optional endpoint requires:

- `ENABLE_SANDBOX_WEBHOOK=true` (default is false)
- `SANDBOX_WEBHOOK_SECRET` at least 24 characters (must not be committed to Git)
- `X-GiftBridge-Timestamp` Unix seconds, no more than five minutes from server time
- `X-GiftBridge-Signature` equal to HMAC-SHA256(secret, `timestamp + '.' + canonical_json`), hexadecimal
- Canonical JSON: UTF-8 JSON, lexicographically sorted keys, no unnecessary spaces
- JSON fields: `amount_minor`, `event_reference`, `intent_id`, `outcome`, `provider_reference`

Only implement this callback in a disposable test environment. **Real M-PESA, telebirr and bank gateways each require their own documented authentication, request verification, merchant onboarding and settlement contracts. This demo format is not a standard interface of those providers.**

## Reconciliation invariants

- **Issued gift face value** = remaining balances + captured redemptions.
- **Outstanding gift liability** in simulated ledger = remaining balances.
- **Paid orders total** = value of all issued cards.
- Every PAID order is linked to exactly one card and has a corresponding SUCCESS payment attempt.
- All ledger events sum to zero, with positive and negative amounts in minor ETB units.
- Simulated merchant payable and fee ledger totals match redemptions.

The reconciliation does not compare actual bank statements, real payment provider records, or external merchant settlement files. Do not label reports as "bank reconciled".

## Fraud controls

| ID | Trigger | Action |
|---|---|---|
| GBF001 | Successful test purchase >= ETB 10,000 | Create HIGH review alert |
| GBF002 | >=3 failed simulated payment attempts in one hour per buyer | Create MEDIUM review alert |
| GBF003 | >=3 invalid redemption PIN attempts for one generated PIN | Create HIGH review alert |

Alerts are deduplicated by fingerprint and can be investigated, resolved or marked false positive by administrators. **These thresholds are examples, not validated fraud-detection models.** No automatic block occurs for high-value purchases; login lockout and invalid PIN attempt limits are separate preventive controls.

## Security and operational limits

This project has local sandbox account/password hashing, 15-minute login rate/lock control, signed JWTs, one-time redemption PINs, issuer program checking and basic security headers. It still does **not** have mobile/phone verification, secure production key storage, true device/session revocation, hardened financial concurrency, online abuse protection, independent audit, retention/deletion policies, sanctions/KYC/AML checks or disaster recovery. Do not expose the server to the public internet.

In particular, `APP_ENV=production` refuses startup intentionally until a separate, fully reviewed production implementation is designed.
