
import os
import re
import time
import requests
import jwt

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field


app = FastAPI(
    title="Kgotla AI Connector",
    version="1.3.2"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://kgotlaai.co.za",
        "https://www.kgotlaai.co.za"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)


# -------------------------------------------------------------
# 1. Environment Variables
# -------------------------------------------------------------

JWT_PRIVATE_KEY = os.getenv(
    "JWT_PRIVATE_KEY", ""
).replace("\\n", "\n")

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN", "")

ZOHO_API_DOMAIN = os.getenv(
    "ZOHO_API_DOMAIN",
    "https://www.zohoapis.com"
).rstrip("/")

# Confirm this matches the data centre where your
# Zoho CRM account and refresh token were created.
ZOHO_ACCOUNTS_URL = os.getenv(
    "ZOHO_ACCOUNTS_URL",
    "https://accounts.zoho.com"
).rstrip("/")


# -------------------------------------------------------------
# 2. Request Model
# -------------------------------------------------------------

class LeadForm(BaseModel):

    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=5, max_length=30)
    email: EmailStr
    company_or_school: str = Field(min_length=2, max_length=150)
    need: str = Field(min_length=5, max_length=2000)


# -------------------------------------------------------------
# 3. JWT Signing Endpoint
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
# 4. Obtain Zoho Access Token
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

        try:
            result = response.json()
        except ValueError:
            result = {}

        access_token = result.get("access_token")

        if response.status_code != 200 or not access_token:

            error_code = result.get(
                "error",
                "unknown_error"
            )

            print(
                f"Zoho OAuth failed: "
                f"HTTP {response.status_code}, "
                f"error={error_code}"
            )

            raise HTTPException(
                status_code=502,
                detail=f"Zoho authentication failed: {error_code}"
            )

        return access_token

    except requests.RequestException as exc:

        print(
            f"Zoho OAuth connection error: "
            f"{type(exc).__name__}"
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to connect to Zoho authentication service"
        )


# -------------------------------------------------------------
# 5. Create Lead in Zoho CRM
# -------------------------------------------------------------

@app.post("/lead")
def capture_lead(lead: LeadForm):

    # Authenticate with Zoho
    access_token = get_zoho_access_token()

    # Split full name into first and last name
    name_parts = lead.name.strip().split(maxsplit=1)

    last_name = (
        name_parts[1]
        if len(name_parts) > 1
        else name_parts[0]
    )

    lead_data = {
        "Last_Name": last_name,
        "Company": lead.company_or_school,
        "Email": str(lead.email),
        "Phone": lead.phone,
        "Description": lead.need
    }

    if len(name_parts) > 1:
        lead_data["First_Name"] = name_parts[0]

    try:

        response = requests.post(
            f"{ZOHO_API_DOMAIN}/crm/v8/Leads",

            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            },

            json={
                "data": [lead_data]
            },

            timeout=20
        )

        try:
            result = response.json()
        except ValueError:
            result = {}

        # Check HTTP response
        if response.status_code not in (200, 201):

            print(
                f"Zoho CRM API failed: "
                f"HTTP {response.status_code}, "
                f"response={result}"
            )

            raise HTTPException(
                status_code=502,
                detail="Zoho CRM rejected the lead submission"
            )

        # Check Zoho application-level response
        records = result.get("data", [])

        if not records or records[0].get("status") != "success":

            print(
                "Zoho CRM lead creation failed:",
                records
            )

            raise HTTPException(
                status_code=502,
                detail="Zoho CRM could not create the lead"
            )

        # Successful lead creation
        return {
            "status": "success",
            "message": "Lead created successfully",
            "zoho_id": records[0].get(
                "details", {}
            ).get("id")
        }

    except requests.RequestException as exc:

        print(
            f"Zoho CRM connection error: "
            f"{type(exc).__name__}"
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to connect to Zoho CRM"
        )


# -------------------------------------------------------------
# 6. Health Check
# -------------------------------------------------------------

@app.get("/health")
def health_check():

    return {
        "status": "ok",
        "service": "Kgotla AI Connector",
        "version": "1.3.1"
    }


# -------------------------------------------------------------
# 7. Root Endpoint
# -------------------------------------------------------------

@app.get("/")
def root():

    return {
        "status": "ok",
        "service": "Kgotla AI Connector",
        "version": "1.3.1"
    }
