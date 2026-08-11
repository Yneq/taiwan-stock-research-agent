# AWS Lightsail deployment

This deployment runs FinScope TW on one always-on Lightsail instance:

```text
Internet
   |
   v
Caddy :80/:443  ->  FastAPI agent :8000  ->  Spring Boot StockTracker :8080
                                                |
                                                v
                                         Neon PostgreSQL
```

Only Caddy publishes host ports. StockTracker has no published host port and is
reachable by the agent through the Docker `backend` network, while still being
able to call TWSE, FinMind, and Neon. Caddy obtains and renews the public TLS
certificate automatically.

## Recommended instance

- Region: Singapore, or the closest available region to Taiwan and the Neon DB
- OS: Ubuntu 24.04 LTS
- Minimum: 2 GB RAM while building both images on the instance
- Static IP attached before configuring DNS
- IPv4 firewall: TCP 22, 80, 443; UDP 443 is optional for HTTP/3

Do not open ports 8000 or 8080 publicly.

## Expected directory layout

```text
/opt/finscope/
├── StockTracker/
└── taiwan-stock-research-agent/
```

Clone both repositories:

```bash
sudo mkdir -p /opt/finscope
sudo chown "$USER":"$USER" /opt/finscope
cd /opt/finscope
git clone https://github.com/Yneq/StockTracker.git
git clone https://github.com/Yneq/taiwan-stock-research-agent.git
```

Install Docker:

```bash
cd /opt/finscope/taiwan-stock-research-agent
chmod +x deploy/aws/bootstrap-ubuntu.sh deploy/aws/deploy.sh
./deploy/aws/bootstrap-ubuntu.sh
```

Reconnect to SSH once after the bootstrap script completes.

## Secrets

Create the ignored deployment environment file on the instance:

```bash
cd /opt/finscope/taiwan-stock-research-agent/deploy/aws
cp .env.aws.example .env.aws
nano .env.aws
chmod 600 .env.aws
```

Important invariants:

- `AGENT_API_KEY` is injected as Java `AGENT_API_KEY` and Python
  `STOCKTRACKER_API_KEY` by Compose.
- `JWT_SECRET` is the same value in Java and Python.
- `DB_URL` is the JDBC URL and starts with `jdbc:postgresql://`.
- Secrets remain only in `.env.aws`; never commit that file.

## DNS

After attaching a Lightsail Static IP, create these Porkbun records:

| Type | Host | Answer |
|---|---|---|
| A | blank / root | Lightsail Static IPv4 |
| CNAME | www | vanceai.space |

Remove conflicting root A/AAAA records before waiting for certificate issuance.

## Deploy

```bash
cd /opt/finscope/taiwan-stock-research-agent
./deploy/aws/deploy.sh
```

Inspect health and logs:

```bash
curl -fsS https://vanceai.space/health
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/compose.yaml ps
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/compose.yaml logs --tail=100 agent stocktracker caddy
```

## Rollback

Checkout the last known-good Git commit in each repository and run
`./deploy/aws/deploy.sh` again. Caddy certificate data survives container
replacement in named Docker volumes.
