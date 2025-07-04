from flask import Flask, render_template, redirect, url_for, session, request, flash, jsonify
import msal
import uuid
from gn import *
import config
from cred_db import *
import urllib3
import warnings 
from urllib3.exceptions import NotOpenSSLWarning
from dotenv import load_dotenv

load_dotenv()



warnings.simplefilter("ignore", NotOpenSSLWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


app = Flask(__name__)
app.secret_key = 'a_random_secret_key'
app.config.from_object(config)

base_url = f"http://{config.HOST}"
getnios_url = f"{base_url}/api/v1/getnios"
BASE_URL = f"https://{donald}/wapi/v2.6"


def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        config.CLIENT_ID,
        authority=config.AUTHORITY,
        client_credential=config.CLIENT_SECRET,
        token_cache=cache
    )

def _build_auth_url(scopes=None, state=None):
    return _build_msal_app().get_authorization_request_url(
        scopes or [],
        state=state or str(uuid.uuid4()),
        redirect_uri=url_for('authorized', _external=True)
    )


@app.route("/")
def index():
    if not session.get("user"):
        # return redirect(url_for("login"))
        return render_template("login.html", user=None)
    return render_template("index.html", user=session["user"])

@app.route("/login")
def login():
    session["state"] = str(uuid.uuid4())
    auth_url = _build_auth_url(scopes=config.SCOPE, state=session["state"])
    return redirect(auth_url)

@app.route(config.REDIRECT_PATH)
def authorized():
    if request.args.get('state') != session.get("state"):
        return redirect(url_for("index"))

    if "error" in request.args:
        return f"Login failed: {request.args['error_description']}"

    if "code" in request.args:
        cache = msal.SerializableTokenCache()
        result = _build_msal_app(cache=cache).acquire_token_by_authorization_code(
            request.args['code'],
            scopes=config.SCOPE,
            redirect_uri=url_for('authorized', _external=True)
        )
        if "id_token_claims" in result:
            session["user"] = result["id_token_claims"]
        else:
            return "Failed to authenticate."
    return redirect(url_for("index"))

@app.route("/logout")
def logout(): 
    session.clear() 
    return redirect(
        config.AUTHORITY + "/oauth2/v2.0/logout" +
        "?post_logout_redirect_uri=" + url_for("index", _external=True)
    )

@app.route("/create", methods=["POST"])
def create():
    version = request.form.get("version")
    hardware = request.form.get("hardware")
    count = int(request.form.get("count"))
    message = request.form.get("message")
    user = session.get("user", {})
    username = user.get("preferred_username", "user").split('@')[0]
    email = user.get("preferred_username", "Unknown Email")

    # vm_list = getnios(version, count, hardware, message, username)
    vm_list = deploy(version, hardware, count, message)
    return render_template("result.html",
                           version=version,
                           hardware=hardware,
                           count=count,
                           message=message,
                           username=username,
                           email=email,
                           vm_list=vm_list)

@app.route("/delete", methods=["POST"])
def delete():
    hostname = request.form.get("hostname", "").strip()

    if not hostname:
        flash("Hostname is required to delete a VM.", "warning")
        return redirect(url_for("index"))

    try:
        result = delete_vm_1(hostname)
        if "successfully" in result.lower():
            flash(f"✅ {result}", "info")
        else:
            flash(f"⚠️ {result}", "warning")
    except Exception as e:
        flash(f"❌ Error occurred while deleting VM '{hostname}': {e}", "danger")

    return redirect(url_for("index"))

@app.route("/extend", methods=["POST"])
def extend():
    hostname = request.form.get("hostname", "").strip()
    if not hostname:
        flash("Hostname is required to delete a VM.", "warning")
        return redirect(url_for("index"))

    try:
        result = vm_extend_default(hostname)
        if "successfully" in result.lower():
            flash(f"✅ {result}", "info")
        else:
            flash(f"⚠️ {result}", "warning")
    except Exception as e:
        flash(f"❌ Error occurred while deleting VM '{hostname}': {e}", "danger")
    return redirect(url_for("index"))



# API endpoint for live feed
@app.route("/api/user-vms", methods=["GET"])
def api_user_vms():
    """API endpoint to fetch user's VMs for the live feed"""
    
    # Check if user is authenticated
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 401
    
    # Get username from session
    user = session.get("user", {})
    username = user.get("preferred_username", "").split('@')[0]
    
    if not username:
        return jsonify({"error": "Username not found"}), 400
    
    try:
        # Fetch VMs for the user
        vms = get_user_vms(username)
        return jsonify({
            "success": True,
            "vms": vms,
            "count": len(vms)
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Failed to fetch VMs: {str(e)}",
            "success": False
        }), 500

@app.route("/api/lan-ip")
def api_lan_ip():
    if not session.get("user"):  # auth check
        return jsonify({"error": "unauthenticated"}), 401
    try:
        ip = get_lan_ip()
        flash(f"LAN IP: {ip}, Gatewate: 10.192.50.1, Subnet: 255.255.254.0", "info")
        return redirect(url_for("index"))
        # return jsonify({"success": True, "ip": ip})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/mgmt-ip")
def api_mgmt_ip():
    if not session.get("user"):
        return jsonify({"error": "unauthenticated"}), 401
    try:
        ip = get_mgmt_ip()
        flash(f"Management IP: {ip}, Gatewate: 10.192.61.1, Subnet: 255.255.255.0", "info")
        return redirect(url_for("index"))
        # return jsonify({"success": True, "ip": ip})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# New Console Routes
@app.route("/console/<vm_name>")
def console_redirect(vm_name):
    """Redirect to VM console - serves as a landing page"""
    if not session.get("user"):
        flash("Please log in to access VM console.", "warning")
        return redirect(url_for("login"))
    
    try:
        vm_details = get_vm_details(vm_name)
        if not vm_details:
            flash(f"VM '{vm_name}' not found or vCenter connection failed.", "danger")
            return redirect(url_for("index"))
        
        console_info = get_console_url(vm_details['vm_id'], vm_details['session_id'])

        if console_info and console_info.get('success'):
            # Create a simple HTML page that opens the console
            console_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>VM Console - {vm_name}</title>
                <style>
                    body {{ 
                        font-family: Arial, sans-serif; 
                        background: #1a1a1a; 
                        color: #ffffff; 
                        text-align: center; 
                        padding: 50px; 
                    }}
                    .console-info {{ 
                        background: #2d2d2d; 
                        padding: 30px; 
                        border-radius: 10px; 
                        margin: 20px auto; 
                        max-width: 600px; 
                        border: 2px solid #4a7c59; 
                    }}
                    .console-btn {{ 
                        background: linear-gradient(135deg, #66ff00, #4dcc00); 
                        color: #000; 
                        padding: 15px 30px; 
                        border: none; 
                        border-radius: 8px; 
                        font-size: 16px; 
                        font-weight: bold; 
                        cursor: pointer; 
                        text-decoration: none; 
                        display: inline-block; 
                        margin: 10px; 
                    }}
                    .back-btn {{ 
                        background: linear-gradient(135deg, #ff6b35, #f7931e); 
                        color: white; 
                    }}
                </style>
            </head>
            <body>
                <div class="console-info">
                    <h1>🖥️ VM Console Access</h1>
                    <h2>{vm_name}</h2>
                    <p>Console ticket generated successfully!</p>
                    <p><strong>Console URL: </strong> {console_info.get('ticket', 'N/A')}</p>
                    <br>
                    <a href="{console_info.get('ticket', '#')}" class="console-btn" target="_blank">
                        🚀 Open Console
                    </a>
                    <a href="{url_for('index')}" class="console-btn back-btn">
                        ← Back to Dashboard
                    </a>
                    <br><br>
                    <p><em>Note: Console will open in a new window/tab</em></p>
                </div>
            </body>
            </html>
            """
            return console_html
        else:
            error_msg = console_info.get('error', 'Unknown error') if console_info else 'Failed to get console access'
            flash(f"Failed to access console for '{vm_name}': {error_msg}", "danger")
            return redirect(url_for("index"))
            
    except Exception as e:
        flash(f"Error accessing console for '{vm_name}': {str(e)}", "danger")
        return redirect(url_for("index"))

@app.route("/api/console/<vm_name>")
def api_console(vm_name):
    """API endpoint to get console URL for a VM"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        vm_details = get_vm_details(vm_name)
        if not vm_details:
            return jsonify({
                "success": False, 
                "error": "VM not found or vCenter connection failed"
            }), 404
        
        console_info = get_console_url(vm_details['vm_id'], vm_details['session_id'])
        
        if console_info and console_info.get('success'):
            return jsonify({
                "success": True,
                "vm_name": vm_name,
                "console_url": console_info.get('console_url'),
                "ticket": console_info.get('ticket'),
                "port": console_info.get('port')
            })
        else:
            return jsonify({
                "success": False,
                "error": console_info.get('error', 'Failed to get console access')
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/console-ticket", methods=["POST"])
def api_console_ticket():
    """API endpoint to generate console ticket for a VM"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    vm_name = data.get('vm_name') if data else None
    
    if not vm_name:
        return jsonify({"success": False, "error": "VM name is required"}), 400
    
    try:
        vm_details = get_vm_details(vm_name)
        if not vm_details:
            return jsonify({
                "success": False, 
                "error": "VM not found or vCenter connection failed"
            }), 404
        
        console_info = get_console_url(vm_details['vm_id'], vm_details['session_id'])
        
        return jsonify(console_info if console_info else {
            "success": False, 
            "error": "Failed to generate console ticket"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True)

# gunicorn -w 4 -b 0.0.0.0:5000 app:app --timeout 1200