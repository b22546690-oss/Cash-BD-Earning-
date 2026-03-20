from flask import Flask, request, jsonify
import os
import requests
import json
import time
import re
from datetime import datetime

app = Flask(__name__)

DB_URL = os.environ.get("DB_URL", "https://cash-5355f-default-rtdb.firebaseio.com")
DB_SECRET = os.environ.get("DB_SECRET", "5WwlOS8k66KYRgap4V4DmQffinLhMJNMQQW6GNdI")

def db_request(path, method="GET", data=None):
    url = f"{DB_URL}/{path}.json?auth={DB_SECRET}"
    headers = {'Content-Type': 'application/json'}
    
    if method == "GET":
        r = requests.get(url)
    elif method == "POST":
        r = requests.post(url, data=json.dumps(data), headers=headers)
    elif method == "PUT":
        r = requests.put(url, data=json.dumps(data), headers=headers)
    elif method == "PATCH":
        r = requests.patch(url, data=json.dumps(data), headers=headers)
    elif method == "DELETE":
        r = requests.delete(url)
        
    try:
        return r.json()
    except:
        return None

def sanitize_input(text, type="text"):
    if type == "username":
        return re.match(r'^[a-zA-Z0-9_]{5,20}$', text) is not None
    if type == "name":
        return re.match(r'^[a-zA-Z0-9\s.,:]{3,25}$', text) is not None
    return True

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    login_input = d.get('input', '').strip()
    password = d.get('password')
    
    users = db_request("users", "GET")
    
    found_user = None
    uid = None
    
    if users:
        for k, v in users.items():
            if (v.get('email') == login_input or v.get('username') == login_input) and v.get('password') == password:
                found_user = v
                uid = k
                break
    
    if found_user:
        return jsonify({"success": True, "uid": uid})
    return jsonify({"success": False, "message": "Invalid Credentials"})

@app.route('/api/register', methods=['POST'])
def register():
    d = request.json
    username = d.get('username', '').strip()
    email = d.get('email', '').strip()
    password = d.get('password')
    fullname = d.get('fullname', '').strip()
    ref_code_input = d.get('refCode', '').strip()
    
    if not sanitize_input(username, "username") or not sanitize_input(fullname, "name"):
        return jsonify({"success": False, "message": "Invalid Input Format"})

    users = db_request("users", "GET")
    if users:
        for v in users.values():
            if v.get('username') == username:
                return jsonify({"success": False, "message": "Username taken"})
            if v.get('email') == email:
                return jsonify({"success": False, "message": "Email already used"})

    referred_by_uid = None
    ref_msg = ""
    
    if ref_code_input:
        ref_codes = db_request("referralCodes", "GET")
        if ref_codes:
            for r_uid, r_code in ref_codes.items():
                if r_code == ref_code_input:
                    referred_by_uid = r_uid
                    break
        if not referred_by_uid:
            ref_msg = "Invalid Referral Code"

    import random
    import uuid
    new_ref_id = f"cash{random.randint(10000, 99999)}"
    uid = str(uuid.uuid4())
    
    new_user = {
        "username": username,
        "password": password, 
        "fullname": fullname,
        "email": email,
        "refId": new_ref_id,
        "referredBy": referred_by_uid,
        "isAccountActive": False,
        "balance": 0,
        "totalWithdraw": 0,
        "joinDate": datetime.now().isoformat(),
        "profilePictureUrl": "https://iili.io/fWs359j.jpg"
    }
    
    db_request(f"users/{uid}", "PUT", new_user)
    db_request(f"referralCodes/{uid}", "PUT", new_ref_id)
    
    if referred_by_uid:
        db_request(f"users/{referred_by_uid}/referrals/{uid}", "PUT", True)
        
    return jsonify({"success": True, "uid": uid, "refMessage": ref_msg})

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    uid = request.args.get('uid')
    if not uid: return jsonify({})
    
    user_data = db_request(f"users/{uid}", "GET")
    settings = db_request("admin", "GET")
    tasks = db_request("tasks", "GET")
    plans = db_request("plans", "GET")
    challenges = db_request("admin/referralChallenges", "GET")
    
    # Check for pending activation or plan requests
    pending_activation = False
    pending_plan = False
    
    transactions = db_request("transactions", "GET")
    if transactions:
        for t in transactions.values():
            if t.get('userId') == uid and t.get('status') == 'pending':
                if t.get('type') == 'Activation':
                    pending_activation = True
                if t.get('type') == 'Plan Purchase':
                    pending_plan = True

    if user_data and 'password' in user_data: del user_data['password']
    
    return jsonify({
        "user": user_data,
        "settings": settings,
        "tasks": tasks,
        "plans": plans,
        "challenges": challenges,
        "pendingActivation": pending_activation,
        "pendingPlan": pending_plan
    })

@app.route('/api/gmail_page', methods=['GET'])
def gmail_page():
    uid = request.args.get('uid')
    subs = db_request(f"users/{uid}/gmailSubmissions", "GET")
    g_settings = db_request("admin/gmailSettings", "GET")
    return jsonify({
        "submissions": subs,
        "settings": g_settings
    })

@app.route('/api/submit_gmail', methods=['POST'])
def submit_gmail():
    d = request.json
    uid = d.get('uid')
    email = d.get('email')
    
    g_settings = db_request("admin/gmailSettings", "GET")
    
    if g_settings.get('todayCount', 0) >= g_settings.get('globalLimit', 200):
        return jsonify({"success": False, "message": "Global Limit Reached"})
        
    submission = {
        "email": email,
        "price": g_settings.get('price', 5),
        "date": datetime.now().isoformat(),
        "status": "pending",
        "passwordUsed": g_settings.get('password')
    }
    
    db_request(f"users/{uid}/gmailSubmissions", "POST", submission)
    new_count = g_settings.get('todayCount', 0) + 1
    db_request("admin/gmailSettings/todayCount", "PUT", new_count)
    
    return jsonify({"success": True})

@app.route('/api/history', methods=['GET'])
def history():
    uid = request.args.get('uid')
    all_trx = db_request("transactions", "GET")
    my_trx = []
    if all_trx:
        for v in all_trx.values():
            if v.get('userId') == uid:
                my_trx.append(v)
    return jsonify(my_trx)

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    d = request.json
    uid = d.get('uid')
    amount = float(d.get('amount'))
    method = d.get('method')
    number = d.get('number')
    
    user = db_request(f"users/{uid}", "GET")
    settings = db_request("admin", "GET")
    
    if not user.get('isAccountActive'):
        return jsonify({"success": False, "message": "Inactive Account"})
        
    if user.get('balance', 0) < amount:
        return jsonify({"success": False, "message": "Low Balance"})
        
    if amount < settings.get('minWithdrawAmount', 100):
        return jsonify({"success": False, "message": "Amount too low"})
        
    trx = {
        "userId": uid,
        "type": "Withdrawal",
        "amount": -amount,
        "details": f"{method} to {number}",
        "date": datetime.now().isoformat(),
        "status": "pending"
    }
    db_request("transactions", "POST", trx)
    new_bal = user.get('balance', 0) - amount
    db_request(f"users/{uid}/balance", "PUT", new_bal)
    
    return jsonify({"success": True})

@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    d = request.json
    uid = d.get('uid')
    fullname = d.get('fullname', '').strip()
    username = d.get('username', '').strip()
    
    if not sanitize_input(username, "username") or not sanitize_input(fullname, "name"):
        return jsonify({"success": False, "message": "Invalid Format"})
    
    db_request(f"users/{uid}/fullname", "PUT", fullname)
    db_request(f"users/{uid}/username", "PUT", username)
    return jsonify({"success": True})

@app.route('/api/activate', methods=['POST'])
def activate():
    d = request.json
    uid = d.get('uid')
    amount = d.get('amount')
    method = d.get('method')
    trx_id = d.get('trxId')
    
    transactions = db_request("transactions", "GET")
    if transactions:
        for t in transactions.values():
            if t.get('userId') == uid and t.get('type') == 'Activation' and t.get('status') == 'pending':
                return jsonify({"success": False, "message": "Request already pending"})

    trx = {
        "userId": uid,
        "type": "Activation",
        "amount": amount,
        "details": "Activation Request",
        "trxId": trx_id,
        "method": method,
        "date": datetime.now().isoformat(),
        "status": "pending"
    }
    db_request("transactions", "POST", trx)
    return jsonify({"success": True})

@app.route('/api/buy_plan', methods=['POST'])
def buy_plan():
    d = request.json
    uid = d.get('uid')
    amount = d.get('amount')
    plan_name = d.get('planName')
    trx_id = d.get('trxId')
    method = d.get('method')

    transactions = db_request("transactions", "GET")
    if transactions:
        for t in transactions.values():
            if t.get('userId') == uid and t.get('type') == 'Plan Purchase' and t.get('status') == 'pending':
                return jsonify({"success": False, "message": "Request already pending"})

    trx = {
        "userId": uid,
        "type": "Plan Purchase",
        "amount": amount,
        "details": f"Plan: {plan_name}",
        "trxId": trx_id,
        "method": method,
        "date": datetime.now().isoformat(),
        "status": "pending"
    }
    db_request("transactions", "POST", trx)
    return jsonify({"success": True})

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    d = request.json
    uid = d.get('uid')
    tid = d.get('taskId')
    reward = float(d.get('reward'))
    
    user = db_request(f"users/{uid}", "GET")
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user.get('lastTaskDate') == today:
        return jsonify({"success": False, "message": "Daily limit reached"})
    
    completed = user.get('completedTasks', {})
    if tid in completed:
        return jsonify({"success": False, "message": "Already completed"})
        
    new_balance = user.get('balance', 0) + reward
    db_request(f"users/{uid}/balance", "PUT", new_balance)
    db_request(f"users/{uid}/lastTaskDate", "PUT", today)
    db_request(f"users/{uid}/completedTasks/{tid}", "PUT", True)
    
    return jsonify({"success": True, "newBalance": new_balance})

@app.route('/api/claim_daily', methods=['POST'])
def claim_daily():
    d = request.json
    uid = d.get('uid')
    amount = float(d.get('amount'))
    
    user = db_request(f"users/{uid}", "GET")
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user.get('lastClaimDate') == today:
        return jsonify({"success": False, "message": "Already claimed today"})
        
    new_balance = user.get('balance', 0) + amount
    db_request(f"users/{uid}/balance", "PUT", new_balance)
    db_request(f"users/{uid}/lastClaimDate", "PUT", today)
    
    return jsonify({"success": True})

@app.route('/api/claim_ref_reward', methods=['POST'])
def claim_ref_reward():
    d = request.json
    uid = d.get('uid')
    target = str(d.get('target'))
    reward = float(d.get('reward'))
    
    user = db_request(f"users/{uid}", "GET")
    
    claimed = user.get('dailyRefClaims', {})
    if claimed.get(target):
        return jsonify({"success": False, "message": "Already claimed"})
        
    new_balance = user.get('balance', 0) + reward
    db_request(f"users/{uid}/balance", "PUT", new_balance)
    db_request(f"users/{uid}/dailyRefClaims/{target}", "PUT", True)
    
    return jsonify({"success": True})
