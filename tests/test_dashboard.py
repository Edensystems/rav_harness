def test_dashboard_stats_empty(client, auth_headers):
    resp = client.get("/api/dashboard/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_runs"] == 0
    assert data["active_runs"] == 0
    assert data["success_rate"] is None
    assert data["list_count"] == 0
