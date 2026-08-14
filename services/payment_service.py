"""Travel Buddy MVP - Payment & Subscription Service

Handles the free-to-paid upgrade flow:
  - RevenueCat: In-app purchase validation (Play Store / App Store)
  - Stripe: Web/direct payment processing
  - Webhook handlers for subscription lifecycle events

Keys are loaded from settings (TB_STRIPE_SECRET_KEY, TB_STRIPE_WEBHOOK_SECRET,
TB_REVENUECAT_API_KEY, TB_REVENUECAT_WEBHOOK_AUTH). All verification fails
closed when the relevant secret is not configured.

Requires: pip install stripe httpx
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import httpx

from config.settings import settings


PLANS = {
    "pro_monthly": {
        "name": "Travel Buddy Pro (Monthly)",
        "price_usd": 4.99,
        "interval": "month",
        "max_reroutes": 50,
        "features": [
            "50 daily reroutes",
            "GPT-4o access",
            "No sponsored results",
            "Priority support",
        ],
        "revenuecat_product_id": "tb_pro_monthly",
    },
    "pro_yearly": {
        "name": "Travel Buddy Pro (Yearly)",
        "price_usd": 39.99,
        "interval": "year",
        "max_reroutes": 50,
        "features": [
            "50 daily reroutes",
            "GPT-4o access",
            "No sponsored results",
            "Priority support",
            "2 months free",
        ],
        "revenuecat_product_id": "tb_pro_yearly",
    },
}


class PaymentService:
    """Unified payment processing for subscription management."""

    def __init__(self):
        # Load real credentials from settings (previously hardcoded to None).
        self.stripe_key = settings.stripe_secret_key
        self.stripe_webhook_secret = settings.stripe_webhook_secret
        self.revenuecat_key = settings.revenuecat_api_key
        self.revenuecat_webhook_auth = settings.revenuecat_webhook_auth

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _entitlement_active(expires_date: Optional[str]) -> bool:
        """True only if expires_date is a valid timestamp in the future (UTC)."""
        if not expires_date:
            return False
        try:
            cleaned = expires_date.replace("Z", "+00:00")
            expiry = datetime.fromisoformat(cleaned)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return False
        return expiry > datetime.now(timezone.utc)

    def _stripe_price_id(self, plan_id: str) -> Optional[str]:
        """Resolve the Stripe price id for a plan from settings."""
        return {
            "pro_monthly": settings.stripe_price_monthly,
            "pro_yearly": settings.stripe_price_yearly,
        }.get(plan_id)

    # =========================================================================
    # RevenueCat (In-App Purchases - Primary for Mobile)
    # =========================================================================

    async def verify_revenuecat_purchase(
        self, user_id: str, receipt_token: str, platform: str = "android"
    ) -> Dict:
        """Verify a mobile in-app purchase via RevenueCat."""
        headers = {
            "Authorization": f"Bearer {self.revenuecat_key}",
            "Content-Type": "application/json",
            "X-Platform": platform,
        }
        body = {
            "app_user_id": user_id,
            "fetch_token": receipt_token,
            "product_id": "tb_pro_monthly",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.revenuecat.com/v1/receipts",
                headers=headers,
                json=body,
            )

        if response.status_code == 200:
            data = response.json()
            entitlements = data.get("subscriber", {}).get("entitlements", {})
            pro = entitlements.get("pro", {})
            expires_at = pro.get("expires_date")
            return {
                "valid": True,
                "product_id": pro.get("product_identifier"),
                "expires_at": expires_at,
                "is_active": self._entitlement_active(expires_at),
            }

        return {"valid": False, "error": response.text}

    async def get_subscriber_status(self, user_id: str) -> Dict:
        """Check current subscription status for a user via RevenueCat."""
        headers = {"Authorization": f"Bearer {self.revenuecat_key}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.revenuecat.com/v1/subscribers/{user_id}",
                headers=headers,
            )

        if response.status_code == 200:
            entitlements = response.json().get("subscriber", {}).get("entitlements", {})
            pro_data = entitlements.get("pro", {})
            expires_at = pro_data.get("expires_date")
            return {
                "user_id": user_id,
                "is_pro": self._entitlement_active(expires_at),
                "expires_at": expires_at,
                "product_id": pro_data.get("product_identifier"),
                "will_renew": not pro_data.get("unsubscribe_detected_at"),
            }

        return {"user_id": user_id, "is_pro": False}

    def verify_revenuecat_webhook_auth(self, authorization: Optional[str]) -> bool:
        """Constant-time check of the RevenueCat webhook Authorization header.

        Fails closed if the expected secret is not configured.
        """
        expected = self.revenuecat_webhook_auth
        if not expected or not authorization:
            return False
        return hmac.compare_digest(authorization, expected)

    # =========================================================================
    # Stripe (Web Payments)
    # =========================================================================

    async def create_checkout_session(self, user_id: str, plan_id: str = "pro_monthly") -> Dict:
        """Create a Stripe Checkout session for web upgrades."""
        import stripe

        stripe.api_key = self.stripe_key

        if plan_id not in PLANS:
            raise ValueError(f"Unknown plan: {plan_id}")

        price_id = self._stripe_price_id(plan_id)
        if not price_id:
            raise ValueError(
                f"Stripe price id for '{plan_id}' is not configured "
                f"(set TB_STRIPE_PRICE_{'MONTHLY' if plan_id == 'pro_monthly' else 'YEARLY'})"
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=settings.checkout_success_url,
            cancel_url=settings.checkout_cancel_url,
            metadata={"user_id": user_id, "plan_id": plan_id},
            # Propagate metadata to the subscription so deletion events carry user_id.
            subscription_data={"metadata": {"user_id": user_id, "plan_id": plan_id}},
            client_reference_id=user_id,
        )
        return {"checkout_url": session.url, "session_id": session.id}

    def verify_stripe_webhook(self, payload: bytes, signature: str) -> Optional[Dict]:
        """Verify and parse a Stripe webhook event. Returns None if invalid."""
        if not self.stripe_webhook_secret:
            return None
        import stripe

        stripe.api_key = self.stripe_key
        try:
            event = stripe.Webhook.construct_event(payload, signature, self.stripe_webhook_secret)
            return {"type": event["type"], "data": event["data"]["object"]}
        except Exception:
            # Any signature/parse failure -> reject.
            return None

    # =========================================================================
    # Webhook Event Handlers
    # =========================================================================

    async def handle_subscription_event(self, event: Dict) -> Dict:
        """Process Stripe subscription lifecycle events."""
        event_type = event.get("type", "")
        data = event.get("data", {})
        user_id = data.get("metadata", {}).get("user_id")

        if event_type == "checkout.session.completed" and user_id:
            return {"action": "upgrade", "user_id": user_id, "tier": "pro"}

        if event_type == "customer.subscription.deleted" and user_id:
            return {"action": "downgrade", "user_id": user_id, "tier": "free"}

        if event_type == "invoice.payment_failed":
            return {
                "action": "grace_period",
                "user_id": user_id,
                "grace_until": (datetime.now(tz=timezone.utc) + timedelta(days=3)).isoformat(),
            }

        return {"action": "ignored", "event_type": event_type}

    async def handle_revenuecat_webhook(self, payload: Dict) -> Dict:
        """Process RevenueCat server-to-server webhook events."""
        event = payload.get("event", {})
        event_type = event.get("type", "")
        app_user_id = event.get("app_user_id", "")

        if event_type in ("INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION"):
            return {"action": "upgrade", "user_id": app_user_id, "event": event_type}

        if event_type in ("CANCELLATION", "EXPIRATION"):
            return {"action": "downgrade", "user_id": app_user_id, "event": event_type}

        if event_type == "BILLING_ISSUE":
            return {"action": "grace_period", "user_id": app_user_id, "event": event_type}

        return {"action": "ignored", "event_type": event_type}


# Singleton instance
payment_service = PaymentService()
