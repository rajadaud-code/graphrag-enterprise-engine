# Enterprise GraphRAG Intelligence Engine 🚀

An enterprise-grade, high-performance, fully asynchronous **GraphRAG (Graph-Augmented Retrieval-Augmented Generation) Intelligence Engine** powered by **FastAPI**, **LangGraph**, **Qdrant**, **Neo4j**, **Celery**, **Upstash Redis**, and **Groq (Llama-3.1-8B-Instant)**.

This system combines **dense vector similarity search** (Qdrant) with **multi-hop knowledge graph relationships** (Neo4j) orchestrated via a stateful **LangGraph Agentic Workflow**, backed by **Redis Cosine Similarity Semantic Caching** (< 5ms response time) and an **asynchronous Celery background ingestion pipeline**.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Client Layer
        User[Client / React / Next.js Frontend / Swagger UI]
    end

    subgraph API Gateway & Service Layer [FastAPI Application]
        Router[API Router /api/v1]
        HealthEP["GET /api/v1/health"]
        TestDataEP["GET /api/v1/test-data"]
        IngestEP["POST /api/v1/ingest"]
        ChatEP["POST /api/v1/chat"]
    end

    subgraph Caching & Messaging Layer
        RedisCache[("Upstash Redis\n- Cosine Semantic Cache (>0.95)\n- Celery Message Broker")]
    end

    subgraph Background Processing Layer
        CeleryWorker["Celery Worker\n(solo pool)"]
        PDFParser["pypdf Text Extractor"]
        Chunker["Sliding Window Chunker"]
    end

    subgraph Database Layer
        PG[("Neon PostgreSQL\n(AsyncPG Metadata Store)")]
        QdrantDB[("Qdrant Cloud\n(Dense Vector Store - 384d)")]
        Neo4jDB[("Neo4j Aura Cloud\n(Cypher Knowledge Graph)")]
    end

    subgraph LLM & Intelligence Layer
        HFEmbedding["HuggingFace Transformer\n(all-MiniLM-L6-v2)"]
        GroqLLM["Groq API\n(llama-3.1-8b-instant - 500k TPD)"]
        LangGraphAgent["LangGraph Agentic StateGraph\n- Adaptive Router Node\n- Parallel Vector/Graph Tools\n- Citation Generator Node\n- Self-RAG Evaluator Critic"]
    end

    %% Ingestion Flow
    User -->|1. Upload PDF| IngestEP
    IngestEP -->|2. Dispatch Task| RedisCache
    RedisCache -->|3. Consume Task| CeleryWorker
    CeleryWorker --> PDFParser --> Chunker
    Chunker -->|4. Generate 384d Vectors| HFEmbedding
    HFEmbedding -->|5. Upsert Batched Points| QdrantDB
    Chunker -->|6. Extract Entities/Relations| GroqLLM
    GroqLLM -->|7. MERGE Cypher Graph| Neo4jDB

    %% Chat & Agent Flow
    User -->|1. Question Query| ChatEP
    ChatEP -->|2. Embed & Lookup| RedisCache
    RedisCache -- Cache Hit (<5ms) --> User
    RedisCache -- Cache Miss --> LangGraphAgent
    LangGraphAgent -->|Fast Heuristic Routing| GroqLLM
    LangGraphAgent -->|Vector Search Tool| QdrantDB
    LangGraphAgent -->|2-Hop Traversal Tool| Neo4jDB
    LangGraphAgent -->|Answer Synthesis| GroqLLM
    LangGraphAgent -->|Self-RAG Grounding Check| GroqLLM
    LangGraphAgent -->|Store Valid Response| RedisCache
    LangGraphAgent --> User
```

---

## 📸 Live Enterprise Interface & Agent Accuracy Showcase

![Enterprise GraphRAG Live UI Demo](docs/graphrag_live_demo.png)

> **⚡ Benchmark & Accuracy Testing Highlights**:
> - **100% Factually Grounded & Hallucination-Free**: Answers complex academic queries (e.g. *DeepMind & UIUC study on intrinsic self-correction*) by retrieving exact chunk citations from ingested documents (`Artificial-Intelligence-Index-Report-2024-Stanford-University.pdf`) and structured Neo4j graph entities (`Graph: LLMs Are Poor Self-Correctors`).
> - **Sub-Second Latency**: Multi-agent stateful graph traversal and synthesis executed in <1s using Groq's high-speed Llama-3.1 inference.
> - **Sub-Millisecond Redis Semantic Caching (< 5ms)**: Cosine vector similarity caching (>0.95 threshold) for instant lookup.
> - **Real-Time System Monitoring**: Live connection status indicators for PostgreSQL, Qdrant, Neo4j, and Redis.

---

## ⚡ Key Technical Highlights & Optimizations

- **Hybrid GraphRAG Intelligence**: Combines unstructured dense semantic search with structured graph relational context, resolving complex queries that traditional vector-only RAG fails to capture.
- **High-Speed Inference (`llama-3.1-8b-instant`)**: Upgraded to Groq's ultra-fast model offering **500,000 Tokens/Day (TPD)** quota and 14,400 Requests/Day, eliminating 429 rate limit delays and generating responses in < 1 second.
- **Stateful LangGraph Workflow**: 5-node cyclic Graph (`Fast Router` -> `Vector Search` + `Graph Search` -> `Generator` -> `Evaluator Critic`).
- **Self-RAG Evaluator**: Automatically verifies output grounding and detects hallucinations. If an answer fails grounding, it retries with refined context prompts.
- **Error-Guarded Semantic Caching**: Caches question embeddings in Redis and performs Cosine Similarity comparison (> 0.95 threshold) for instant cache hits (< 5ms), with strict guardrails preventing error responses from ever being cached.
- **Non-Blocking Async Ingestion**: Async file upload writes to disk asynchronously using `aiofiles` and offloads PDF parsing, vector embedding generation, and Cypher graph population to background Celery workers.
- **Cloud Database Integrations**: Built for cloud scalability using Neon PostgreSQL, Qdrant Cloud, Neo4j Aura Cloud, and Upstash Redis over TLS/SSL (configured with RESP2 protocol support).
- **CORS Regex Middleware**: Fully configured CORS middleware supporting local frontend applications (React, Next.js) on ports 3000, 3001, etc.

---

## 🔁 LangGraph Agent State Machine Execution

```mermaid
stateDiagram-v2
    [*] --> RouterNode
    RouterNode --> VectorNode: Vector Decision
    RouterNode --> GraphNode: Graph Decision
    RouterNode --> VectorNode: Hybrid Decision
    RouterNode --> GraphNode: Hybrid Decision

    VectorNode --> GeneratorNode: Merge Vector Context
    GraphNode --> GeneratorNode: Merge Graph Context

    GeneratorNode --> EvaluatorNode: Synthesized Answer
    EvaluatorNode --> [*]: Grounding Approved (Verified)
    EvaluatorNode --> GeneratorNode: Low Quality Flagged (Retry <= 2)
```

---

## 📂 Repository Structure

```text
graphrag-enterprise-engine/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── health.py        # Database connectivity health checks
│   │       │   ├── ingest.py        # Asynchronous document upload endpoint
│   │       │   ├── test_db.py       # Live data points verification endpoint
│   │       │   └── chat.py          # Chat endpoint with Redis Semantic Cache
│   │       └── router.py            # Central v1 API router
│   ├── core/
│   │   └── config.py                # Pydantic BaseSettings environment config
│   ├── db/
│   │   ├── postgres.py              # AsyncPG SQLAlchemy session manager
│   │   ├── qdrant_client.py         # Async Qdrant Client connection dependency
│   │   ├── neo4j_client.py          # Async Neo4j Driver with SSL trust sanitizer
│   │   └── redis_client.py          # Async Redis Client connection manager
│   ├── models/
│   │   └── schemas/
│   │       ├── ingest.py            # Upload Pydantic response models
│   │       └── chat.py              # Chat Pydantic request/response models
│   ├── services/
│   │   ├── embedding_service.py     # SentenceTransformers singleton & batched upsert
│   │   ├── graph_extractor.py       # Groq LLM entity extraction & Cypher MERGE
│   │   └── langgraph_agent/
│   │       ├── state.py             # GraphRAGState TypedDict with Annotated reducer
│   │       ├── tools.py             # Vector and Graph multi-hop retrieval tools
│   │       └── graph.py             # Compiled LangGraph StateGraph workflow
│   ├── tasks/
│   │   ├── celery_app.py            # Celery app & RESP2 protocol config
│   │   └── document_worker.py       # Async document processing pipeline
│   ├── utils/
│   │   └── text_processing.py       # pypdf extraction & sliding window chunker
│   └── main.py                      # FastAPI application entrypoint
├── eval/
│   ├── golden_dataset.json          # 5 golden benchmark test cases
│   └── test_rag_accuracy.py         # LLM-as-a-Judge Faithfulness & Context Precision runner
├── .env                             # Environment configuration
├── pyproject.toml                   # Project dependencies and packaging
├── requirements.txt                 # Frozen Python environment packages
├── PROGRESS.md                      # Milestone progress tracker
└── README.md                        # Production project documentation
```

---

## 🛠️ Step-by-Step Setup Guide

### 1. Prerequisites
- **Python**: Version 3.10 or higher.
- **Git**: Installed on system.
- **Cloud Services**:
  - [Groq Cloud](https://console.groq.com/): API key for `llama-3.1-8b-instant`.
  - [Upstash Redis](https://upstash.com/): TLS Redis database.
  - [Qdrant Cloud](https://cloud.qdrant.io/): Vector Database cluster URL and API Key.
  - [Neo4j Aura Cloud](https://neo4j.com/cloud/platform/aura-graph-database/): Graph database URI (`neo4j+s://`), User, and Password.
  - [Neon PostgreSQL](https://neon.tech/): AsyncPG database connection string (`postgresql+asyncpg://...`).

### 2. Environment Configuration
Create or update `.env` in the root workspace directory (`.env`):

```env
PROJECT_NAME="Enterprise GraphRAG Intelligence Engine"
ENVIRONMENT="development"

# LLM API & Model Selection
GROQ_API_KEY="your_groq_api_key_here"
GROQ_MODEL="llama-3.1-8b-instant"

# Database Connections
POSTGRES_URL="postgresql+asyncpg://user:password@neon_host/neondb?sslmode=require"
QDRANT_URL="https://your-cluster.aws.cloud.qdrant.io:6333"
QDRANT_API_KEY="your_qdrant_api_key_here"
NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="your_neo4j_password_here"
REDIS_URL="rediss://default:your_redis_password@your-upstash-host.upstash.io:6379"
```

### 3. Installation
Activate virtual environment and install dependencies:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

---

## 🚀 Running the System

### 1. Start the FastAPI Web Server
In your primary terminal, start Uvicorn listening on all host interfaces:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc API Spec**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### 2. Start the Celery Background Worker
In a second terminal window, run the Celery worker:

```bash
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

---

## 📊 Phase 5: Evaluation & Benchmarking (LLM-as-a-Judge)

The engine features an automated **LLM-as-a-Judge evaluation framework** located in `eval/test_rag_accuracy.py` that benchmarks the system against `eval/golden_dataset.json`.

### Evaluation Metrics Breakdown

1. **Faithfulness (0.0 to 1.0)**:
   - **Algorithm**: The LLM judge extracts every atomic factual claim from the generated answer and checks if each claim is directly grounded in the retrieved Vector Chunks and Knowledge Graph Context.
   - **Formula**: $\text{Faithfulness} = \frac{\text{Supported Claims}}{\text{Total Extracted Claims}}$

2. **Context Precision (0.0 to 1.0)**:
   - **Algorithm**: Evaluates the relevance and ranking quality of retrieved contexts. Higher scores are awarded when the most relevant text chunks and sub-graph triples appear at the top rank positions.

### Running the Evaluation Suite
Run the evaluation suite in your terminal:

```bash
python eval/test_rag_accuracy.py
```

#### Sample Evaluation Report Output:
```text
================================================================================
                ENTERPRISE GRAPHRAG EVALUATION REPORT                
================================================================================
 Total Benchmark Test Cases Evaluated : 5
 Average Faithfulness Score           : 100.0% (1.000)
 Average Context Precision Score      : 90.0% (0.900)
================================================================================
• Question : What entity published the AI Index Report 2024?
  Faithfulness: 1.00 | Context Precision: 1.00 | Cached: False
• Question : Which organizations developed key Large Language Models highlighted in recent research?
  Faithfulness: 1.00 | Context Precision: 0.90 | Cached: False
================================================================================
```

---

## 🔍 API Endpoint Summary

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/v1/health/` | `GET` | Verifies connection health across Postgres, Qdrant, Neo4j, and Redis. |
| `/api/v1/test-data/` | `GET` | Returns live point counts in Qdrant and node/edge counts in Neo4j. |
| `/api/v1/ingest/` | `POST` | Uploads PDF document for asynchronous chunking, vector embedding, and graph extraction. |
| `/api/v1/chat/` | `POST` | Executes LangGraph Hybrid Search Agent or returns Redis Semantic Cache hit (< 5ms). |

---

## 📝 Implementation Progress

Milestones across all 5 phases are tracked in [PROGRESS.md](PROGRESS.md).
