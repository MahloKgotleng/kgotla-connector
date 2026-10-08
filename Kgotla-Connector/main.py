import os
import time
import requests
import jwt
from fastapi import FastAPI, Request, HTTPException, Query, Response
from pydantic import BaseModel

app = FastAPI(title="Kgotla AI Connector", version="1.0.0")

# --- Environment Variables (Injected from Secrets Manager) ---
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "kgotla_wa_verify_secret")
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY", "").replace("\\n", "\n")
EVENT_NOTIFICATIONS_ENDPOINT = os.getenv("EVENT_NOTIFICATIONS_ENDPOINT", "")
EVENT_NOTIFICATIONS_IAM_KEY = os.getenv("EVENT_NOTIFICATIONS_IAM_KEY", "")

# --- Request Models ---
class LeadForm(BaseModel):
    name: str
    phone: str
    email: str
    company_or_school: str
    need: str

# -------------------------------------------------------------
# 1. WhatsApp Webhook Endpoint
# -------------------------------------------------------------
@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """Meta verification handshake"""
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request):
    """Receive incoming WhatsApp messages from Meta API"""
    data = await request.json()
    
    # Process incoming WhatsApp payload
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        
        if messages:
            msg = messages[0]
            sender_id = msg.get("from")  # Sender phone number
            text_body = msg.get("text", {}).get("body", "")
            
            # Log & process message with watsonx agent
            print(f"Incoming WhatsApp message from {sender_id}: {text_body}")
            
    except Exception as e:
        print(f"Error processing WhatsApp payload: {e}")
        
    return {"status": "success"}

# -------------------------------------------------------------
# 2. JWT Signing Endpoint for Web Chat Embed
# -------------------------------------------------------------
@app.get("/jwt")
async def generate_chat_jwt(user_id: str = "anonymous_visitor"):
    """Generates signed RSA JWT for kgotlaai.co.za webchat widget security"""
    if not JWT_PRIVATE_KEY:
        raise HTTPException(status_code=500, detail="JWT Signing Key not configured")
        
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + 3600,  # Valid for 1 hour
        "iss": "https://kgotlaai.co.za"
    }
    
    token = jwt.encode(payload, JWT_PRIVATE_KEY, algorithm="RS256")
    return {"token": token}

# -------------------------------------------------------------
# 3. Lead Capture Endpoint (Form Submissions)
# -------------------------------------------------------------
@app.post("/lead")
async def capture_lead(lead: LeadForm):
    """Receives book-a-demo submissions and sends email via Event Notifications"""
    payload = {
        "subject": f"New Lead Captured: {lead.name} ({lead.company_or_school})",
        "body": (
            f"Name: {lead.name}\n"
            f"Phone: {lead.phone}\n"
            f"Email: {lead.email}\n"
            f"Company/School: {lead.company_or_school}\n"
            f"Need/Details: {lead.need}\n"
        )
    }
    
    # Send lead notification if endpoint configured
    if EVENT_NOTIFICATIONS_ENDPOINT:
        try:
            requests.post(
                EVENT_NOTIFICATIONS_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
        except Exception as e:
            print(f"Failed to dispatch event notification: {e}")
            
    return {"status": "received", "message": "Lead captured successfully"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Kgotla AI Code Engine Connector"}