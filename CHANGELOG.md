# GiftBridge Ethiopia — Changelog

## v0.6.0 — Payment readiness & fraud controls (sandbox)

- Introduced `PaymentIntent` + immutable `PaymentEvent` records for a realistic two-step simulated checkout.
- Added idempotent payment processing, terminal states and retry after failure. One paid order issues one gift only.
- Added an optional **disabled-by-default** HMAC-signed example sandbox webhook for developer tests; it is **not** a real payment-provider webhook.
- Added admin reconciliation comparing paid orders, issued gifts, gift liabilities, redemptions, merchant payables, fees and balanced ledger entries.
- Added triageable fraud alerts for high-value gifts, repeated failed demo payments and repeated invalid redemption PINs.
- Added account login lockouts after repeated incorrect passwords, API cache/security headers and safer cross-version checkout checks.
- Added a Risk & reconciliation center to the Management screen, payment-activity feed, clearer checkout progress, browser UI smoke tests and expanded API tests.
- Preserved v0.5 merchant onboarding, scoped POS, gift personalization and wallet behavior. Additive tables; no destructive DB migration.
- Remains **LOCAL SANDBOX ONLY** with zero real bank/payment/merchant settlement connectivity.

## v0.5.0 — Merchant ecosystem

Merchant applications, approval, merchant owners/managers/cashiers, branches, QR-assisted POS and analytics.

## v0.4.0 — Customer experience

Favorites, gift browse filters, personalized previews, wallet enhancements, demo receipts and partial Amharic localization.

## v0.3.0 — Personalized gifts and redemption

Occasions, presentations, gift notifications, redemption PIN, merchant metrics and Windows launcher.

## v0.2.0 — End-to-end gift purchase simulation

Orders, simulated payments, issuance, wallet transfers, redemption and ledger entries.
