from datetime import datetime, date
from zoneinfo import ZoneInfo
from decouple import config
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import razorpay
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client



SUPABASE_URL = config("SUPABASE_URL")
SUPABASE_KEY = config("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
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

    subject = "🎉 IPSA 2025 – Registration Confirmation"

    body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; padding:20px;">

        <!-- Header with logo -->
        <div style="display:flex; justify-content: space-between; align-items:center; margin-bottom:20px;">
          <div>
            <h1 style="color:#2E86C1; margin:0; font-size:22px;">IPSA 2025</h1>
          </div>
          <div>
            <img src="https://saigangapanakeia.in/Images/logo.png" 
                 alt="Sai Ganga Panakeia Ltd" 
                 style="height:50px;"/>
          </div>
        </div>

        <h2 style="color:#2E86C1;">Hello {name},</h2>

        <p><b>Thank you for registering for the Conference </b> (Two Traditions,
        One Science : The PSA Paradigm.)</p>

        <h3 style="color:#117A65;">Your Registration Details:</h3>
        <table style="border-collapse: collapse; width: 100%; margin-bottom:20px;">
          <tr>
            <td style="border:1px solid #ddd; padding:8px;"><b>Tier</b></td>
            <td style="border:1px solid #ddd; padding:8px;">{tier}</td>
          </tr>
          <tr>
            <td style="border:1px solid #ddd; padding:8px;"><b>Amount Paid</b></td>
            <td style="border:1px solid #ddd; padding:8px;">₹{final_amount}</td>
          </tr>
          <tr>
            <td style="border:1px solid #ddd; padding:8px;"><b>Location</b></td>
            <td style="border:1px solid #ddd; padding:8px;">{location}</td>
          </tr>
          <tr>
            <td style="border:1px solid #ddd; padding:8px;"><b>Conference Date</b></td>
            <td style="border:1px solid #ddd; padding:8px;">{conference_date}</td>
          </tr>
        </table>

        <p>
          Healthcare is changing fast — and India is leading the way. 
          The Conference 
          is not just another event, but a 
          <span style="color:#D35400;"><b>movement where tradition meets technology</b></span> and ideas turn into action.
          Uniting <b>Ayurveda, Allopathy, Naturopathy, Nutrition</b> and <b>Digital Health</b>, 
          IPSA 2025 provides a unique platform for <b>doctors, students, researchers, entrepreneurs</b> 
          and <b>policymakers</b> to collaborate, learn, and shape the future of integrative healthcare.
        </p>

        <p style="margin-top:20px;">We look forward to welcoming you to the Conference.</p>

        <p style="margin-top:30px; font-weight:bold; color:#2E4053;">Warm regards, <br>
        Sai Ganga Panakeia Ltd</p>

        <hr style="margin-top:40px;"/>
        <p style="font-size:12px; color:#7F8C8D;">
          📍 Location: {location} | 📅 Date: {conference_date} <br>
          For any queries, contact us at <a href="mailto:ipsaevent@sgprs.com">ipsaevent@sgprs.com</a>
        </p>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Bcc"] = "sgpsmm@sgprs.com"

    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
            print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def store_registration(name: str, email: str, tier: str, amount: str, location: str, conference_date: str):
    try:
        data = {
            "name": name,
            "email": email,
            "tier": tier,
            "amount_paid": amount,
            "location": location,
            "conference_date": conference_date
        }
        supabase.table("registrations").insert(data).execute()
        print(f"✅ Stored registration in Supabase for {email}")
    except Exception as e:
        print(f"❌ Failed to store registration: {e}")

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

    FIXED_LOCATION = "T-HUB"
    FIXED_CONFERENCE_DATE = "2025-09-21"

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

        # store registration in Supabase
        store_registration(
            name=notes.get("name"),
            email=notes.get("email"),
            tier=notes.get("tier"),
            amount=notes.get("final_rupees"),
            location=notes.get("location"),
            conference_date=notes.get("conference_date"),
        )

        return {
            "status": "success",
            "order_id": payload.razorpay_order_id,
            "notes": notes,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {e}")

