# Enterprise GraphRAG SaaS Intelligence Engine 🚀

An enterprise-grade, multi-tenant **GraphRAG (Graph-Augmented Retrieval-Augmented Generation) SaaS Platform** powered by **FastAPI**, **LangGraph**, **Qdrant Cloud**, **Neo4j Aura Cloud**, **Upstash Redis**, **Celery**, and **Groq LLM**.

Designed for SaaS platforms and enterprise clients, this engine enables multiple independent organizations (tenants) to upload proprietary PDF documents, securely build isolated Knowledge Graphs and Vector Embeddings, and query them seamlessly through stateful multi-turn conversational agents embedded directly onto their client websites.

---

## 🏛️ Multi-Tenant SaaS System Architecture

```mermaid
flowchart TD
    subgraph Client & Widget Layer
        WebsiteA["Client A Website\n(Embeddable Chat Widget)\nX-API-Key: grag_live_alpha\ntenant_id: tenant_alpha"]
        WebsiteB["Client B Website\n(Embeddable Chat Widget)\nX-API-Key: grag_live_beta\ntenant_id: tenant_beta"]
        AdminDashboard["Tenant & Admin Portal\n- API Key Provisioning\n- PDF Upload & Ingestion"]
    end

    subgraph API Gateway & Security Layer [FastAPI Application]
        CORS["Permissive CORS (*)\nSupports any external client domain"]
        AuthMiddleware["FastAPI API Key Auth Dependency\n- Header: X-API-Key\n- Query: ?api_key=\n- Tenant Isolation Enforcement"]
        AuthRouter["/api/v1/auth\n- POST /api-keys (Generate)\n- GET /verify (Validate)"]
        IngestRouter["/api/v1/ingest\n- POST / (Upload PDF with tenant_id)"]
        ChatRouter["/api/v1/chat\n- POST / (Multi-turn stateful query)"]
        HealthRouter["/api/v1/health & /api/v1/test-data"]
    end

    subgraph Caching & Session Storage [Upstash Redis]
        TenantCache["Tenant-Partitioned Semantic Cache\n`grag:semantic_cache:{tenant_id}`\n(Cosine Similarity > 0.95, <5ms)"]
        RedisCheckpointer["LangGraph Persistent Memory Checkpointer\n`grag:ckpt:data:{tenant_id}:{session_id}`\n(Preserves multi-turn chat history)"]
        APIKeyStore["API Key Repository\n`grag:apikey:{api_key}`"]
        CeleryBroker["Celery Task Queue & Results Broker"]
    end

    subgraph Background Processing Layer [Celery Workers]
        CeleryWorker["Celery Worker (solo pool)"]
        PDFParser["pypdf Text Extraction"]
        Chunker["Sliding Window Chunker (1000 chars, 200 overlap)"]
    end

    subgraph Isolated Storage Layer [Multi-Tenant Partitioned]
        QdrantDB[("Qdrant Vector DB\n- Collection: 'documents'\n- Payload: {tenant_id, text, chunk_id}\n- Strict Filter: tenant_id == $tenant_id")]
        Neo4jDB[("Neo4j Knowledge Graph\n- Chunk nodes: {tenant_id}\n- Entity nodes: {tenant_id}\n- Relationships: {tenant_id}\n- Isolated 2-hop Cypher traversal")]
        PostgresDB[("Neon PostgreSQL\n(AsyncPG Storage)")]
    end

    subgraph LLM & Agentic Intelligence Layer
        EmbeddingModel["HuggingFace Transformer\n(all-MiniLM-L6-v2 - 384d)"]
        GroqLLM["Groq API Engine\n(openai/gpt-oss-120b / llama-3.1-8b)"]
        LangGraphWorkflow["LangGraph Agentic StateGraph\n- Heuristic Router Node\n- Parallel Vector & Graph Retrieval Tools\n- History-Aware Synthesis Generator\n- Self-RAG Evaluator Critic"]
    end

    %% Ingestion Pipeline
    AdminDashboard -->|1. Upload PDF + tenant_id| IngestRouter
    IngestRouter --> AuthMiddleware
    IngestRouter -->|2. Dispatch Ingestion Task| CeleryBroker
    CeleryBroker --> CeleryWorker
    CeleryWorker --> PDFParser --> Chunker
    Chunker -->|3. Generate 384d Vectors| EmbeddingModel
    EmbeddingModel -->|4. Upsert Batched with tenant_id| QdrantDB
    Chunker -->|5. Extract Entities with Groq| GroqLLM
    GroqLLM -->|6. Ingest Scoped Graph| Neo4jDB

    %% Chat & Query Flow
    WebsiteA -->|Query + API Key + session_id| CORS
    WebsiteB -->|Query + API Key + session_id| CORS
    CORS --> AuthMiddleware
    AuthMiddleware --> ChatRouter
    ChatRouter -->|1. Lookup Tenant Cache| TenantCache
    TenantCache -- Cache Hit (<5ms) --> WebsiteA
    TenantCache -- Cache Miss --> LangGraphWorkflow
    LangGraphWorkflow <-->|Load / Save Turn State| RedisCheckpointer
    LangGraphWorkflow -->|Vector Tool (tenant filter)| QdrantDB
    LangGraphWorkflow -->|Graph Tool (tenant traversal)| Neo4jDB
    LangGraphWorkflow -->|Synthesize with History| GroqLLM
    LangGraphWorkflow -->|Self-RAG Validation| GroqLLM
    LangGraphWorkflow -->|Save Valid Response| TenantCache
    LangGraphWorkflow --> WebsiteA
```

---

## ⚡ Core SaaS Features & Architectural Capabilities

### 1. 🛡️ Strict Multi-Tenancy Data Isolation
- **Vector Storage (Qdrant)**: Every point payload contains `tenant_id`. All semantic queries automatically execute with indexed `models.Filter(must=[models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id))])`. Cross-tenant data leakage is mathematically impossible at the database index layer.
- **Knowledge Graph (Neo4j)**: Every `Chunk` node, `Entity` node, and relationship (`HAS_ENTITY`, `MENTIONED_IN`, `RELATES_TO`) is tagged with `tenant_id`. Cypher graph traversals enforce `WHERE e.tenant_id = $tenant_id AND all(rel IN r WHERE rel.tenant_id = $tenant_id)`.
- **Semantic Caching (Redis)**: Cache records are partitioned by tenant namespace (`grag:semantic_cache:{tenant_id}`). Tenant A cannot access or warm Tenant B's cache.
- **Ingestion Pipeline**: The asynchronous Celery pipeline tags all chunks and graph extractions with the target `tenant_id`.

### 2. 🧠 Stateful Memory & Session Management
- **Persistent LangGraph Checkpointer (`RedisSaver`)**: Checkpoint states and conversation history are automatically saved into Redis keyed by `grag:ckpt:data:{tenant_id}:{session_id}` with configurable TTL (default 30 days).
- **Multi-Turn Contextual Awareness**: The chat endpoint accepts a `session_id`. The LangGraph generator node integrates recent multi-turn conversation history into its prompt synthesis, resolving co-references (e.g. "What did they conclude in the study we just discussed?").

### 3. 🔑 Authentication & API Key Management
- **Client API Keys**: Each tenant is issued a secure API key (`grag_live_<random_hex>`).
- **Flexible Widget Auth**: FastAPI middleware validates the key via the standard `X-API-Key` HTTP header or the `?api_key=` URL query parameter.
- **Cross-Tenant Violation Guard**: If a request attempts to query `tenant_beta` using an API key issued to `tenant_alpha`, the request is rejected with `403 Forbidden`.
- **Master Admin Key**: Administrators can provision, list, and revoke tenant keys using the `MASTER_ADMIN_KEY`.

### 4. 🌐 Embeddable Chat Widget Integration
- **Universal CORS Policy**: Pre-configured with permissive CORS headers (`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Headers: *`), allowing client companies to embed the chat widget on any domain (`https://client1.com`, `https://store.io`, etc.) without CORS blocking.
- **Plug-and-Play Script**: Lightweight drop-in HTML/JavaScript widget snippet.

---

## 🛠️ Environment Variables Configuration

Create a `.env` file in the project root with the following parameters:

```env
PROJECT_NAME="Enterprise GraphRAG Intelligence Engine"
ENVIRONMENT="development"

# LLM Configuration
GROQ_API_KEY="gsk_your_groq_api_key"
GROQ_MODEL="openai/gpt-oss-120b"

# SaaS & Security Configuration
MASTER_ADMIN_KEY="grag_master_admin_secret_key_2026"
DEFAULT_DEV_API_KEY="grag_dev_tenant_default_key_2026"
DEFAULT_TENANT_ID="default_tenant"

# Database Connections
POSTGRES_URL="postgresql+asyncpg://user:pass@host/dbname?sslmode=require"
QDRANT_URL="https://your-qdrant-instance.cloud.qdrant.io:6333"
QDRANT_API_KEY="your_qdrant_api_key"
NEO4J_URI="neo4j+s://your-neo4j-instance.databases.neo4j.io"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="your_neo4j_password"
REDIS_URL="rediss://default:your_redis_password@your-redis-instance.upstash.io:6379"
```

---

## 🚀 Quickstart & Setup Guide

### 1. Clone & Activate Environment
```bash
git clone <repository_url>
cd graphrag-enterprise-engine

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start Celery Background Ingestion Worker
```bash
# Windows:
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo

# Linux/macOS:
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

### 3. Start FastAPI Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive Swagger documentation is available at `http://localhost:8000/docs`.

---

## 📡 API Reference & cURL Examples

### 1. Provision a New Tenant API Key (`POST /api/v1/auth/api-keys`)
```bash
curl -X POST "http://localhost:8000/api/v1/auth/api-keys" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: grag_master_admin_secret_key_2026" \
  -d '{
    "tenant_id": "acme_corp",
    "client_name": "Acme Corporation",
    "description": "Production Website Chat Widget"
  }'
```
**Response:**
```json
{
  "api_key": "grag_live_17082d750f7b51bc3665e76c348c9c6adeb712a5",
  "tenant_id": "acme_corp",
  "client_name": "Acme Corporation",
  "description": "Production Website Chat Widget",
  "created_at": "2026-08-22T10:27:47.805818+00:00",
  "is_active": true
}
```

---

### 2. Verify an API Key (`GET /api/v1/auth/verify`)
```bash
curl -X GET "http://localhost:8000/api/v1/auth/verify" \
  -H "X-API-Key: grag_live_17082d750f7b51bc3665e76c348c9c6adeb712a5"
```
Or via query parameter:
```bash
curl -X GET "http://localhost:8000/api/v1/auth/verify?api_key=grag_live_17082d750f7b51bc3665e76c348c9c6adeb712a5"
```
**Response:**
```json
{
  "valid": true,
  "tenant": {
    "tenant_id": "acme_corp",
    "client_name": "Acme Corporation",
    "is_active": true,
    "created_at": "2026-08-22T10:27:47.805818+00:00"
  },
  "message": "API Key is valid and authenticated for tenant 'acme_corp' (Acme Corporation)"
}
```

---

### 3. Ingest a PDF Document for a Tenant (`POST /api/v1/ingest`)
```bash
curl -X POST "http://localhost:8000/api/v1/ingest" \
  -H "X-API-Key: grag_live_17082d750f7b51bc3665e76c348c9c6adeb712a5" \
  -F "file=@sample_contract.pdf" \
  -F "tenant_id=acme_corp"
```
**Response (202 Accepted):**
```json
{
  "task_id": "f66bd600-f4ee-4010-afe0-8229fdac1801",
  "tenant_id": "acme_corp",
  "filename": "sample_contract.pdf",
  "message": "Document 'sample_contract.pdf' accepted for background ingestion for tenant 'acme_corp'",
  "status": "processing"
}
```

---

### 4. Multi-Turn Stateful Chat (`POST /api/v1/chat`)

#### Turn 1: Initial Query
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: grag_live_17082d750f7b51bc3665e76c348c9c6adeb712a5" \
  -d '{
    "question": "What are the SLA terms in our service agreement?",
    "session_id": "user_sess_98765"
  }'
```
**Response:**
```json
{
  "tenant_id": "acme_corp",
  "session_id": "user_sess_98765",
  "question": "What are the SLA terms in our service agreement?",
  "answer": "According to the Service Agreement [Doc: sample_contract.pdf], uptime SLA is guaranteed at 99.95% with 24/7 dedicated support escalation [Graph: Acme Corp -> SLA_99.95].",
  "cache_hit": false,
  "route_decision": "hybrid",
  "sources": {
    "vector_chunks_count": 3,
    "graph_relations_count": 12,
    "vector_sources": ["sample_contract.pdf"],
    "tenant_id": "acme_corp"
  }
}
```

#### Turn 2: Follow-Up Query (Session Memory Preserved)
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: grag_live_17082d750f7b51bc3665e76c348c9c6adeb712a5" \
  -d '{
    "question": "What penalty occurs if that uptime SLA is breached?",
    "session_id": "user_sess_98765"
  }'
```
*(The LangGraph agent uses the checkpointer session memory to know "that uptime SLA" refers to the 99.95% SLA discussed in Turn 1.)*

---

### 5. Multi-Tenant Data Statistics (`GET /api/v1/test-data`)
```bash
# Query stats for a specific tenant
curl -X GET "http://localhost:8000/api/v1/test-data?tenant_id=acme_corp"
```
**Response:**
```json
{
  "tenant_id": "acme_corp",
  "qdrant": {
    "collection": "documents",
    "tenant_filter": "acme_corp",
    "points_count": 42
  },
  "neo4j": {
    "tenant_filter": "acme_corp",
    "nodes_count": 68,
    "relationships_count": 115
  }
}
```

---

## 💻 Embeddable Chat Widget Snippet

Clients can embed the GraphRAG chat assistant into their website by adding the following snippet before the closing `</body>` tag:

```html
<!-- GraphRAG Multi-Tenant Chat Widget Embed -->
<div id="graphrag-chat-widget"></div>
<script>
  (function() {
    const CONFIG = {
      apiUrl: "https://your-graphrag-engine.com/api/v1",
      apiKey: "grag_live_YOUR_TENANT_API_KEY",
      tenantId: "your_tenant_id",
      sessionId: "session_" + Math.random().toString(36).substring(2, 9),
      themeColor: "#3B82F6",
      title: "AI Knowledge Assistant"
    };

    async function sendChatQuery(userQuestion) {
      const response = await fetch(`${CONFIG.apiUrl}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": CONFIG.apiKey
        },
        body: JSON.stringify({
          question: userQuestion,
          tenant_id: CONFIG.tenantId,
          session_id: CONFIG.sessionId
        })
      });
      return await response.json();
    }

    console.log("GraphRAG Widget initialized for tenant:", CONFIG.tenantId);
  })();
</script>
```

---

## 🧪 Automated Testing

Run the full SaaS multi-tenant test suite:
```bash
python eval/test_saas_multi_tenant.py
```

The test suite validates:
1. System Health & Gateway Endpoints
2. Seed Dev Key & Master Admin Authentication
3. Provisioning Tenant API Keys (`tenant_alpha`, `tenant_beta`)
4. Ingesting isolated documents per tenant
5. Stateful multi-turn chat sessions with persistent memory
6. Cross-tenant permission violation rejection (`403 Forbidden`)
7. Permissive CORS preflight headers for external widget embedding

---

## 📄 License
Enterprise Commercial License. All rights reserved.
