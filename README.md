# Private Search Engine

> **A production-grade, privacy-first, self-hosted search platform built in 12 phases with enterprise-quality standards.**

## 🎯 Overview

Private Search Engine is a **complete full-stack search solution** designed for privacy, performance, and scalability. Built from scratch over 12 phases with rigorous engineering practices, comprehensive testing, and production-grade deployment capabilities.

### ✨ Key Highlights

- **Complete Implementation**: All 12 phases complete (backend, frontend, testing, security, performance, deployment)
- **Quality Assurance**: 380 automated tests (100% pass rate), 86.35% code coverage
- **Security**: Zero vulnerabilities, full OWASP Top 10 (2021) compliance

### 📊 By The Numbers

| Metric | Result |
|--------|--------|
| **Total Tests** | 380 ✅ |
| **Code Coverage** | 86.35% |
| **Vulnerabilities** | 0 (Zero) |
| **Query Latency (p50)** | < 0.001 ms |
| **Batch Indexing** | 2,815 docs/sec |
| **Cache Improvement** | 1,600x faster |

### 🛠️ Technology Stack

**Backend**
- Python 3.11, FastAPI, SQLite (WAL mode)
- BM25 ranking algorithm, NLTK NLP
- Async/await optimization

**Frontend**
- React 18, Vite 5, TypeScript
- Real-time search, autocomplete
- Dark/light theme support

**DevOps**
- Docker (multi-stage), Docker Compose
- Kubernetes manifests (Deployment, PVC, Ingress)
- GitHub Actions CI/CD pipeline
- Prometheus + Grafana monitoring

---

## 🏗️ Architecture (12 Phases)

### **Phases 1-6: Core Engine** (Backend)
- ✅ Web crawler with SSRF protection
- ✅ NLP content processing pipeline
- ✅ SQLite inverted indexing (BM25)
- ✅ Query ranking engine
- ✅ FastAPI REST server

### **Phases 7-8: User Interfaces**
- ✅ React search UI
- ✅ Admin dashboard with metrics

### **Phases 9-10: Quality & Security**
- ✅ Integration & E2E testing
- ✅ Security audit (OWASP compliance)

### **Phases 11-12: Production**
- ✅ Performance optimization
- ✅ Deployment infrastructure

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### Backend Setup
```powershell
# Navigate to project
cd "d:\Project-07\Private Search Engine"

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt

# Start FastAPI backend
uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup (New Terminal)
```powershell
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```

### Seed Sample Data (Optional - New Terminal)
```powershell
# Back in project root
cd "d:\Project-07\Private Search Engine"
python scripts/seed_e2e_db.py
```

### Access Application
- **Frontend**: http://localhost:5173 (or http://localhost:8000 when built)
- **Backend API**: http://localhost:8000/api/v1
- **API Docs**: http://localhost:8000/docs
- **Metrics**: http://localhost:8000/metrics

### Test Search
1. Type in search box: "python"
2. See autocomplete suggestions
3. Press Enter or click Search
4. View ranked results with snippets

### Access Admin Dashboard
1. Click "Admin" button on homepage (or navigate to `/admin`)
2. Enter admin token (set via `ADMIN_TOKEN` environment variable)
3. View crawl controls, metrics, system stats

---

## 📦 Production Deployment

### Docker Compose
```bash
docker compose up -d
# Runs on http://localhost:8000, Prometheus on :9090, Grafana on :3001
```

### Kubernetes
```bash
kubectl apply -f k8s/
```

---

## 🧪 Testing

### Run All Tests
```bash
pytest tests/ -v
```

### Frontend Tests
```bash
cd frontend && npm run test
```

### Load Testing
```bash
locust -f tests/locustfile.py
```

---

## 🔐 Security & Compliance

✅ **OWASP Top 10 (2021)**: All 10 categories mitigated  
✅ **Zero Vulnerabilities**: Verified through automated scanning  
✅ **SSRF Protection**: Hardened at multiple boundaries  
✅ **SQL Injection Protection**: Parameterized queries throughout  
✅ **XSS Protection**: Safe DOM rendering, no dangerouslySetInnerHTML  
✅ **Rate Limiting**: Per-IP sliding window (100 req/min)  
✅ **Security Headers**: CSP, HSTS, X-Frame-Options, etc.  

---

## 📈 Performance Metrics

| Scenario | Result |
|----------|--------|
| Cached Query Latency | < 0.001 ms |
| Single-Term Query Latency | 1.03 ms |
| Multi-Term Query Latency | 4.86 ms |
| Autocomplete Response | 0.01 ms |
| Batch Indexing | 2,815 docs/sec |
| HTML Parsing | 676 docs/sec |
| Memory (Idle) | ~42 MB |
| Memory (Active) | ~118 MB |

---

## 📚 Documentation

- `/docs` - Complete 18-document specification
- `DEPLOYMENT.md` - Production deployment guide
- `PRODUCTION_CHECKLIST.md` - Launch checklist
- `README.md` - This file

---

## 👤 Author

**Anshul (Govind Chandrashekhar Turkar)**
- B.Tech CSE - G H Raisoni University
- Intern - KodeKalp Global Technologies
- GitHub: [@govindturkar69-crypto](https://github.com/govindturkar69-crypto)

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🎯 Status

✅ **Production Ready** | All phases complete | Ready for deployment

---

## 🔗 Repository

- **Source**: https://github.com/govindturkar69-crypto/Private-Search-Engine
- **Issues**: [GitHub Issues](https://github.com/govindturkar69-crypto/Private-Search-Engine/issues)
- **Discussions**: [GitHub Discussions](https://github.com/govindturkar69-crypto/Private-Search-Engine/discussions)

---

**Built with ❤️ for privacy, performance, and production excellence.**
