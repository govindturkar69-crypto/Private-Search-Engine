# Private Search Engine — Production Deployment & Operations Guide

## 1. Architectural Model & Sizing

The Private Search Engine is architected as an optimized, single-replica service utilizing an embedded SQLite database engine with Write-Ahead Logging (WAL), in-memory process-local LRU caching, in-memory token bucket rate limiting, and an asynchronous crawler manager.

> [!IMPORTANT]
> **Single-Replica Deployment Requirement (ADR D039)**
> Because the authoritative inverted index is stored in SQLite on a single `ReadWriteOnce` (RWO) volume, and because query caches, rate limiters, and crawl worker state are process-local, the application **must be deployed with `replicas: 1`** and `strategy: Recreate`.
> Do not configure Horizontal Pod Autoscaling (HPA) or Pod Disruption Budgets (PDB) expecting multi-replica active-active clustering. Horizontal scaling requires transitioning SQLite to a client-server distributed database (e.g., PostgreSQL/Distributed Vector/Search Store) and distributed cache/rate-limiter (e.g., Redis).

### Sizing Guidelines
- **CPU:** 0.5 cores allocated (burst up to 1.0 core for crawl tokenization or heavy query ranking).
- **RAM:** 512Mi request, 1Gi limit.
- **Storage:** 10Gi to 50Gi PersistentVolume (SSD recommended for SQLite random I/O performance).

---

## 2. Environment Configuration

All production configurations are passed through environment variables or Kubernetes ConfigMaps and Secrets.

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | **Yes** | `production` | Set to `production` to enforce strict security gates. |
| `PORT` | No | `8000` | Port for the Uvicorn HTTP server. |
| `ADMIN_TOKEN` | **Yes** | *None* | Cryptographic secret for crawl/admin API. Minimum 16 characters. |
| `DATABASE_PATH` | No | `/app/data/index.db` | Absolute path to SQLite index file. |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `RATE_LIMIT_PER_MINUTE` | No | `100` | Token bucket limit per client IP. |
| `CORS_ORIGINS` | No | `[]` | JSON array of permitted origins (e.g., `["https://search.example.com"]`). |
| `TRUSTED_PROXIES` | No | `[]` | JSON array of trusted proxy CIDRs/IPs for `X-Forwarded-For`. |
| `ENABLE_HSTS` | No | `true` | Enables `Strict-Transport-Security` header. |
| `MAX_OFFSET` | No | `1000` | Maximum pagination offset. |
| `CRAWL_DELAY` | No | `1.0` | Politeness delay between crawler page fetches. |

### Generating a Secure Admin Token
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 3. Containerized Deployment (Docker Compose)

The repository provides a complete single-host production stack containing:
1. `api`: Multi-stage Python 3.11 / Vite SPA runtime container.
2. `prometheus`: Prometheus v2.51.0 metrics aggregator.
3. `grafana`: Grafana v10.4.0 pre-provisioned dashboards.

### Quick Start
```bash
# 1. Prepare environment file
cp .env.production.example .env.production
# Edit .env.production to set your generated ADMIN_TOKEN and settings

# 2. Build and launch services
docker compose up -d --build

# 3. Verify services are running and healthy
docker compose ps
docker compose logs -f api
```

### Accessing Endpoints
- **Search SPA & API:** `http://localhost:8000/`
- **Liveness Health Check:** `http://localhost:8000/health`
- **Component Readiness:** `http://localhost:8000/api/v1/health`
- **Prometheus Metrics:** `http://localhost:8000/metrics`
- **Prometheus UI:** `http://localhost:9090`
- **Grafana UI:** `http://localhost:3001` (Credentials: `admin` / `admin`)

---

## 4. Kubernetes Deployment

Production Kubernetes manifests reside in `k8s/`.

### 4.1 Deployment Steps
```bash
# 1. Create dedicated namespace
kubectl create namespace search-engine

# 2. Create production secrets
kubectl -n search-engine create secret generic search-engine-secret \
  --from-literal=ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --from-literal=CORS_ORIGINS='["https://search.example.com"]' \
  --from-literal=TRUSTED_PROXIES='["10.0.0.0/8"]'

# 3. Apply persistent storage and configurations
kubectl -n search-engine apply -f k8s/pvc.yaml
kubectl -n search-engine apply -f k8s/configmap.yaml
kubectl -n search-engine apply -f k8s/service.yaml
kubectl -n search-engine apply -f k8s/networkpolicy.yaml

# 4. Deploy application pod
kubectl -n search-engine apply -f k8s/deployment.yaml

# 5. Await rollout completion
kubectl -n search-engine rollout status deployment/search-engine-deployment --timeout=180s

# 6. Apply Ingress routing (omitting /metrics from public exposition)
kubectl -n search-engine apply -f k8s/ingress.yaml
```

---

## 5. Automated Database Backup & Disaster Recovery

SQLite databases running in Write-Ahead Logging (WAL) mode cannot be backed up reliably using naive filesystem copies (`cp`), which can capture torn pages. The search engine provides an automated, transactionally consistent backup utility (`scripts/backup_database.py` and `scripts/backup-database.sh`).

### 5.1 Taking a Live Backup
```bash
# Create live snapshot with integrity verification and automatic retention purge:
./scripts/backup-database.sh --db-path data/index.db --backup-dir data/backups --verify-restore --retention-days 30
```

### 5.2 Backup Subsystem Features
- **Online Backup API:** Calls Python `sqlite3.connect().backup()`, locking pages cleanly without interrupting active concurrent read/write transactions.
- **Cryptographic Digest:** Computes SHA-256 hash stored alongside backup in `index_backup_<timestamp>.db.sha256`.
- **Logical Validation:** Executes `PRAGMA integrity_check` on backup snapshot before marking success.
- **Non-Destructive Restore Verification:** When `--verify-restore` is passed, restores database to an isolated temporary sandbox, initializes `SQLiteIndexer`, and runs smoke queries.
- **Safe Retention:** Automatically purges backups older than `--retention-days`, matching only `index_backup_*.db`.

### 5.3 Scheduled Cron Job
Add the following entry to crontab (`crontab -e`) to execute automated daily backups at 02:00 UTC:
```cron
0 2 * * * /app/scripts/backup-database.sh --db-path /app/data/index.db --backup-dir /app/data/backups --verify-restore --retention-days 30 >> /app/data/backups/backup.log 2>&1
```

### 5.4 Disaster Recovery Restoration Runbook
In the event of volume loss or catastrophic database corruption:
```bash
# 1. Stop running application container or deployment
kubectl -n search-engine scale deployment search-engine-deployment --replicas=0

# 2. Identify latest verified backup and checksum
cd /app/data/backups
LATEST_BACKUP=$(ls -t index_backup_*.db | head -n 1)
LATEST_SHA="${LATEST_BACKUP}.sha256"

# 3. Verify checksum integrity
sha256sum -c "$LATEST_SHA"

# 4. Restore verified backup to primary index path
cp "$LATEST_BACKUP" /app/data/index.db
# Remove stale WAL/SHM locks
rm -f /app/data/index.db-wal /app/data/index.db-shm

# 5. Verify database integrity
python -c "import sqlite3; conn = sqlite3.connect('/app/data/index.db'); print(conn.execute('PRAGMA integrity_check;').fetchone()); conn.close()"

# 6. Restart application
kubectl -n search-engine scale deployment search-engine-deployment --replicas=1
```

---

## 6. Post-Deployment Verification & Smoke Tests

After deploying or updating an instance, execute the non-destructive production smoke test:
```bash
# Linux/macOS
./scripts/production-test.sh --base-url "https://search.example.com"

# Windows PowerShell
.\scripts\production-test.ps1 -base-url "http://localhost:8000"
```

The smoke test validates:
1. `GET /health` (Liveness)
2. `GET /api/v1/health` (Readiness & Indexer status)
3. `POST /api/v1/search` (Read-only query execution)
4. `GET /metrics` (Prometheus exposition format)

---

## 7. Rollback Procedures

If a newly deployed image fails startup probes or post-deployment smoke tests:

### Kubernetes Rollback
```bash
# View rollout history
kubectl -n search-engine rollout history deployment/search-engine-deployment

# Instantly rollback to previous known-healthy revision
kubectl -n search-engine rollout undo deployment/search-engine-deployment

# Confirm rollout status
kubectl -n search-engine rollout status deployment/search-engine-deployment
```

### Docker Compose Rollback
```bash
# Revert image tag or git checkout to previous release tag
git checkout v1.0.0
docker compose up -d --build
```

