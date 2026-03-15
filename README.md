# Huangting-Flux Hub

> **The central API hub for the Huangting-Flux Agent Network.**
> Private backend service powering [huangting.ai](https://huangting.ai).

[![Protocol](https://img.shields.io/badge/Protocol-Huangting%20v7.8-gold)](https://github.com/XianDAO-Labs/huangting-protocol)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)

---

## Architecture

```
XianDAO-Labs/
├── huangting-protocol     (Public)  ← Protocol + SDK + Standards
├── huangting-flux-web     (Public)  ← Next.js Frontend
└── huangting-flux-hub     (Private) ← This repo: FastAPI Backend
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/register` | Register an Agent to the network |
| `POST` | `/api/v1/broadcast` | Broadcast an energy state signal |
| `GET`  | `/api/v1/subscribe?task_type=...` | Get optimization strategies |
| `GET`  | `/api/v1/network/stats` | Real-time network statistics |
| `GET`  | `/api/v1/signals/recent` | Recent network signals |
| `WS`   | `/api/v1/ws/live` | WebSocket live signal stream |
| `GET`  | `/docs` | Interactive API documentation (Swagger UI) |

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 7+

### Development Setup

```bash
# 1. Clone and install dependencies
git clone https://github.com/XianDAO-Labs/huangting-flux-hub.git
cd huangting-flux-hub
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 3. Start dependencies
docker-compose up db redis -d

# 4. Run the API server
uvicorn app.main:app --reload --port 8000
```

### Docker Deployment

```bash
# Start all services (db + redis + hub)
docker-compose up -d

# View logs
docker-compose logs -f hub
```

The API will be available at `http://localhost:8000`.
Interactive docs at `http://localhost:8000/docs`.

## SDK Integration

The [huangting-soul](https://pypi.org/project/huangting-soul/) SDK connects to this hub:

```python
from huangting_soul.flux import HuangtingFlux

# Connect to production hub
flux = HuangtingFlux(
    agent_id="my-agent",
    hub_url="https://api.huangting.ai"  # or your self-hosted URL
)
flux.register(capabilities=["research"])
```

## Author

**Meng Yuanjing (Mark Meng)** — [XianDAO Labs](https://github.com/XianDAO-Labs)

## License

Apache 2.0 — See [LICENSE](LICENSE)
