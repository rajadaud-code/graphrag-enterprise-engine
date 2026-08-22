import asyncio
import sys
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
MASTER_KEY = "grag_master_admin_secret_key_2026"
DEV_KEY = "grag_dev_tenant_default_key_2026"


async def run_tests():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0, follow_redirects=True) as client:
        print("=== Test 1: Root & Health Check ===")
        res = await client.get("/")
        print("Root response:", res.status_code, res.json())
        assert res.status_code == 200

        res_health = await client.get("/api/v1/health/")
        print("Health status:", res_health.status_code, res_health.json())
        assert res_health.status_code in [200, 503]

        print("\n=== Test 2: Auth Verification with Default Dev Key ===")
        res_auth_dev = await client.get("/api/v1/auth/verify", headers={"X-API-Key": DEV_KEY})
        print("Auth Dev Key:", res_auth_dev.status_code, res_auth_dev.json())
        assert res_auth_dev.status_code == 200
        assert res_auth_dev.json()["tenant"]["tenant_id"] == "default_tenant"

        print("\n=== Test 3: Create API Key for Tenant Alpha & Tenant Beta ===")
        res_key_a = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-API-Key": MASTER_KEY},
            json={
                "tenant_id": "tenant_alpha",
                "client_name": "Alpha Technologies",
                "description": "Alpha Tech Chat Widget Key",
            },
        )
        print("Created Key A:", res_key_a.status_code, res_key_a.json())
        assert res_key_a.status_code == 201
        key_alpha = res_key_a.json()["api_key"]

        res_key_b = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-API-Key": MASTER_KEY},
            json={
                "tenant_id": "tenant_beta",
                "client_name": "Beta Financial",
                "description": "Beta Finance Chat Widget Key",
            },
        )
        print("Created Key B:", res_key_b.status_code, res_key_b.json())
        assert res_key_b.status_code == 201
        key_beta = res_key_b.json()["api_key"]

        print("\n=== Test 4: Verify Newly Generated API Keys ===")
        verify_a = await client.get("/api/v1/auth/verify", headers={"X-API-Key": key_alpha})
        print("Verify A:", verify_a.status_code, verify_a.json())
        assert verify_a.status_code == 200
        assert verify_a.json()["tenant"]["tenant_id"] == "tenant_alpha"

        verify_b = await client.get(f"/api/v1/auth/verify?api_key={key_beta}")
        print("Verify B (query param):", verify_b.status_code, verify_b.json())
        assert verify_b.status_code == 200
        assert verify_b.json()["tenant"]["tenant_id"] == "tenant_beta"

        print("\n=== Test 5: Ingest Document for Tenant Alpha ===")
        # Test file upload with tenant_id form field
        with open("sample_test.pdf", "rb") as f:
            pdf_bytes = f.read()

        ingest_res_a = await client.post(
            "/api/v1/ingest",
            headers={"X-API-Key": key_alpha},
            files={"file": ("sample_alpha.pdf", pdf_bytes, "application/pdf")},
            data={"tenant_id": "tenant_alpha"},
        )
        print("Ingest Tenant Alpha:", ingest_res_a.status_code, ingest_res_a.json())
        assert ingest_res_a.status_code == 202
        assert ingest_res_a.json()["tenant_id"] == "tenant_alpha"

        print("\n=== Test 6: Ingest Document for Tenant Beta ===")
        ingest_res_b = await client.post(
            "/api/v1/ingest",
            headers={"X-API-Key": key_beta},
            files={"file": ("sample_beta.pdf", pdf_bytes, "application/pdf")},
            data={"tenant_id": "tenant_beta"},
        )
        print("Ingest Tenant Beta:", ingest_res_b.status_code, ingest_res_b.json())
        assert ingest_res_b.status_code == 202
        assert ingest_res_b.json()["tenant_id"] == "tenant_beta"

        print("\n=== Test 7: Multi-Turn Chat & Stateful Session Memory (Tenant Alpha) ===")
        import uuid
        session_id = f"test_sess_alpha_{uuid.uuid4().hex[:6]}"
        chat_turn_1 = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": key_alpha},
            json={
                "question": "What is GraphRAG and what are its main components?",
                "session_id": session_id,
            },
        )
        print("Turn 1 Response:", chat_turn_1.status_code, {k: v if k != "answer" else f"{v[:80]}..." for k, v in chat_turn_1.json().items()})
        assert chat_turn_1.status_code == 200
        assert chat_turn_1.json()["tenant_id"] == "tenant_alpha"
        assert chat_turn_1.json()["session_id"] == session_id

        # Turn 2: Follow-up question testing session history
        chat_turn_2 = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": key_alpha},
            json={
                "question": "Can you summarize what we just discussed in one sentence?",
                "session_id": session_id,
            },
        )
        print("Turn 2 Response (Memory):", chat_turn_2.status_code, {k: v if k != "answer" else f"{v[:80]}..." for k, v in chat_turn_2.json().items()})
        assert chat_turn_2.status_code == 200
        assert chat_turn_2.json()["tenant_id"] == "tenant_alpha"

        print("\n=== Test 8: Tenant Cross-Query Protection ===")
        # Attempt to query tenant_beta using tenant_alpha API key -> Should be rejected with 403 Forbidden
        bad_query = await client.post(
            "/api/v1/chat",
            headers={"X-API-Key": key_alpha},
            json={
                "question": "Show me private data",
                "tenant_id": "tenant_beta",
                "session_id": "hack_attempt",
            },
        )
        print("Cross-tenant violation response:", bad_query.status_code, bad_query.json())
        assert bad_query.status_code == 403

        print("\n=== Test 9: CORS Headers Verification for Embeddable Widget ===")
        cors_res = await client.options(
            "/api/v1/chat",
            headers={
                "Origin": "https://random-client-website.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-API-Key, Content-Type",
            },
        )
        print("CORS Preflight Headers:", cors_res.status_code, dict(cors_res.headers))
        assert "access-control-allow-origin" in cors_res.headers

        print("\n*** ALL MULTI-TENANT SAAS ARCHITECTURE TESTS PASSED SUCCESSFULLY! ***")


if __name__ == "__main__":
    asyncio.run(run_tests())
