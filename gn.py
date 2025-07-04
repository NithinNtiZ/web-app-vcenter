from flask import session
import uuid
import requests
import mysql.connector
import logging
import random
import string
import json
import os
import time
import threading
import re
import sys
import config
from datetime import datetime, timedelta
from cred_db import *
import urllib3
import warnings
from urllib3.exceptions import NotOpenSSLWarning
from dotenv import load_dotenv
load_dotenv()
warnings.simplefilter("ignore", NotOpenSSLWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = f"http://{config.HOST}"
getnios_url = f"{base_url}/api/v1/getnios"
BASE_URL = f"https://{donald}/wapi/v2.6"

def db_con():    
    # db_host_s="10.192.36.101"
    # db_user = "root"
    # db_pass = "password"

    db_host_s= os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    try:
        return mysql.connector.connect(
        host= db_host_s,
        user= db_user,
        password= db_pass,
            )
    except Exception as e:
        return("Unable to connect to db")
    
def record_times():
    """Record the start and end times for the VM."""
    start_time = datetime.now().replace(microsecond=0)
    end_time = start_time + timedelta(hours=24)
    return start_time, end_time

def generate_hostname():
    """Generate a random hostname."""
    user = session.get("user", {})
    username = user.get("preferred_username", "user").split('@')[0]
    random_str = ''.join(random.choice(string.ascii_lowercase) for _ in range(3))
    return username, f"{username}-{random_str}"

def create_host(ip, hostname):
    """Create a host record in the network."""
    data = json.dumps({
        "ipv4addrs": [{"ipv4addr": ip}],
        "name": hostname,
        "view": "default",
        "ttl": 30
    })
    try:
        response = requests.post(
            f"https://{donald}/wapi/v2.6/record:host",
            data=data,
            auth=(popepy, jerry),
            verify=False
        )
    except Exception as e:
        logging.error(f"Error while creating A record : {e}")

def save_lan_ip_details(username, hostname, ip):
    date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    """Save VM details to the database."""
    conn = db_con()
    cursor = conn.cursor()
    insert_query = """
        INSERT INTO Loto.lan_ip (username, datecreated, hostname, ip)
        VALUES (%s, %s, %s, %s)
    """
    record = (username, date_created, hostname, ip )
    cursor.execute(insert_query, record)
    conn.commit()

def save_mgmt_ip_details(username, hostname, ip):
    date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    """Save VM details to the database."""
    conn = db_con()
    cursor = conn.cursor()
    insert_query = """
        INSERT INTO Loto.management_ip (username, datecreated, hostname, ip)
        VALUES (%s, %s, %s, %s)
    """
    record = (username, date_created, hostname, ip )
    cursor.execute(insert_query, record)
    conn.commit()

def get_next_available_ip(network): 
    """Get the next available IP address from the network."""
    netw = f"https://{donald}/wapi/v2.6/network?network={network}"
    netw_url = requests.get(netw, auth=(popepy, jerry), verify=False)
    netw_ref = netw_url.text.split("_ref\": \"")[1].split("\"")[0]
    next_avl_ip = f"https://{donald}/wapi/v2.6/{netw_ref}?_function=next_available_ip"
    next_avl_ip_url = requests.post(next_avl_ip, auth=(popepy, jerry), verify=False)
    if next_avl_ip_url.status_code != 200:
        print(next_avl_ip_url.text)
        logging.error(f"NIOS Grid unavailable or Unexpected HTTP Response: {next_avl_ip_url.status_code}")
    next_available_ip = next_avl_ip_url.json()['ips'][0]
    return next_available_ip

def get_lan_ip ():
    ip = get_next_available_ip(thanos)
    username, hostname = generate_hostname()
    hostname = f"{hostname}.{domain}"
    create_host(ip, hostname)
    save_lan_ip_details(username, hostname, ip)
    return ip

def get_mgmt_ip():
    ip = get_next_available_ip(mgmt)
    username, hostname = generate_hostname()
    hostname = f"{hostname}.{domain}"
    create_host(ip, hostname)
    save_mgmt_ip_details(username, hostname, ip)
    # delete_host(hostname)
    return ip

def get_user_vms(username):
    """Fetch VMs for a specific user from the database"""
    try:
        conn = db_con()
        if isinstance(conn, str):  # Error connecting to DB
            return []
        
        cursor = conn.cursor(dictionary=True)
        
        # Query to get user's VMs - adjust table name and columns as needed
        query = """
        SELECT 
            vmname as hostname,
            nios_version as version,
            hw_model as hardware,
            status as status,
            case_no as message,
            start_time as created_at,
            end_time as end_time,
            ip as ip,
            username
        FROM Loto.vm_info 
        WHERE username = %s 
        ORDER BY created_at DESC
        """
        
        cursor.execute(query, (username,))
        vms = cursor.fetchall()
        # Convert datetime objects to strings for JSON serialization
        for vm in vms:
            if vm.get('created_at'):
                vm['created_at'] = vm['created_at'].isoformat()
            
            # Normalize status values
            if vm.get('status'):
                vm['status'] = vm['status'].lower()
            else:
                vm['status'] = 'pending'
        
        cursor.close()
        conn.close()
        
        return vms
        
    except Exception as e:
        print(f"Error fetching user VMs: {e}")
        return []

def delete_host(VM_NAME):
    try:
        # Fetch the host record
        response = requests.get(
            f"{BASE_URL}/record:host?name={VM_NAME}&_return_as_object=1",
            auth=(popepy, jerry),
            verify=False
        )
        response.raise_for_status()
        data = response.json()
        # sys.exit(data['result'])
        # Extract the value of '_ref'
        try:
            ref_value = data['result'][0]['_ref']
            # Delete the host record
            delete_response = requests.delete(
                f"{BASE_URL}/{ref_value}",
                auth=(popepy, jerry),
                verify=False
            )
            delete_response.raise_for_status()
            return delete_response.json()
        except IndexError :
            print(f"unable to find ref for this record in the server : {data}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def getnios(version, count, hw_model, mes, username):
    payload = {
        "Version": version,
        "Count": count,
        "Hardware": hw_model,
        "Message": mes,
        "Username": username
    }
    headers = {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'your_csrf_token_here'
    }
    try:
        res = requests.post(getnios_url, json=payload, headers=headers)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"error": str(e)}

def get_vm_end_date(hostname):
    conn = db_con()
    cursor = conn.cursor()
    query = """
        SELECT end_time, lease_duration FROM Loto.vm_info WHERE vmname = %s
    """
    cursor.execute(query, (hostname,))
    res = cursor.fetchall()
    if not res:
        raise ValueError(f"No VM found with hostname: {hostname}")
    return res  # Result will be a list of tuples

def update_vm_info(new_date, new_hr, vmname):
    conn = db_con()
    cursor = conn.cursor()
    query = """
        UPDATE Loto.vm_info
        SET end_time = %s, lease_duration = %s
        WHERE vmname = %s
    """
    cursor.execute(query, (new_date, new_hr, vmname))
    conn.commit()
    return cursor.rowcount  # Number of rows affected

def vm_extend_default(vm_name):
    res = get_vm_end_date(vm_name)
    date, hr = res[0]
    new_hr = int(hr + 48)
    extend_hr = 48
    if new_hr <= 72:
        new_date = date + timedelta(hours=extend_hr)
        update_vm_info(new_date, new_hr, vm_name)
        return f"VM {vm_name} extended for {new_hr} hours and will expire on {new_date}"
    else:
        return "Create Jira ticket for extending appliance for more than 3 days"

def session_create():
    """Create a vCenter session and return session ID"""
    url = f"https://{vc}/api/session"
    payload = {}
    headers = {
    'Authorization': 'Basic YWRtaW5pc3RyYXRvckBzdXBwb3J0bGFiLmluZm9ibG94LmNvbTpJbmZvYmxveGVzeGlAMjAyNCMx'
    }
    try:
        response = requests.request("POST", url, headers=headers, data=payload, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error creating vCenter session: {e}")
        return None

def get_vm_id(header_1, vm_name):
    """Get VM ID by VM name"""
    url = f"https://{vc}/api/vcenter/vm?names={vm_name}"
    payload = {}
    try:
        response = requests.request("GET", url, headers=header_1, data=payload, verify=False)
        response.raise_for_status()
        vm_data = response.json()
        return vm_data[0]['vm'] if vm_data else None
    except (requests.exceptions.RequestException, IndexError, KeyError) as e:
        logging.error(f"Error getting VM ID for {vm_name}: {e}")
        return None

def stop_vm(session_id, vm_id):
    """Stop a VM"""
    url = f'https://{vc}/api/vcenter/vm/{vm_id}/power?action=stop'
    headers = {'vmware-api-session-id': session_id, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, verify=False)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Error stopping VM {vm_id}: {e}")
        return False
def power_on_vm(session_id, vm_id):
    url = f'https://{vc}/api/vcenter/vm/{vm_id}/power?action=start'
    headers = {
        'vmware-api-session-id': session_id,
        'Content-Type': 'application/json'
    }
    response = requests.post(url, headers=headers, verify=False)

    logging.debug(f"Status Code: {response.status_code}")
    logging.debug(f"Response Text: {response.text}")

    if response.status_code == 204:
        logging.info(f"Successfully powered on VM {vm_id}")
        return {"message": "Power on initiated successfully", "vm_id": vm_id}

    else:
        try:
            error_response = response.json()
        except requests.exceptions.JSONDecodeError:
            error_response = {"error": "Invalid JSON response", "raw": response.text}

        logging.error(f"Failed to power on VM {vm_id}: {response.status_code} - {error_response}")
        return error_response

def delete_vm(vcenter, session_id, vm_id):
    """Delete a VM"""
    url = f'https://{vcenter}/api/vcenter/vm/{vm_id}'
    headers = {'vmware-api-session-id': session_id}
    try:
        response = requests.delete(url, headers=headers, verify=False)
        response.raise_for_status()
        return response.json() if response.status_code == 200 else True
    except requests.exceptions.RequestException as e:
        logging.error(f"Error deleting VM {vm_id}: {e}")
        return False

def update_status(VM_NAME):
    """Update VM status in database"""
    try:
        conn = db_con()
        if isinstance(conn, str):  # Error connecting to DB
            return False
        cursor = conn.cursor()
        update_query = "UPDATE Loto.vm_info SET Status = 'Deleted' WHERE vmname = %s"
        cursor.execute(update_query, (VM_NAME,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error updating status for {VM_NAME}: {e}")
        return False

def get_console_url(vm_id, session_id=None):
    """Get console URL for a VM"""
    if not session_id:
        session_id = session_create()
    
    if not session_id:
        return None
    
    url = f"https://{vc}/api/vcenter/vm/{vm_id}/console/tickets"
    headers = {
        'vmware-api-session-id': session_id,
        'Content-Type': 'application/json'
    }
    payload = {
        "type": "VMRC"
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
        
        if response.status_code == 201:
            console_data = response.json()
            return {
                'success': True,
                'console_url': console_data.get('url'),
                'ticket': console_data.get('ticket'),
                'port': console_data.get('port')
            }
        elif response.status_code == 404:
            return {'success': False, 'error': 'VM not found'}
        else:
            return {'success': False, 'error': f'HTTP {response.status_code}: {response.text}'}
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Error getting console URL for VM {vm_id}: {e}")
        return {'success': False, 'error': str(e)}

def get_vm_details(vm_name):
    """Get VM details including VM ID"""
    session_id = session_create()
    if not session_id:
        return None
    
    headers = {'vmware-api-session-id': session_id}
    vm_id = get_vm_id(headers, vm_name)
    
    if not vm_id:
        return None
    
    return {
        'vm_id': vm_id,
        'session_id': session_id,
        'vm_name': vm_name
    }

def delete_vm_1(vm_name):
    """Enhanced delete VM function with better error handling"""
    try:
        session_id = session_create()
        if not session_id:
            update_status(vm_name)
            return f"Failed to create vCenter session for {vm_name}"
        
        header_1 = {"vmware-api-session-id": session_id}
        vm_id = get_vm_id(header_1, vm_name)
        
        if vm_id:
            # Try to stop VM
            try:
                stop_vm(session_id, vm_id)
                logging.info(f"VM {vm_name} stopped successfully")
            except Exception as e:
                logging.warning(f"Failed to stop VM {vm_name}: {e}")
            
            # Try to delete host record
            try:
                delete_host(vm_name)
                logging.info(f"Host record for {vm_name} deleted successfully")
            except Exception as e:
                logging.warning(f"Failed to delete host record for {vm_name}: {e}")
            
            # Try to delete VM
            try:
                delete_vm(vc, session_id, vm_id)
                update_status(vm_name)
                logging.info(f"VM {vm_name} deleted successfully")
                return f"VM {vm_name} deleted successfully."
            except Exception as e:
                update_status(vm_name)
                logging.error(f"Failed to delete VM {vm_name}: {e}")
                return f"VM {vm_name} marked as deleted but may still exist in vCenter."
        else:
            update_status(vm_name)
            return f"VM {vm_name} not found in vCenter."
            
    except Exception as e:
        update_status(vm_name)
        logging.error(f"Unexpected error while deleting VM {vm_name}: {e}")
        return f"Error occurred while deleting VM {vm_name}: {str(e)}"

def save_execution_time(session_id, hostname, execution_time):

    """Save VM execution time details to the database."""
    conn = db_con()
    cursor = conn.cursor()
    insert_query = """
        INSERT INTO Loto.vm_execution_time (session_id, vmname, deploy_time)
        VALUES (%s, %s, %s)
    """
    record = (session_id, hostname, execution_time )
    cursor.execute(insert_query, record)
    conn.commit()
    cursor.close()

def save_details(hostname, username, ip, message, version, hw_model, start_time, end_time, lease_duration, time_remaining, default_Status):
    """Save VM details to the database."""
    conn = db_con()
    cursor = conn.cursor()
    insert_query = """
        INSERT INTO Loto.vm_info (vmname, username, ip, case_no, nios_version, hw_model, start_time, end_time, lease_duration, time_remaining, Status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    record = (hostname, username, ip, message, version, hw_model, start_time, end_time, lease_duration, time_remaining, default_Status)
    cursor.execute(insert_query, record)
    conn.commit()

def get_lib(header_1):
    url = f"https://{vc}/api/content/library"
    payload = {}
    response = requests.request("GET", url, headers=header_1, data=payload, verify=False)
    return response.json()[0]

def get_lib_item_id(header_1):
    library_id = get_lib(header_1)
    url = f"https://{vc}/api/content/library/item?library_id={library_id}"
    payload = {}
    response = requests.request("GET", url, headers=header_1, data=payload, verify=False)
    return response.json()

def get_item_name(header_1, item_id):
    url = f"https://{vc}/api/content/library/item/{item_id}"
    payload = {}
    response = requests.request("GET", url, headers=header_1, data=payload, verify=False)
    return response.json()

def find_item_by_version(version: str) -> str | None:
    header_1 = { 
    "vmware-api-session-id" : session_create()
}
    """Return the item‑ID matching nios‑<version>, or None if not found."""
    allowed = {f"9.0.{i}" for i in range(8)}        # 9.0.0‑9.0.7
    if version not in allowed:
        print(f"❌  {version} is invalid — choose 9.0.0 through 9.0.7")
        sys.exit(1)
    pattern = re.compile(fr"^nios-{re.escape(version)}(?!\d)")  # exact patch, block 9.0.70 …

    for item_id in get_lib_item_id(header_1):
        item = get_item_name(header_1, item_id)
        name = item["name"]
        # print(f"Item Name: {name}, Item ID: {item['id']}")
        if pattern.search(name):
            # print(f"✅  Match found for {version}: {name}")
            return item["id"]

    print(f"❌  No library item found for {version}")
    return None

def add_disk(vm_id):
    url = f"https://{vc}/api/vcenter/vm/{vm_id}/hardware/disk"
    header_1 = {
        'Content-Type': 'application/json',
        "vmware-api-session-id": session_create()
    }
    payload = json.dumps({
    "new_vmdk": {
        "capacity": 268435456000,
        "name": "reporting-disk"
    },
    "scsi": {
        "bus": 0,
        "unit": 1
    },
    "type": "SCSI"
    })

    response = requests.request("POST", url, headers=header_1, data=payload, verify=False)

    return response.json()

def deploy_ovf_vapi(session_id_2, hw_model, item_id, vm_name, lan_ip):
    url = f"https://{vc}/api/vcenter/ovf/library-item/{item_id}?action=deploy"
    res_pool = random.choice(res_pool_list)
    payload = {
        "target": {
            "folder_id": "group-v8001",
            "resource_pool_id": res_pool,
        },
        "deployment_spec": {
            "accept_all_EULA": True,
            "name": vm_name,
            "default_datastore_id": f"{ds}",
            "storage_provisioning": "thin",
            "network_mappings": {
                "VM Network": f"{network}"
            },
            "additional_parameters": [
                {
                    "type": "PropertyParams",
                    "properties": [
                        {"id": "hardware_type", "value": ""},
                        {"id": "temp_license", "value": f"dns dhcp nios IB-V{hw_model} enterprise"},
                        {"id": "remote_console_enabled", "value": "True"},
                        {"id": "default_admin_password", "value": "infoblox"},
                        {"id": "gridmaster-certificate", "value": ""},
                        {"id": "gridmaster-ip_addr", "value": ""},
                        {"id": "gridmaster-token", "value": ""},
                        {"id": "lan1-v4_addr", "value": lan_ip},
                        {"id": "lan1-v4_gw", "value": "10.192.50.1"},
                        {"id": "lan1-v4_netmask", "value": "255.255.254.0"},
                        {"id": "lan1-v6_cidr", "value": ""},
                        {"id": "lan1-v6_gw", "value": ""},
                        {"id": "lan1-v6_addr", "value": ""},
                        {"id": "mgmt-v4_addr", "value": ""},
                        {"id": "mgmt-v4_gw", "value": ""},
                        {"id": "mgmt-v4_netmask", "value": ""},
                        {"id": "mgmt-v6_cidr", "value": ""},
                        {"id": "mgmt-v6_gw", "value": ""},
                        {"id": "mgmt-v6_addr", "value": ""},
                        {"id": "lan2-v4_addr", "value": ""},
                        {"id": "lan2-v4_gw", "value": ""},
                        {"id": "lan2-v4_netmask", "value": ""},
                        {"id": "lan2-v6_cidr", "value": ""},
                        {"id": "lan2-v6_gw", "value": ""},
                        {"id": "lan2-v6_addr", "value": ""}
                    ]
                },
                {
                    "type": "DeploymentOptionParams",
                    "selected_key": f"{hw_model}"
                }
            ]
        }
    }

    headers = {
        'Content-Type': 'application/json',
        'vmware-api-session-id': session_create()
    }
    start = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
    # print(response.json())
    execution_time = time.time() - start
    # print(f"Execution time: {execution_time} seconds")
    save_execution_time(session_id_2, vm_name, execution_time)
    return response.json()

def deploy(version, models, counts, message):
    
    names = []
    header_1 = { 
        "vmware-api-session-id" : session_create()
    }
    session_id = session_create()
    item_id = find_item_by_version(version)

    threads = []
    vm_names : list = []
    session_id_2 = uuid.uuid4().int
    if models in ["805", "1405"]:
        for _ in range(int(counts)):   
            lan_ip = get_next_available_ip(thanos)
            username, vm_name = generate_hostname()
            vm_name = f"{vm_name}.{domain}"
            start_time, end_time = record_times()
            lease_duration = 24
            lease_duration_seconds = 86400
            vm_names.append({"hostname": vm_name, "ip": lan_ip})
            create_host(lan_ip, vm_name)
            thread = threading.Thread(target=deploy_ovf_vapi, args=(session_id_2, models, item_id, vm_name, lan_ip))
            threads.append(thread)
            thread.start()
            default_Status = "Running"
            try :
                save_details(vm_name, username, lan_ip, message, version, models, start_time, end_time, lease_duration, lease_duration_seconds, default_Status)
            except Exception as e:
                sys.exit (f"failed to save details : {e}")

        for thread in threads:
            thread.join()

        for vm_name in vm_names:
            vm_id = get_vm_id(header_1, vm_name['hostname'])
            if not vm_id:
                print(f"VM {vm_name} not found in vCenter.")
                continue
            res = add_disk(vm_id)
            # print(f"Disk added: {res}")
            power_on_vm(session_id, vm_id)
        return vm_names
    else:
        for _ in range(int(counts)):
            lan_ip = get_next_available_ip(thanos)
            username, vm_name = generate_hostname()
            vm_name = f"{vm_name}.{domain}"
            start_time, end_time = record_times()
            lease_duration = 24
            lease_duration_seconds = 86400
            vm_names.append({"hostname": vm_name, "ip": lan_ip})
            create_host(lan_ip, vm_name)
            thread = threading.Thread(target=deploy_ovf_vapi, args=(session_id, models, item_id, vm_name, lan_ip))
            threads.append(thread)
            thread.start()
            default_Status = "Running"
            try :
                save_details(vm_name, username, lan_ip, message, version, models, start_time, end_time, lease_duration, lease_duration_seconds, default_Status)
            except Exception as e:
                sys.exit (f"failed to save details : {e}")

        for thread in threads:
            thread.join()

        for vm_name in vm_names:
            vm_id = get_vm_id(header_1, vm_name['hostname'])
            power_on_vm(session_id, vm_id)
        return vm_names