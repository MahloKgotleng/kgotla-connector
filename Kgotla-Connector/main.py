
import os
import re
import time
import requests
import jwt

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

app = FastAPI(
    title="Kgotla AI Connector",
    version="1.3.0"
)

# --- Environment Variables ---
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY", "").replace("\\n", "\n")

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN", "")
ZOHO_API_DOMAIN = os.getenv(
    "ZOHO_API_DOMAIN", "https://www.zohoapis.com"
).rstrip("/")

ZOHO_ACCOUNTS_URL = "https://accounts.zoho.com"

# --- Request Models ---
class LeadForm(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=5, max_length=30)
    email: EmailStr
    company_or_school: str = Field(min_length=2, max_length=150)
    need: str = Field(min_length=5, max_length=2000)


# -------------------------------------------------------------
# 1. JWT Signing Endpoint
# -------------------------------------------------------------
@app.get("/jwt")
def generate_chat_jwt(user_id: str = "anonymous_visitor"):

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
# 2. Obtain Zoho Access Token
# -------------------------------------------------------------
def get_zoho_access_token():

    if not all([
        ZOHO_CLIENT_ID,
        ZOHO_CLIENT_SECRET,
        ZOHO_REFRESH_TOKEN
    ]):
        raise HTTPException(
            status_code=503,
            detail="Zoho CRM integration is not configured"
        )

    try:
        response = requests.post(
            f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
            data={
                "refresh_token": ZOHO_REFRESH_TOKEN,
                "client_id": ZOHO_CLIENT_ID,
                "client_secret": ZOHO_CLIENT_SECRET,
                "grant_type": "refresh_token"
            },
            timeout=15
        )

        response.raise_for_status()
        result = response.json()
        access_token = result.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=502,
                detail="Zoho authentication failed"
            )

        return access_token

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Unable to authenticate with Zoho CRM"
        )


# -------------------------------------------------------------
# 3. Create Lead in Zoho CRM
# -------------------------------------------------------------
@app.post("/lead")
def capture_lead(lead: LeadForm):

    access_token = get_zoho_access_token()

    name_parts = lead.name.strip().split(maxsplit=1)

    lead_data = {
        "Last_Name": (
            name_parts[0] if len(name_parts) == 1
            else name_parts[1]
        ),
        "Company": lead.company_or_school,
        "Email": str(lead.email),
        "Phone": lead.phone,
        "Description": lead.need
    }

    if len(name_parts) > 1:
        lead_data["First_Name"] = name_parts[0]

    payload = {"data": [lead_data]}

    try:
        response = requests.post(
            f"{ZOHO_API_DOMAIN}/crm/v8/Leads",
            json=payload,
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            },
            timeout=20
        )

        response.raise_for_status()
        result = response.json()
        records = result.get("data", [])

        if not records or records[0].get("status") != "success":
            raise HTTPException(
                status_code=502,
                detail="Zoho CRM could not create the lead"
            )

        return {
            "status": "success",
            "message": "Your enquiry has been received successfully"
        }

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Unable to submit your enquiry to Zoho CRM"
        )


# -------------------------------------------------------------
# 4. Health Check
# -------------------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Kgotla AI Connector"
    }


# -------------------------------------------------------------
# 5. Root Endpoint
# -------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Kgotla AI Connector",
        "version": "1.3.0"
    }

