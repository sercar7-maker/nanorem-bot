# WooCommerce payment with partner balance

The backend now provides balance reservation operations through
`BalanceService`:

- `reserve_purchase(partner_id, order_id, order_total)` reserves
  `min(available_balance, order_total)`. The remaining gateway amount is
  `order_total - reservation.amount`.
- `confirm_purchase(order_id)` finalizes the pending reservation.
- `release_purchase(order_id)` returns a pending reservation after a failed
  or cancelled order.

These methods participate in the caller's SQLAlchemy transaction and do not
commit it. The caller must commit a successful operation and roll back the
transaction if a later step fails. Reservation identity is the WooCommerce
order ID; duplicate requests return the existing reservation. The database
also enforces uniqueness for reservation IDs and purchase-payment ledger event
IDs.

The existing signed WooCommerce webhook confirms a pending reservation in
the same transaction as `Purchase`, turnover/rank updates, and commission
processing. A repeated completed webhook is ignored through the existing
`Purchase.ext_ref` guard. Commission and turnover continue to use the complete
WooCommerce order total, including both the balance contribution and the
remaining gateway payment.

## WooCommerce integration still required

This repository does not currently contain a customer-facing WooCommerce
payment gateway or authenticated checkout endpoint. Before enabling balance
payment in the storefront, WooCommerce must:

1. Authenticate the partner and obtain the final order total after discounts.
2. Call the backend reservation operation before charging the remaining
   amount, then persist/use the returned reserved and remaining amounts.
3. Pay `order_total - reservation.amount` through the normal gateway.
4. Send the existing signed completed/failed/cancelled webhook with the same
   order ID and final order total.

Do not expose the service through a public unauthenticated route. The checkout
service-to-service authentication and WooCommerce gateway implementation are
not part of this backend change. Refunds after a reservation has been
confirmed also require a separately defined refund flow.
