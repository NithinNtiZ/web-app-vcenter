
# OVF Deployment Web App for VMware vCenter

A Flask-based web application that deploys OVF templates to a VMware vSphere environment managed by vCenter. The app supports Azure AD-based SSO, MySQL backend, and allows users to spin up VMs using version, hardware model, and count as input.

## 🧰 Tech Stack

-   **Python 3.10+** - Core application runtime
-   **Flask** - Web framework
-   **VMware vSphere API** - vCenter integration
-   **MySQL** - Database backend
-   **Azure AD SSO** - Authentication via OAuth 2.0
-   **Gunicorn** - WSGI HTTP Server for production

## 🚀 Features

-   **OVF Template Deployment** - Deploy VMs from OVF images to vCenter
-   **Azure AD Single Sign-On** - Secure authentication and authorization
-   **Resource Management** - Resource pool, folder, and network selection
-   **Multi-Configuration Support** - Multiple OVF versions and hardware profiles
-   **Deployment Tracking** - MySQL database for tracking deployment history
-   **Web Interface** - User-friendly form-based VM provisioning
-   **Production Ready** - Gunicorn WSGI server with timeout handling

## ⚙️ Prerequisites

Before setting up the application, ensure you have:

-   **Python 3.8 or newer** installed
-   **vCenter Server** with REST API access enabled
-   **Azure AD App Registration** configured for SSO
-   **MySQL Server** set up and accessible
-   **Network connectivity** to vCenter and MySQL from the app server

## 🔧 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/vmware-ovf-deploy-app.git
cd vmware-ovf-deploy-app

```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

```

### 3. Install Dependencies

```bash
pip install -r requirements.txt

```

### 4. Configure Azure AD Application

Create a `config.py` file in the project root:

```python
# config.py
CLIENT_ID = 'your-azure-app-client-id'
CLIENT_SECRET = 'your-azure-app-client-secret'
AUTHORITY = 'https://login.microsoftonline.com/your-tenant-id'
REDIRECT_PATH = '/getAToken'
SCOPE = ['User.Read']
SESSION_TYPE = 'filesystem'
HOST = 'your.domain.com:5000'

```

### 5. Environment Variables

Create a `.env` file for sensitive database credentials:

```env
DB_HOST=10.0.0.1
DB_USER=root
DB_PASS=your-mysql-password

```

⚠️ **Important**: Never commit your `.env` file. Add it to `.gitignore` to keep credentials secure.

### 6. vCenter and Infrastructure Configuration

Create a `cred.json` file with your vCenter and infrastructure details:

```json
{
  "vc": "vcenter.example.com",
  "domain": "corp.example.com",
  "donald": "dns1.corp.example.com",
  "popepy": "vmadmin",
  "jerry": "SecurePass123!",
  "thanos": "192.168.100.0/24",
  "mgmt": "192.168.200.0/24",
  "folder": "example-vm-folder",
  "username": "svc.deploy@corp.example.com",
  "password": "ExampleSvc@2025#",
  "res_pool_list": ["resgroup-201", "resgroup-202", "resgroup-203"],
  "ds": "datastore-55",
  "network": "network-210",
  "sql_database": "vm_deploy_db"
}

```

### 7. Database Setup

Ensure your MySQL database is created and accessible:

```sql
CREATE DATABASE vm_deploy_db;
-- Grant appropriate permissions to your database user

```

## 🏃 Running the Application

### Development Mode

For local development and testing:

```bash
python app.py

```

### Production Mode

Use Gunicorn for production deployment:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app --timeout 1200

```

**Gunicorn Options Explained:**

-   `-w 4`: 4 worker processes
-   `-b 0.0.0.0:5000`: Bind to all interfaces on port 5000
-   `--timeout 1200`: 20-minute timeout for long-running VM deployments

## ✅ Usage

1.  **Access the Application** - Navigate to `http://your.domain.com:5000`
2.  **Azure AD Login** - Authenticate using your Azure AD credentials
3.  **VM Deployment Form** - Fill out the deployment form with:
    -   OVF version selection
    -   Hardware model/profile
    -   Number of VMs to deploy
    -   Resource pool and network settings
4.  **Submit Deployment** - Click deploy to start VM provisioning
5.  **Track Progress** - Monitor deployment status via the dashboard

## 🔐 Security Considerations

-   **Credentials Management** - Store sensitive data in environment variables and secure files
-   **Azure AD Integration** - Leverage enterprise SSO for secure authentication
-   **Network Security** - Ensure proper firewall rules for vCenter API access
-   **Database Security** - Use strong MySQL credentials and network isolation
-   **File Permissions** - Restrict access to configuration files containing secrets

## 📁 Project Structure

```
vmware-ovf-deploy-app/
├── app.py                 # Main Flask application
├── config.py              # Azure AD configuration
├── cred.json              # vCenter and infrastructure config
├── .env                   # Database credentials
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates
├── static/               # CSS, JS, images
├── .gitignore            # Git ignore rules
└── README.md             # This file

```

## 🛠️ Troubleshooting

### Common Issues

**Connection Errors to vCenter:**

-   Verify network connectivity to vCenter server
-   Check credentials in `cred.json`
-   Ensure vCenter API is enabled and accessible

**Azure AD Authentication Issues:**

-   Verify client ID and secret in `config.py`
-   Check redirect URI configuration in Azure AD
-   Ensure proper permissions are granted to the Azure AD app

**Database Connection Problems:**

-   Verify MySQL server is running and accessible
-   Check database credentials in `.env` file
-   Ensure database exists and user has proper permissions

**Deployment Timeouts:**

-   Increase Gunicorn timeout for large deployments
-   Check vCenter resources and capacity
-   Monitor network latency between app server and vCenter

**Note**: This application requires proper vCenter permissions and Azure AD configuration. Ensure all prerequisites are met before deployment.