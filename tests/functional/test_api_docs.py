async def test_swagger_ui_and_openapi_are_served(client):
    assert (await client.get("/docs")).status_code == 200
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["info"]["title"] == "Task Tracker API"
    assert {t["name"] for t in spec["tags"]} >= {"projects", "tasks"}


async def test_openapi_documents_error_envelope_and_status_codes(client):
    spec = (await client.get("/openapi.json")).json()
    assert "ErrorEnvelope" in spec["components"]["schemas"]
    create = spec["paths"]["/api/v1/projects"]["post"]["responses"]
    assert {"201", "422", "429", "500"} <= set(create)
    patch = spec["paths"]["/api/v1/tasks/{task_id}/status"]["patch"]["responses"]
    assert {"200", "404", "422"} <= set(patch)
    assert "429" not in spec["paths"]["/api/v1/projects"]["get"]["responses"]
