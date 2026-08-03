"""Travel Buddy MVP - Payment Router

Endpoints:
  GET  /api/v1/payment/plans              -> Available plans (public)
  GET  /api/v1/payment/status             -> Caller's subscription status
  POST /api/v1/payment/checkout           -> Create Stripe checkout session
  POST /api/v1/payment/verify-purchase    -> Mobile IAP verification (RevenueCat)
  POST /api/v1/payment/webhook/stripe      -> Stripe webhook (signature-verified)
  POST /api/v1/payment/webhook/revenuecat  -> RevenueCat webhook (auth-verified)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from services.payment_service import payment_service, PLANS
from services.database_service import db_service
from security import get_current_user_id

router = APIRouter(prefix="/api/v1/payment", tags=["payment"])


class CheckoutRequest(BaseModel):
    plan_id: str = "pro_monthly"


class VerifyPurchaseRequest(BaseModel):
    receipt_token: str
    platform: str = "android"  # "android" or "ios"


# =========================================================================
# Endpoints
# =========================================================================

@router.get("/plans")
async def get_plans():
    """Get available subscription plans (public)."""
    return {
        "plans": [
            {
                "id": plan_id,
                "name": plan["name"],
                "price_usd": plan["price_usd"],
                "interval": plan["interval"],
                "features": plan["features"],
            }
            for plan_id, plan in PLANS.items()
        ]
    }


@router.get("/status")
async def get_subscription_status(user_id: str = Depends(get_current_user_id)):
    """Check subscription status for the authenticated user."""
    rc_status = await payment_service.get_subscriber_status(user_id)
    user = db_service.get_or_create_user(user_id)
    return {
        "user_id": user_id,
        "local_tier": user.tier_status.value,
        "revenuecat_pro": rc_status.get("is_pro", False),
        "expires_at": rc_status.get("expires_at"),
        "will_renew": rc_status.get("will_renew"),
    }


@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a Stripe Checkout session for the authenticated user."""
    try:
        return await payment_service.create_checkout_session(
            user_id=user_id, plan_id=request.plan_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment error: {str(e)}")


@router.post("/verify-purchase")
async def verify_mobile_purchase(
    request: VerifyPurchaseRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Verify a mobile in-app purchase via RevenueCat for the authenticated user."""
    result = await payment_service.verify_revenuecat_purchase(
        user_id=user_id,
        receipt_token=request.receipt_token,
        platform=request.platform,
    )

    if result.get("valid") and result.get("is_active"):
        db_service.upgrade_user(user_id)
        return {
            "status": "activated",
            "tier": "pro",
            "expires_at": result.get("expires_at"),
            "message": "Pro subscription activated! You now have 50 daily reroutes.",
        }

    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=result.get("error", "Purchase verification failed"),
    )


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (signature-verified)."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    event = payment_service.verify_stripe_webhook(payload, signature)
    if not event:
        raise HTTPException(status_code=400, detail="Invalid signature")

    result = await payment_service.handle_subscription_event(event)

    if result.get("action") == "upgrade" and result.get("user_id"):
        db_service.upgrade_user(result["user_id"])
    elif result.get("action") == "downgrade" and result.get("user_id"):
        db_service.downgrade_user(result["user_id"])

    return {"received": True, "action": result.get("action")}


@router.post("/webhook/revenuecat")
async def revenuecat_webhook(request: Request):
    """Handle RevenueCat server-to-server webhook events (auth-verified)."""
    authorization = request.headers.get("authorization", "")
    if not payment_service.verify_revenuecat_webhook_auth(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authorization",
        )

    payload = await request.json()
    result = await payment_service.handle_revenuecat_webhook(payload)

    if result.get("action") == "upgrade" and result.get("user_id"):
        db_service.upgrade_user(result["user_id"])
    elif result.get("action") == "downgrade" and result.get("user_id"):
        db_service.downgrade_user(result["user_id"])

    return {"received": True, "action": result.get("action")}
