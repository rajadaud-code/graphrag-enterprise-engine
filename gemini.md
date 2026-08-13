# GEMINI.md: Enterprise GraphRAG Intelligence Engine Context & Instructions

## 1. Executive Summary & Core Objectives
You are operating as an Expert Principal AI & Backend Engineer working on the **Enterprise GraphRAG Intelligence Engine**.

This project is a high-performance, low-latency, zero-cost (open-source) Retrieval-Augmented Generation API. Its primary goal is to solve enterprise data accuracy challenges by combining **Semantic Vector Search (Qdrant)** with **Relational Knowledge Graphs (Neo4j)** into a stateful **LangGraph** retrieval and reasoning agent.

### Key Performance & Quality Targets
* **Zero Hallucination:** Answers must be strictly grounded in vector chunks and verified graph relations.
* **Non-Blocking Architecture:** All PDF/document ingestion, parsing, embedding, and LLM-driven graph extraction must be offloaded to **Celery** background tasks backed by **Redis**.
* **Ultra-Low Latency:** Implement **Redis Semantic Caching** to intercept duplicate or semantically similar queries before hitting the LLM.
* **Cost Efficiency:** Use local Hugging Face embedding models (`all-MiniLM-L6-v2`) and free-tier Groq API (`Llama-3.3-70B-versatile` / `Llama-3.1-70B`) for high-speed inference without API costs.

---

## 2. Technical Stack Specifications

* **Backend Framework:** FastAPI (Python 3.11+), Pydantic v2, Uvicorn
* **Task Queue & Caching:** Celery, Redis (Broker, Result Store, & Semantic Cache)
* **Vector Database:** Qdrant (Local Docker instance, Cosine Distance)
* **Graph Database:** Neo4j Community Edition (Local Docker instance, Cypher Query Language)
* **Relational Database:** PostgreSQL (Local Docker instance, SQLAlchemy 2.0 Async)
* **Agent Framework:** LangGraph (Stateful Agent Graph Workflows)
* **Embeddings Model:** `sentence-transformers/all-MiniLM-L6-v2` (Local Hugging Face execution)
* **LLM Engine:** Groq API (`llama-3.3-70b-versatile` or `llama-3.1-70b-versatile`)

---

## 3. Strict Coding & Operational Rules for AI Agents

When generating, modifying, or refactoring code in this repository, you **MUST** follow these rules without exception:

1. **Strict Modular Architecture:** Never write monolithic files. Keep API endpoints, DB configurations, schemas, Celery tasks, and LangGraph nodes cleanly separated.
2. **Dependency Injection:** Never instantiate global clients or connections at the module root. Always use FastAPI dependency injection (`Depends()`) or factory contexts.
3. **Non-Blocking Async Code:** Use `async def` and asynchronous drivers (`asyncpg`, `AsyncQdrantClient`, `httpx`) for all network operations.
4. **Structured JSON Validation:** Enforce strict Pydantic models for all incoming API requests, outgoing responses, and LLM structured outputs (e.g., Graph entity extractions).
5. **Resilience & Retries:** Wrap external LLM calls in `tenacity` retry decorators using exponential backoff to handle rate limits (`429` status codes).
6. **No Debug Prints:** Use Python’s built-in `logging` module configured with structured JSON formatters instead of `print()` statements.

---

## 4. End-to-End Directory Blueprint

```text
graphrag-enterprise-engine/
│
├── gemini.md                           # AI Agent Context & Instruction Manual
├── README.md                           # Overall Project Setup & User Manual
├── PROGRESS.md                         # Current Implementation Progress Tracker
├── .gitignore                          # Git Ignore Rules
├── docker-compose.yml                  # Local Infrastructure (Qdrant, Neo4j, Redis, Postgres)
├── Dockerfile                          # FastAPI & Celery Container Definition
├── requirements.txt                    # Python Dependencies
├── .env.example                        # Environment Variables Template
│
├── app/
│   ├── main.py                         # FastAPI App Setup, CORS, & Exception Handlers
│   ├── api/
│   │   └── v1/
│   │       ├── router.py               # Central Router
│   │       └── endpoints/
│   │           ├── ingest.py           # Document Upload Endpoint (Async Celery trigger)
│   │           ├── chat.py             # Agentic Retrieval & Chat Endpoint
│   │           └── health.py           # Database & Service Health Check Endpoint
│   │
│   ├── core/
│   │   ├── config.py                   # Environment Configurations (BaseSettings)
│   │   ├── security.py                 # Security & Auth Utilities
│   │   └── exceptions.py               # Custom Exception Definitions
│   │
│   ├── db/
│   │   ├── postgres.py                 # Async SQLAlchemy Session & Base Model
│   │   ├── qdrant_client.py            # Async Qdrant Connection Manager
│   │   └── neo4j_client.py             # Neo4j Cypher Execution Driver
│   │
│   ├── models/
│   │   ├── domain/                     # DB Tables (User, ChatSession, TaskStatus)
│   │   └── schemas/                    # Pydantic Schemas (API Contracts & LLM Schemas)
│   │
│   ├── services/
│   │   ├── embedding_service.py        # Local Hugging Face Embedding Generator
│   │   ├── graph_extractor.py          # LLM JSON Schema Node/Edge Extractor
│   │   └── langgraph_agent/
│   │       ├── graph.py                # StateGraph Definition & Compilation
│   │       ├── state.py                # GraphRAGState TypedDict Memory
│   │       ├── tools.py                # Qdrant Vector & Neo4j Cypher Search Tools
│   │       └── prompts.py              # Router, Cypher, and Generation Prompts
│   │
│   ├── tasks/
│   │   ├── celery_app.py               # Celery Setup with Redis Broker
│   │   └── document_worker.py          # Background Chunking, Embedding, & Graph Ingestion
│   │
│   └── utils/
│       ├── text_processing.py          # PDF Parser & Semantic Chunking Logic
│       └── logger.py                   # Structured JSON Logger Configuration
│
└── eval/
    ├── golden_dataset.json             # Test Queries & Ground Truth Criteria
    └── test_rag_accuracy.py            # Ragas / DeepEval Verification Script