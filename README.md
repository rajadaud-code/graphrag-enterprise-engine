# Enterprise GraphRAG Intelligence Engine

A high-performance, low-latency, zero-cost Retrieval-Augmented Generation (GraphRAG) API built with Python, FastAPI, Celery, Redis, Qdrant, Neo4j, and LangGraph.

---

## 🏛️ Architecture Overview

The **Enterprise GraphRAG Intelligence Engine** combines vector retrieval with graph database structures into a stateful reasoning pipeline:

- **FastAPI**: Non-blocking asynchronous REST API framework.
- **Qdrant**: High-performance vector database for semantic chunk retrieval.
- **Neo4j**: Relational Knowledge Graph database for multi-hop graph queries.
- **PostgreSQL**: Relational storage for users, sessions, and task logs via SQLAlchemy 2.0 Async.
- **Redis**: Asynchronous task broker, result backend, and semantic query cache.
- **Celery**: Background async document parsing, embedding, and graph extraction worker pool.
- **LangGraph**: Stateful agentic search & synthesis pipeline.

---

## 🛠️ Project Structure

```text
graphrag-enterprise-engine/
│
├── gemini.md                           # AI Agent Context & Instruction Manual
├── README.md                           # Overall Project Setup & User Manual
├── PROGRESS.md                         # Current Implementation Progress Tracker
├── .gitignore                          # Git Ignore Rules
├── docker-compose.yml                  # Local Infrastructure Setup
├── requirements.txt                    # Dependencies
│
└── app/
    ├── main.py                         # FastAPI Entrypoint
    ├── api/
    │   └── v1/
    │       ├── router.py               # Central Router
    │       └── endpoints/
    │           └── health.py           # Health Checks Endpoint
    ├── core/
    │   └── config.py                   # Pydantic Settings Configuration
    └── db/
        ├── postgres.py                 # Async PostgreSQL Session
        ├── qdrant_client.py            # Async Qdrant Connection
        ├── neo4j_client.py             # Async Neo4j Driver Connection
        └── redis_client.py             # Async Redis Client
```

---

## 🚀 Quick Start

### 1. Environment Configuration

Create a `.env` file in the root directory (or copy `.env.example`):

```env
PROJECT_NAME="Enterprise GraphRAG Intelligence Engine"
ENVIRONMENT="development"

# LLM API
GROQ_API_KEY="your-groq-api-key"

# Database Connections
POSTGRES_URL="postgresql+asyncpg://user:password@localhost:5432/dbname"
QDRANT_URL="http://localhost:6333"
QDRANT_API_KEY=""
NEO4J_URI="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="password"
REDIS_URL="redis://localhost:6379/0"
```

### 2. Setup & Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run Application

```bash
# Run FastAPI development server with Uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔍 API Endpoints

Once the application is running, visit:
- **Interactive OpenAPI Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Health Check Endpoint
```http
GET /api/v1/health
```
Performs non-blocking async status checks across PostgreSQL, Qdrant, Neo4j, and Redis.

**Sample Response (200 OK):**
```json
{
  "status": "all systems operational",
  "details": {
    "postgres": "healthy",
    "qdrant": "healthy",
    "neo4j": "healthy",
    "redis": "healthy"
  }
}
```

---

## 📝 Progress & Status

Track implementation milestones across all phases in [PROGRESS.md](PROGRESS.md).
