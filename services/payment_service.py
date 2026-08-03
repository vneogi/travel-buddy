"""Travel Buddy MVP - Payment & Subscription Service

Handles the free-to-paid upgrade flow:
  - RevenueCat: In-app purchase validation (Play Store / App Store)
  - Stripe: Web/direct payment processing (backup/admin)
  - Webhook handlers for subscription lifecycle events

Tier Logic:
  Free: 5 reroutes/day, light model only, basic venues
  Pro ($4.99/mo): 50 reroutes/day, heavy model access, sponsored-free results

Requires:
  pip install stripe
  Environment vars: TB_STRIPE_SECRET_KEY, TB_STRIPE_WEBHOOK_SECRET,
                    TB_REVENUECAT_API_KEY
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx

from config.settings import settings


# Subscription plans
PLANS = {
    "pro_monthly": {
        "name": "Travel Buddy Pro (Monthly)",
        "price_usd": 4.99,
        "interval": "month",
        "max_reroutes": 50,
        "features": ["50 daily reroutes", "GPT-4o access", "No sponsored results", "Priority support"],
        "stripe_price_id": "price_XXXXXXXXX",  # Set in env
        "revenuecat_product_id": "tb_pro_monthly",
    },
    "pro_yearly": {
        "name": "Travel Buddy Pro (Yearly)",
        "price_usd": 39.99,
        "interval": "year",
        "max_reroutes": 50,
        "features": ["50 daily reroutes", "GPT-4o access", "No sponsored results", "Priority support", "2 months free"],
        "stripe_price_id": "price_YYYYYYYYY",
        "revenuecat_product_id": "tb_pro_yearly",
    },
}


class PaymentService:
    """Unified payment processing for subscription management."""

    def __init__(self):
        self.stripe_key = None  # Set via env: TB_STRIPE_SECRET_KEY
        self.stripe_webhook_secret = None  # TB_STRIPE_WEBHOOK_SECRET
        self.revenuecat_key = None  # TB_REVENUECAT_API_KEY

    # =========================================================================
    # RevenueCat (In-App Purchases - Primary for Mobile)
    # =========================================================================

    async def verify_revenuecat_purchase(
        self, user_id: str, receipt_token: str, platform: str = "android"
    ) -> Dict:
        """Verify a mobile in-app purchase via RevenueCat.

        Called after the mobile app completes a purchase through
        Google Play Billing or Apple StoreKit.

        Returns:
            {
                "valid": bool,
                "product_id": str,
                "expires_at": str,
                "is_active": bool,
            }
        """
        headers = {
            "Authorization": f"Bearer {self.revenuecat_key}",
            "Content-Type": "application/json",
            "X-Platform": platform,  # "android" or "ios"
        }

        # POST receipt to RevenueCat
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
            subscriber = data.get("subscriber", {})
            entitlements = subscriber.get("entitlements", {})

            # Check for active "pro" entitlement
            pro_entitlement = entitlements.get("pro", {})
            is_active = pro_entitlement.get("expires_date") is not None

            return {
                "valid": True,
                "product_id": pro_entitlement.get("product_identifier"),
                "expires_at": pro_entitlement.get("expires_date"),
                "is_active": is_active,
            }

        return {"valid": False, "error": response.text}

    async def get_subscriber_status(self, user_id: str) -> Dict:
        """Check current subscription status for a user via RevenueCat."""
        headers = {
            "Authorization": f"Bearer {self.revenuecat_key}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.revenuecat.com/v1/subscribers/{user_id}",
                headers=headers,
            )

        if response.status_code == 200:
            data = response.json()
            subscriber = data.get("subscriber", {})
            entitlements = subscriber.get("entitlements", {})

            has_pro = "pro" in entitlements
            pro_data = entitlements.get("pro", {})

            return {
                "user_id": user_id,
                "is_pro": has_pro,
                "expires_at": pro_data.get("expires_date"),
                "product_id": pro_data.get("product_identifier"),
                "will_renew": not pro_data.get("unsubscribe_detected_at"),
            }

        return {"user_id": user_id, "is_pro": False}

    # =========================================================================
    # Stripe (Web Payments - Secondary/Admin)
    # =========================================================================

    async def create_checkout_session(
        self, user_id: str, plan_id: str = "pro_monthly"
    ) -> Dict:
        """Create a Stripe Checkout session for web upgrades."""
        import stripe
        stripe.api_key = self.stripe_key

        plan = PLANS.get(plan_id)
        if not plan:
            raise ValueError(f"Unknown plan: {plan_id}")

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price": plan["stripe_price_id"],
                "quantity": 1,
            }],
            success_url="https://travelbuddy.app/upgrade/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://travelbuddy.app/upgrade/cancel",
            metadata={
                "user_id": user_id,
                "plan_id": plan_id,
            },
            client_reference_id=user_id,
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    def verify_stripe_webhook(
        self, payload: bytes, signature: str
    ) -> Optional[Dict]:
        """Verify and parse a Stripe webhook event."""
        import stripe
        stripe.api_key = self.stripe_key

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.stripe_webhook_secret
            )
            return {
                "type": event["type"],
                "data": event["data"]["object"],
            }
        except (stripe.error.SignatureVerificationError, ValueError):
            return None

    # =========================================================================
    # Webhook Event Handlers
    # =========================================================================

    async def handle_subscription_event(self, event: Dict) -> Dict:
        """Process subscription lifecycle events from Stripe or RevenueCat.

        Events handled:
          - checkout.session.completed -> Activate pro
          - customer.subscription.deleted -> Downgrade to free
          - customer.subscription.updated -> Update expiry
          - invoice.payment_failed -> Grace period
        """
        event_type = event.get("type", "")
        data = event.get("data", {})

        if event_type == "checkout.session.completed":
            user_id = data.get("metadata", {}).get("user_id")
            if user_id:
                return {
                    "action": "upgrade",
                    "user_id": user_id,
                    "tier": "pro",
                    "message": "Subscription activated",
                }

        elif event_type == "customer.subscription.deleted":
            user_id = data.get("metadata", {}).get("user_id")
            if user_id:
                return {
                    "action": "downgrade",
                    "user_id": user_id,
                    "tier": "free",
                    "message": "Subscription cancelled",
                }

        elif event_type == "invoice.payment_failed":
            user_id = data.get("metadata", {}).get("user_id")
            return {
                "action": "grace_period",
                "user_id": user_id,
                "message": "Payment failed - 3 day grace period",
                "grace_until": (
                    datetime.utcnow() + timedelta(days=3)
                ).isoformat(),
            }

        return {"action": "ignored", "event_type": event_type}

    # =========================================================================
    # RevenueCat Webhook Handler
    # =========================================================================

    async def handle_revenuecat_webhook(self, payload: Dict) -> Dict:
        """Process RevenueCat server-to-server webhook events.

        Events: INITIAL_PURCHASE, RENEWAL, CANCELLATION, EXPIRATION,
                BILLING_ISSUE, PRODUCT_CHANGE
        """
        event_type = payload.get("event", {}).get("type", "")
        app_user_id = payload.get("event", {}).get("app_user_id", "")

        if event_type in ("INITIAL_PURCHASE", "RENEWAL"):
            return {
                "action": "upgrade",
                "user_id": app_user_id,
                "tier": "pro",
                "event": event_type,
            }

        elif event_type in ("CANCELLATION", "EXPIRATION"):
            return {
                "action": "downgrade",
                "user_id": app_user_id,
                "tier": "free",
                "event": event_type,
            }

        elif event_type == "BILLING_ISSUE":
            return {
                "action": "grace_period",
                "user_id": app_user_id,
                "event": event_type,
            }

        return {"action": "ignored", "event_type": event_type}


# Singleton instance
payment_service = PaymentService()
