import os
import secrets

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for
import msal


# ---------------------------------------------------------
# Load local configuration
# ---------------------------------------------------------

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# This project uses OIDC for authentication only.
# We are not requesting access to Microsoft Graph or another API.
SCOPES = []


# ---------------------------------------------------------
# Flask configuration
# ---------------------------------------------------------

app = Flask(__name__)

# Local lab session key.
# Production applications should use persistent,
# securely managed key material.
app.secret_key = secrets.token_hex(32)


# ---------------------------------------------------------
# MSAL confidential client
# ---------------------------------------------------------

def build_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        exclude_scopes=["offline_access"],
    )

# ---------------------------------------------------------
# Home page
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        user=session.get("user"),
    )


# ---------------------------------------------------------
# Start OIDC Authorization Code Flow
# ---------------------------------------------------------

@app.route("/login")
def login():
    msal_app = build_msal_app()

    flow = msal_app.initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        prompt="select_account",
    )

    if "error" in flow:
        return render_template(
            "error.html",
            error=flow.get("error"),
            error_description=flow.get("error_description"),
        )

    # Preserve the authorization flow in the Flask session.
    # MSAL uses this information when validating the callback.
    session["auth_flow"] = flow
    
    return redirect(flow["auth_uri"])


# ---------------------------------------------------------
# OIDC redirect/callback
# ---------------------------------------------------------

@app.route("/auth/callback")
def auth_callback():
    try:
        msal_app = build_msal_app()

        result = msal_app.acquire_token_by_auth_code_flow(
            session.get("auth_flow", {}),
            request.args,
        )

    except ValueError:
        return render_template(
            "error.html",
            error="authorization_response_validation_failed",
            error_description=(
                "The authorization response could not be validated. "
                "The request state may be missing or invalid."
            ),
        )

    if "error" in result:
        return render_template(
            "error.html",
            error=result.get("error"),
            error_description=result.get("error_description"),
        )

    claims = result.get("id_token_claims", {})

    session["user"] = {
        "name": claims.get("name"),
        "username": claims.get("preferred_username"),
        "tenant_id": claims.get("tid"),
        "object_id": claims.get("oid"),
        "issuer": claims.get("iss"),
        "audience": claims.get("aud"),
    }

    # Authentication flow data is no longer needed.
    session.pop("auth_flow", None)

    return redirect(url_for("index"))


# ---------------------------------------------------------
# Logout
# ---------------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()

    return redirect(
        f"{AUTHORITY}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={url_for('index', _external=True)}"
    )


# ---------------------------------------------------------
# Run local development server
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="localhost",
        port=5000,
        debug=True,
    )