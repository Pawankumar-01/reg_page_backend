from fastapi import BackgroundTasks
import smtplib
from email.mime.text import MIMEText

def send_acknowledgement_email(reg: dict):
    body = f"""
    Dear {reg['name']},

    Thank you for registering for the conference.

    📍 Location: {reg['location']}
    📅 Date: {reg['conference_date']}
    🎟️ Tier: {reg['tier']}
    💰 Base Price: ₹{reg['base_rupees']}
    🎁 Discount: ₹{reg['discount_rupees']}
    ✅ Final Amount Paid: ₹{reg['final_rupees']}
    📌 Coupon Used: {reg['coupon'] if reg['coupon'] else "None"}
    🆔 Payment ID: {reg['razorpay_payment_id']}

    Regards,  
    Conference Team
    """

    msg = MIMEText(body)
    msg["Subject"] = "Conference Registration Acknowledgement"
    msg["From"] = "no-reply@conference.com"
    msg["To"] = reg["email"]

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login("your-email@gmail.com", "your-app-password")
        server.send_message(msg)
