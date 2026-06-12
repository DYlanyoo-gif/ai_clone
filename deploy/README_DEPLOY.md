# Echo Profile Production Deployment

This guide deploys Echo Profile on a VPS with:

- React/Vite frontend built to `frontend/dist`
- Nginx serving static frontend files
- Nginx reverse proxying `/api` to FastAPI on `127.0.0.1:8000`
- FastAPI running under `systemd`
- secrets stored only in `/opt/ai_clone/.env`
- optional Nginx Basic Auth to protect demo/API quota

Production users should visit the domain, for example `https://echo.example.com`. Do not expose Vite dev port `5173` in production.

## 1. Install VPS Dependencies

Example for Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip nodejs npm
```

Recommended for HTTPS and Basic Auth:

```bash
sudo apt install -y certbot python3-certbot-nginx apache2-utils
```

Check versions:

```bash
python3 --version
node --version
npm --version
nginx -v
```

## 2. Clone the Project

```bash
cd /opt
sudo git clone --recurse-submodules https://github.com/YOUR_ACCOUNT/YOUR_REPO.git ai_clone
sudo chown -R $USER:$USER /opt/ai_clone
cd /opt/ai_clone
```

If the repo was cloned without submodules:

```bash
git submodule update --init --recursive
```

## 3. Create Production `.env`

Copy the template:

```bash
cp .env.production.example .env
nano .env
```

Fill in your DeepSeek API key on the VPS only:

```env
LLM_API_KEY=sk-your-real-key
APP_PUBLIC_BASE_URL=https://echo.example.com
SHOW_ADMIN_DIAGNOSTICS=false
```

Do not commit `.env` or API keys to GitHub.

## 4. Install Python Dependencies

```bash
cd /opt/ai_clone/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r /opt/ai_clone/requirements.txt
```

Optional integrations such as Qdrant/FastEmbed and mem0 should remain disabled unless you intentionally enable and install them:

```env
VECTOR_ENABLED=false
MEM0_ENABLED=false
```

## 5. Build the Frontend

```bash
cd /opt/ai_clone/frontend
npm install
npm run build
```

The production static files are created in:

```text
/opt/ai_clone/frontend/dist
```

## 6. Configure systemd for FastAPI

Copy the example service:

```bash
sudo cp /opt/ai_clone/deploy/systemd-backend.service.example /etc/systemd/system/ai-clone-backend.service
```

Review it:

```bash
sudo nano /etc/systemd/system/ai-clone-backend.service
```

The important settings are:

```ini
WorkingDirectory=/opt/ai_clone/backend
EnvironmentFile=/opt/ai_clone/.env
ExecStart=/opt/ai_clone/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
```

Start and enable the backend:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-clone-backend
sudo systemctl start ai-clone-backend
sudo systemctl status ai-clone-backend
```

The backend should listen only on localhost:

```bash
curl http://127.0.0.1:8000/api/config/status
```

## 7. Configure Nginx

Copy the example site config:

```bash
sudo cp /opt/ai_clone/deploy/nginx.conf.example /etc/nginx/sites-available/echo-profile
sudo nano /etc/nginx/sites-available/echo-profile
```

Change:

```nginx
server_name echo.example.com;
root /opt/ai_clone/frontend/dist;
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/echo-profile /etc/nginx/sites-enabled/echo-profile
sudo nginx -t
sudo systemctl reload nginx
```

The Nginx config:

- serves the React build from `/opt/ai_clone/frontend/dist`
- supports React Router with `try_files $uri $uri/ /index.html`
- proxies `/api/` to `http://127.0.0.1:8000/api/`
- limits upload size with `client_max_body_size 25M`
- denies access to `.env`, `.git`, `data`, `uploads`, and `generated_skills`

## 8. Configure Domain DNS

In your DNS provider, add an A record:

```text
Type: A
Name: echo
Value: YOUR_VPS_PUBLIC_IP
TTL: Auto
```

After DNS propagation:

```bash
curl -I http://echo.example.com
```

## 9. Enable HTTPS

Use Certbot:

```bash
sudo certbot --nginx -d echo.example.com
```

Certbot will update Nginx and configure certificate renewal.

Verify:

```bash
sudo certbot renew --dry-run
```

## 10. Optional Basic Auth

For a resume/demo site, Basic Auth is recommended to prevent strangers from using your API quota.

Create a password file:

```bash
sudo htpasswd -c /etc/nginx/.htpasswd echo
```

Uncomment this block in `/etc/nginx/sites-available/echo-profile`:

```nginx
auth_basic "Echo Profile";
auth_basic_user_file /etc/nginx/.htpasswd;
```

Reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 11. View Logs

Backend:

```bash
sudo journalctl -u ai-clone-backend -f
sudo systemctl status ai-clone-backend
```

Nginx:

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## 12. Update Deployment

```bash
cd /opt/ai_clone
git pull --recurse-submodules
git submodule update --init --recursive

cd /opt/ai_clone/backend
source venv/bin/activate
pip install -r /opt/ai_clone/requirements.txt

cd /opt/ai_clone/frontend
npm install
npm run build

sudo systemctl restart ai-clone-backend
sudo nginx -t
sudo systemctl reload nginx
```

## 13. Files That Must Not Be Committed

Never commit:

- `.env`
- API keys or provider secrets
- `data/`
- `uploads/`
- local SQLite databases
- `generated_skills/`
- Nginx password files such as `/etc/nginx/.htpasswd`
- production logs

Keep only templates such as `.env.production.example`, `deploy/nginx.conf.example`, and `deploy/systemd-backend.service.example` in Git.

## 14. Quick Smoke Test

```bash
curl -I https://echo.example.com
curl https://echo.example.com/api/config/status
sudo journalctl -u ai-clone-backend --no-pager -n 50
```

Open the domain in a browser and verify:

- homepage loads from the domain
- `/profiles` loads with React Router
- `/api` calls work through Nginx
- no one needs port `5173`
- API key remains only in `/opt/ai_clone/.env`
