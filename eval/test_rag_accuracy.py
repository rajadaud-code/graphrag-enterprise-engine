import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure parent directory is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from groq import Groq

from app.core.config import settings
from app.main import app

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RAGEvaluation")

GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.json"

FAITHFULNESS_PROMPT = """You are an expert RAG Evaluation Judge.
Evaluate the Faithfulness of the Generated Answer relative to the Provided Context.

Step 1: Extract all factual claims made in the Generated Answer.
Step 2: For each claim, check if it is directly supported by the Provided Context (Vector Chunks + Knowledge Graph Triples).
Step 3: Calculate Faithfulness Score = (Number of Supported Claims) / (Total Number of Extracted Claims). If no claims, return 1.0.

Return ONLY a JSON object with this exact schema:
{{
  "reasoning": "Step-by-step analysis of claims and context alignment",
  "claims": ["List of extracted claims"],
  "supported_claims_count": 0,
  "total_claims_count": 0,
  "faithfulness_score": 0.95
}}

Question: {question}
Provided Context:
\"\"\"{context}\"\"\"

Generated Answer:
\"\"\"{answer}\"\"\"
"""

CONTEXT_PRECISION_PROMPT = """You are an expert RAG Evaluation Judge.
Evaluate the Context Precision of the retrieved context relative to the Question and Expected Answer.

Step 1: Inspect each retrieved context chunk in rank order (chunk 1, chunk 2, chunk 3...).
Step 2: Determine if each chunk contains relevant information required to answer the question.
Step 3: Evaluate if higher-ranked chunks (chunk 1 > chunk 2 > chunk 3) contain more relevant information than lower-ranked ones.
Step 4: Output a Context Precision Score as a float between 0.0 and 1.0 (1.0 = perfect ranking, 0.0 = completely irrelevant context).

Return ONLY a JSON object with this exact schema:
{{
  "reasoning": "Step-by-step ranking order analysis",
  "context_precision_score": 0.90
}}

Question: {question}
Expected Answer: {expected_answer}
Retrieved Context Chunks:
\"\"\"{context}\"\"\"
"""


def call_llm_judge(prompt: str) -> Dict[str, Any]:
    """Call Groq API (llama-3.3-70b-versatile) with strict JSON mode for evaluation metrics."""
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is missing in configuration.")

    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = (response.choices[0].message.content or "{}").strip()
    try:
        return json.loads(content)
    except Exception as exc:
        logger.error(f"Failed to parse LLM judge response: {exc}")
        return {}


async def evaluate_rag_pipeline():
    """Run full automated evaluation against golden_dataset.json and calculate benchmark scores."""
    if not GOLDEN_DATASET_PATH.exists():
        logger.error(f"Golden dataset file not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        test_cases: List[Dict[str, Any]] = json.load(f)

    logger.info(f"Loaded {len(test_cases)} benchmark test cases from {GOLDEN_DATASET_PATH.name}")

    results: List[Dict[str, Any]] = []
    total_faithfulness = 0.0
    total_context_precision = 0.0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=15.0) as client:
        for idx, test in enumerate(test_cases):
            question = test["question"]
            expected_answer = test["expected_answer"]

            logger.info(f"\n--- [Test Case {idx + 1}/{len(test_cases)}] Query: '{question}' ---")

            chat_res = await client.post("/api/v1/chat/", json={"question": question})
            res_data = chat_res.json()

            answer = res_data.get("answer", "")
            vector_ctx = res_data.get("vector_context", [])
            graph_ctx = res_data.get("graph_context", [])
            cached = res_data.get("cached", False)

            combined_context = f"Vector Chunks:\n{json.dumps(vector_ctx, indent=2)}\n\nGraph Triples:\n{json.dumps(graph_ctx, indent=2)}"

            # 2. Evaluate Faithfulness
            f_prompt = FAITHFULNESS_PROMPT.format(
                question=question,
                context=combined_context,
                answer=answer,
            )
            f_eval = call_llm_judge(f_prompt)
            faith_score = float(f_eval.get("faithfulness_score", 0.0))

            # 3. Evaluate Context Precision
            cp_prompt = CONTEXT_PRECISION_PROMPT.format(
                question=question,
                expected_answer=expected_answer,
                context=combined_context,
            )
            cp_eval = call_llm_judge(cp_prompt)
            cp_score = float(cp_eval.get("context_precision_score", 0.0))

            total_faithfulness += faith_score
            total_context_precision += cp_score

            results.append(
                {
                    "question": question,
                    "answer": answer,
                    "cached": cached,
                    "faithfulness_score": faith_score,
                    "context_precision_score": cp_score,
                }
            )

            logger.info(f"Answer: {answer[:100]}...")
            logger.info(f"Faithfulness Score: {faith_score:.2f}")
            logger.info(f"Context Precision Score: {cp_score:.2f}")
            logger.info(f"Cached Response: {cached}")

    avg_faithfulness = total_faithfulness / len(test_cases) if test_cases else 0.0
    avg_context_precision = total_context_precision / len(test_cases) if test_cases else 0.0

    print("\n" + "=" * 80)
    print("                ENTERPRISE GRAPHRAG EVALUATION REPORT                ")
    print("=" * 80)
    print(f" Total Benchmark Test Cases Evaluated : {len(results)}")
    print(f" Average Faithfulness Score           : {avg_faithfulness * 100:.1f}% ({avg_faithfulness:.3f})")
    print(f" Average Context Precision Score      : {avg_context_precision * 100:.1f}% ({avg_context_precision:.3f})")
    print("=" * 80)
    for r in results:
        print(f"• Question : {r['question']}")
        print(f"  Faithfulness: {r['faithfulness_score']:.2f} | Context Precision: {r['context_precision_score']:.2f} | Cached: {r['cached']}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(evaluate_rag_pipeline())
