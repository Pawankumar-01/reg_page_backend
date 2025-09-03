from datetime import datetime, date
from zoneinfo import ZoneInfo
from decouple import config
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import razorpay
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter()

KEY_ID = config("RAZORPAY_KEY_ID")
KEY_SECRET = config("RAZORPAY_SECRET")
client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))

EARLY_END = date(2025, 9, 9)   # inclusive
REGULAR_END = date(2025, 9, 18)  # inclusive

SMTP_HOST = config("SMTP_HOST", default="smtp.gmail.com")
SMTP_PORT = int(config("SMTP_PORT", default="587"))
SMTP_USER = config("SMTP_USER", default="")
SMTP_PASS = config("SMTP_PASS", default="")

class CouponRequest(BaseModel):
    coupon: str | None = None

class CreateOrderRequest(BaseModel):
    coupon: str | None = None
    name: str
    email: str
   

def today_ist() -> date:
    # keep cutoffs in India time
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()

def current_tier_and_price(d: date | None = None) -> tuple[str, int]:
    d = d or today_ist()
    if d <= EARLY_END:
        return ("Early Bird", 1000)
    if d <= REGULAR_END:
        return ("Regular", 1200)
    return ("Late/Onsite", 1500)

def normalize(code: str | None) -> str:
    return (code or "").strip().upper()

def validate_coupon(code: str | None) -> bool:
    # simple 50% coupon; swap for DB logic when needed
    return normalize(code) == "IPSA2025"

def apply_coupon(amount_rupees: int, code: str | None) -> tuple[int, int]:
    """returns (discount_rupees, final_rupees)"""
    if validate_coupon(code):
        disc = amount_rupees // 2
        return disc, amount_rupees - disc
    return 0, amount_rupees

def send_ack_email(to_email: str, name: str, tier: str, location: str, conference_date: str, final_amount: str):
    if not SMTP_USER or not SMTP_PASS:
        print("⚠️ SMTP not configured, skipping email.")
        return

    subject = "Conference Registration Confirmation"
    body = f"""
Dear {name},

Thank you for registering for the conference.

Your details:
- Tier: {tier}
- Amount Paid: ₹{final_amount}
- Location: {location}
- Conference Date: {conference_date}

We look forward to seeing you at the event!

Regards,
Conference Team
    """

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
            print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

@router.post("/quote")
def quote(body: CouponRequest):
    tier, base = current_tier_and_price()
    discount, final_amt = apply_coupon(base, body.coupon)
    return {
        "tier": tier,
        "base_rupees": base,
        "discount_rupees": discount,
        "final_rupees": final_amt,
        "coupon_valid": validate_coupon(body.coupon),
    }

@router.post("/validate-coupon")
def validate(body: CouponRequest):
    tier, base = current_tier_and_price()
    ok = validate_coupon(body.coupon)
    discount, final_amt = apply_coupon(base, body.coupon)
    return {
        "valid": ok,
        "tier": tier,
        "base_rupees": base,
        "discount_rupees": discount,
        "final_rupees": final_amt,
        "message": "Coupon applied" if ok else "Invalid coupon",
    }

@router.post("/create-order")
def create_order(body: CreateOrderRequest):
    # server-authoritative pricing (never trust client)
    tier, base = current_tier_and_price()
    discount, final_amt_rupees = apply_coupon(base, body.coupon)

    FIXED_LOCATION = "Hyderabad International Convention Centre"
    FIXED_CONFERENCE_DATE = "2025-09-20"

    amount_paise = final_amt_rupees * 100
    try:
        order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {
                    "tier": tier,
                    "base_rupees": str(base),
                    "discount_rupees": str(discount),
                    "final_rupees": str(final_amt_rupees),
                    "coupon": normalize(body.coupon),
                    "name": body.name,
                    "email": body.email,
                    "location": FIXED_LOCATION,
                    "conference_date": FIXED_CONFERENCE_DATE,
                }
        })
        return {
            "key": KEY_ID,
            "order": order,
            "amount": amount_paise,
            "display": {
                "tier": tier,
                "base_rupees": base,
                "discount_rupees": discount,
                "final_rupees": final_amt_rupees
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class VerifyPayload(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/verify-payment")
def verify_payment(payload: VerifyPayload):
    try:
        order = client.order.fetch(payload.razorpay_order_id)
        notes = order.get("notes", {})

        # send acknowledgment email after payment
        send_ack_email(
            to_email=notes.get("email"),
            name=notes.get("name"),
            tier=notes.get("tier"),
            location=notes.get("location"),
            conference_date=notes.get("conference_date"),
            final_amount=notes.get("final_rupees"),
        )

        return {"status": "success", "order_id": payload.razorpay_order_id, "notes": notes}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {e}")
