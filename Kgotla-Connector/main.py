
import os
import re
import time
import requests
import jwt

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

app = FastAPI(
    title="Kgotla AI Connector",
    version="1.2.0"
)

# --- Environment Variables ---
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY", "").replace("\\n", "\n")
EVENT_NOTIFICATIONS_ENDPOINT = os.getenv(
    "EVENT_NOTIFICATIONS_ENDPOINT", ""
)

# --- Request Models ---
class LeadForm(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=5, max_length=30)
    email: EmailStr
    company_or_school: str = Field(min_length=2, max_length=150)
    need: str = Field(min_length=5, max_length=2000)


# -------------------------------------------------------------
# 1. JWT Signing Endpoint for Website Chat
# -------------------------------------------------------------
@app.get("/jwt")
def generate_chat_jwt(user_id: str = "anonymous_visitor"):
    """Generate a short-lived JWT for the Kgotla AI website chat."""

    if not JWT_PRIVATE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Chat authentication is not configured"
        )

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", user_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid visitor ID"
        )

    now = int(time.time())

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + 3600,
        "iss": "https://kgotlaai.co.za"
    }

    try:
        token = jwt.encode(
            payload,
            JWT_PRIVATE_KEY,
            algorithm="RS256"
        )
        return {"token": token}

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to generate chat authentication token"
        )


# -------------------------------------------------------------
# 2. Lead Capture Endpoint
# -------------------------------------------------------------
@app.post("/lead")
def capture_lead(lead: LeadForm):
    """
    Forward a website enquiry to a configured notification endpoint.

    A successful response means the receiving endpoint accepted
    the notification. It does not mean a permanent CRM record exists.
    """

    if not EVENT_NOTIFICATIONS_ENDPOINT:
        raise HTTPException(
            status_code=503,
            detail="Lead notification service is not configured"
        )

    payload = {
        "subject": (
            f"New Kgotla AI Enquiry: "
            f"{lead.name} ({lead.company_or_school})"
        ),
        "body": (
            f"Name: {lead.name}\n"
            f"Phone: {lead.phone}\n"
            f"Email: {lead.email}\n"
            f"Company/School: {lead.company_or_school}\n"
            f"Need/Details: {lead.need}"
        )
    }

    try:
        response = requests.post(
            EVENT_NOTIFICATIONS_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        response.raise_for_status()

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Lead notification could not be delivered"
        )

    return {
        "status": "accepted",
        "message": "Your enquiry has been forwarded successfully"
    }


# -------------------------------------------------------------
# 3. Health Check
# -------------------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Kgotla AI Connector"
    }


# -------------------------------------------------------------
# 4. Root Endpoint
# -------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Kgotla AI Connector",
        "version": "1.1.0"
    }
