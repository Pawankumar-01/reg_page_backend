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
from typing import List, Optional


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
    phone: int
    email: str
    college: str | None = None
    type: str | None = None


class GroupMember(BaseModel):
    name: str
    email: str
    college: str | None = None
    type: str | None = None

class CreateOrderRequest(BaseModel):
    coupon: str | None = None
    name: str | None = None 
    phone: int| None = None 
    email: str | None = None
    college: str | None = None
    type: str | None = None
    group_members: list[GroupMember] | None = None
   
def group_discount_price(size: int) -> int:
    if 5 <= size <= 10:
        return 400   # 60% discount
    if size > 10:
        return 300   # 70% discount
    return 1000      # no group discount

def today_ist() -> date:
    # keep cutoffs in India time
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()

def current_tier_and_price(d: date | None = None) -> tuple[str, int]:
    d = d or today_ist()
    if d <= EARLY_END:
        return ("Early Bird", 1000)
    if d <= REGULAR_END:
        return ("Regular", 1000)
    return ("Late/Onsite", 1000)

def normalize(code: str | None) -> str:
    return (code or "").strip().upper()


def free_coupon_used_count() -> int:
    """Count how many people already registered with FREE coupon."""
    try:
        res = supabase.table("registrations").select("id", count="exact").eq("tier", "FREE").execute()
        return res.count or 0
    except Exception as e:
        print(f"⚠️ Failed to fetch free coupon usage: {e}")
        return 0

def validate_coupon(code: str | None) -> str | None:
    """
    Returns type of coupon:
    - "FREE" for free coupon
    - "DISCOUNT" for 50% discount coupon
    - None if invalid
    """
    code = normalize(code)
    if code == "FREEIPSA2025":
        if free_coupon_used_count() >=54:   # ✅ limit check
            return None
        return "FREE"
    if code == "IPSA2025":
        return "DISCOUNT"
    return None


def apply_coupon(base: int, coupon: str | None) -> tuple[int, int, str]:
    """
    Returns: (discount, final_amount, coupon_type)
    """
    if not coupon:
        return (0, base, "NONE")

    code = normalize(coupon)

    if code == "FREEIPSA2025":
        if free_coupon_used_count() >=54:   #  prevent overuse
            return (0, base, "NONE")
        return (base, 0, "FREE")

    if code == "IPSA2025":
        discount = base // 2
        return (discount, base - discount, "DISCOUNT")

    # Invalid coupon
    return (0, base, "NONE")

def group_discount_price(count: int) -> int:
    base = 1000
    if count >= 10:   # 10 or more
        return 300    # 70% off
    if count >= 5:    # 5 to 9
        return 400    # 60% off
    return base

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

def store_registration(name: str, email: str, phone:int, tier: str, amount: str, location: str, conference_date: str, college:str,type_: str | None = None):
    try:
        data = {
            "name": name,
            "email": email,
            "phone": phone,
            "tier": tier,
            "amount_paid": amount,
            "location": location,
            "conference_date": conference_date,
            "college" : college,
            "type": type_,
        }
        supabase.table("registrations").insert(data).execute()
        print(f"✅ Stored registration in Supabase for {email}")
    except Exception as e:
        print(f"❌ Failed to store registration: {e}")

@router.post("/quote")
def quote(body: CouponRequest):
    tier, base = current_tier_and_price()
    discount, final_amt, ctype = apply_coupon(base, body.coupon)
    return {
        "tier": tier,
        "base_rupees": base,
        "discount_rupees": discount,
        "final_rupees": final_amt,
        "coupon_type": ctype,
        "coupon_valid": ctype != "NONE"
    }

@router.post("/validate-coupon")
def validate(body: CouponRequest):
    tier, base = current_tier_and_price()
    discount, final_amt, ctype = apply_coupon(base, body.coupon)
    return {
        "valid": ctype != "NONE",
        "tier": tier,
        "base_rupees": base,
        "discount_rupees": discount,
        "final_rupees": final_amt,
        "coupon_type": ctype,
        "message": (
            "Free registration applied" if ctype == "FREE" else
            "Discount applied" if ctype == "DISCOUNT" else
            "Invalid coupon or free quota exhausted"
        )
    }

@router.post("/create-order")
def create_order(body: CreateOrderRequest):
    tier, base = current_tier_and_price()
    discount, final_amt_rupees, ctype = apply_coupon(base, body.coupon)

    FIXED_LOCATION = "T-HUB"
    FIXED_CONFERENCE_DATE = "2025-09-21"

    # --- FREE coupon path ---
    if ctype == "FREE":
        store_registration(
            name=body.name,
            email=body.email,
            phone=body.phone,
            tier="FREE",
            amount="0",
            location=FIXED_LOCATION,
            conference_date=FIXED_CONFERENCE_DATE,
            college=body.college,
            type_=body.type,  # capture if provided
        )

        send_ack_email(
            to_email=body.email,
            name=body.name,
            tier="FREE",
            location=FIXED_LOCATION,
            conference_date=FIXED_CONFERENCE_DATE,
            final_amount="0",
        )

        return {
            "status": "success",
            "message": "Registered with free coupon – no payment required.",
            "free_coupon": True,
        }
    # --- GROUP path ---
    if body.group_members and len(body.group_members) >= 2:
        size = len(body.group_members)
        price_per_head = group_discount_price(size)
        total_rupees = price_per_head * size

        amount_paise = total_rupees * 100
        try:
            order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {
                    "tier": f"Group ({size})",
                    "price_per_head": str(price_per_head),
                    "group_size": str(size),
                    "location": FIXED_LOCATION,
                    "conference_date": FIXED_CONFERENCE_DATE,
                    "phones": ",".join(str(m.phone) for m in body.group_members)
                }
            })
            return {
                "key": KEY_ID,
                "order": order,
                "amount": amount_paise,
                "display": {
                    "tier": f"Group ({size})",
                    "base_rupees": base,
                    "discount_rupees": (base - price_per_head),
                    "final_rupees": total_rupees,
                }
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

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
                    "phone": body.phone,
                    "college": body.college or "N/A",
                    "type": body.type or "N/A", 
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
    group_members: list[GroupMember] | None = None

@router.post("/verify-payment")
def verify_payment(payload: VerifyPayload):
    FIXED_LOCATION = "T-HUB"
    FIXED_CONFERENCE_DATE = "2025-09-21"

    try:
        order = client.order.fetch(payload.razorpay_order_id)
        notes = order.get("notes", {})
        if payload.group_members and len(payload.group_members) >= 5:
            size = len(payload.group_members)
            price_per_head = group_discount_price(size)

            for member in payload.group_members:
                send_ack_email(
                    to_email=member.email,
                    name=member.name,
                    tier=f"Group ({size})",
                    location=FIXED_LOCATION,
                    conference_date=FIXED_CONFERENCE_DATE,
                    final_amount=str(price_per_head),
                )
                store_registration(
                    name=member.name,
                    email=member.email,
                    phone=member.phone,
                    tier=f"Group ({size})",
                    amount=str(price_per_head),
                    location=FIXED_LOCATION,
                    conference_date=FIXED_CONFERENCE_DATE,
                    college=member.college,
                    type_=member.type,
                )

            return {
                "status": "success",
                "order_id": payload.razorpay_order_id,
                "group_size": size,
                "price_per_head": price_per_head,
            }

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
            college=notes.get("college"),
            type_=notes.get("type"),
        )

        return {
            "status": "success",
            "order_id": payload.razorpay_order_id,
            "notes": notes,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {e}")

###
@router.post("/test-registration")
def test_registration():
    store_registration(
        name="Dummy User",
        email="dummy@example.com",
        tier="Business",
        amount="1999.00",
        location="Bangalore",
        conference_date="2025-12-11",
        college="IIMS"
    )
    return {"status": "ok", "msg": "Fake registration stored ✅"}




class TestGroupMember(BaseModel):
    fullName: str
    email: str
    phone: Optional[str] = None
    type: Optional[str] = None
    college: Optional[str] = None

class TestGroupRequest(BaseModel):
    group_members: List[TestGroupMember]

@router.post("/payments/test-group-registration")
def test_group_registration(req: TestGroupRequest):
    FIXED_LOCATION = "T-HUB"
    FIXED_CONFERENCE_DATE = "2025-09-21"

    size = len(req.group_members)
    if size < 2:
        return {"status": "error", "detail": "Group must have at least 2 members"}

    price_per_head = group_discount_price(size)

    for member in req.group_members:
        send_ack_email(
            to_email=member.email,
            name=member.fullName,
            tier=f"Group-Test ({size})",
            location=FIXED_LOCATION,
            conference_date=FIXED_CONFERENCE_DATE,
            final_amount=str(price_per_head),
        )
        store_registration(
            name=member.fullName,
            email=member.email,
            tier=f"Group-Test ({size})",
            amount=str(price_per_head),
            location=FIXED_LOCATION,
            conference_date=FIXED_CONFERENCE_DATE,
            college=member.college or "N/A",
            type_=member.type or "N/A",
        )

    return {
        "status": "success",
        "test_mode": True,
        "group_size": size,
        "price_per_head": price_per_head,
        "message": f"✅ Test completed, emails sent and registrations stored for {size} members."
    }




