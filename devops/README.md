# Ubuntu server deployment

This guide deploys the Streamlit app on an Ubuntu server using `systemd`. It
assumes you have a sudo-enabled Linux account and deploy the main app,
`main.py`.

## Class-wise DevOps learning path

These project-based classes follow the requested numbering:

1. [Class 1: Linux, Git, and GitHub](classes/class-1-linux-git-github.md)
2. [Class 2: Bash scripting](classes/class-2-bash-scripting.md)
3. [Class 3: GitHub Actions](classes/class-3-github-actions.md)
4. [Class 5: Docker](classes/class-5-docker.md)
5. [Class 6: Jenkins](classes/class-6-jenkins.md)

The class numbers are kept as provided; Class 4 was not included in the
requested topics.

## Ubuntu server deployment

## 1. Install the project

Clone the repository and run the setup script from the project directory:

```bash
git clone https://github.com/shahil04/Text-to-SQL-Chatbot.git
cd Text-to-SQL-Chatbot
bash setup_ubuntu.sh
```

Run setup and the service as the same Linux user. The setup script installs
Python 3.12 and creates `.venv` in the project directory.

## 2. Configure credentials

Create `.env` in the project root and add the API key for the provider you
intend to use. For example:

```env
OPENAI_API_KEY=your-openai-api-key
```

Use `GEMINI_API_KEY` or `GROQ_API_KEY` for those providers instead. Add the
`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` values only if
you use Real Database mode. MySQL is not required for the bundled SQLite Demo.

Protect the credentials file:

```bash
chmod 600 .env
```

Never commit `.env` or put API keys in the service file. Use a least-privilege
MySQL account if connecting to a real database.

## 3. Test locally on the server

From the project directory, start the app bound to the local machine:

```bash
source .venv/bin/activate
streamlit run main.py --server.address 127.0.0.1 --server.port 8501
```

Stop it with `Ctrl+C` after confirming it starts.

## 4. Run it with systemd

Create `/etc/systemd/system/text-to-sql.service` and replace
`DEPLOY_USER` and `/PATH/TO/Text-to-SQL-Chatbot` with the Linux username and
absolute project path used above:

```ini
[Unit]
Description=Text-to-SQL Streamlit app
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=DEPLOY_USER
WorkingDirectory=/PATH/TO/Text-to-SQL-Chatbot
ExecStart=/PATH/TO/Text-to-SQL-Chatbot/.venv/bin/python -m streamlit run /PATH/TO/Text-to-SQL-Chatbot/main.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable the service and check its status:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now text-to-sql
sudo systemctl status text-to-sql
```

View application logs with:

```bash
sudo journalctl -u text-to-sql -f
```

## 5. Expose it safely

The app does not provide user authentication. Keep Streamlit bound to
`127.0.0.1`; do not expose port `8501` directly to the internet. To make it
available remotely, configure a reverse proxy such as Nginx with HTTPS,
WebSocket forwarding, and an authentication layer. Only then allow external
traffic to the proxy's HTTPS port.

## Updating the deployment

Pull the desired code changes as the deployment user, rerun setup to sync the
locked dependencies, then restart the service:

```bash
git pull
bash setup_ubuntu.sh
sudo systemctl restart text-to-sql
```

## GitHub Actions Docker deployment

The [Docker deployment workflow](../.github/workflows/docker-deploy.yml)
builds the SQLite demo image and pushes it to Docker Hub for pushes to `master`.
It deploys the image to EC2 after that push. A manual run from `master` also
publishes and deploys. Pull requests to `master` run the syntax, database, and
Docker build checks without publishing or deploying.

Add these repository secrets in **Settings → Secrets and variables → Actions**:

- `DOCKER_USERNAME` and `DOCKER_PASSWORD` — Docker Hub credentials.
- `EC2_HOST`, `EC2_USER`, and `EC2_KEY` — the EC2 host, SSH username, and
  private key. The matching public key must be authorized on the instance.

The workflow publishes `shahil004/text-to-sql-chatbot:latest`; change
`IMAGE_NAME` in the workflow if your Docker Hub namespace or repository name
differs. The Docker Hub image must be public, or the EC2 instance must already
be authenticated to Docker Hub to pull it. The container port is published on
EC2's localhost (`127.0.0.1:8501`) so it is not directly exposed to the
internet. Configure an authenticated HTTPS reverse proxy on the instance to
provide remote access, as described above.
