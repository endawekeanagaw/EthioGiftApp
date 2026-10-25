# Changelog

## v0.2.0 — End-to-end payment simulation and merchant administration
- Added `gift_orders`, `payment_attempts`, `order_cards`, `merchant_staff`, and `gift_transfers` tables.
- Added customer checkout modal with simulated payment channel selection, success popup, failure handling, and retry.
- Added replay-safe order-to-card issuance mapping and prevented duplicate minting from repeating payment callbacks.
- Added role-gated cashier redemption, assigned merchant access and idempotency mismatch checks.
- Added customer order tracking, gift transaction history and better merchant/program creation UI.
- Improved visual design and mobile responsiveness; added Windows one-click launcher.
- Added end-to-end API tests, updated Windows setup, and safer Git ignore defaults.

## v0.1.0 — Original prototype
- Login, merchant programs, simulated gift issue, wallet, transfers, simplified redemption and admin reports.
