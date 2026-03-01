"""Tests for global capability config import/export."""


class TestExportCapabilities:
    async def test_export_empty(self, app_client):
        resp = await app_client.get("/api/settings/capabilities/export")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_export_returns_created_configs(self, app_client):
        await app_client.post("/api/settings/capabilities", json={
            "capability": "ai", "provider": "claude_code",
            "enabled": True, "label": "Claude", "config": {"key": "val"},
        })
        resp = await app_client.get("/api/settings/capabilities/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert item["capability"] == "ai"
        assert item["provider"] == "claude_code"
        assert item["enabled"] is True
        assert item["label"] == "Claude"
        assert item["config"] == {"key": "val"}
        assert "id" not in item


class TestImportCapabilities:
    async def test_import_creates_new(self, app_client):
        resp = await app_client.post("/api/settings/capabilities/import", json={
            "configs": [
                {"capability": "ai", "provider": "claude_code", "label": "Claude"},
                {"capability": "scm", "provider": "github", "enabled": False},
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["created"] == 2
        assert body["skipped"] == 0

        # verify via export
        export = await app_client.get("/api/settings/capabilities/export")
        assert len(export.json()) == 2

    async def test_import_skip_existing(self, app_client):
        # seed one config
        await app_client.post("/api/settings/capabilities", json={
            "capability": "ai", "provider": "claude_code",
        })
        # import with duplicate + new
        resp = await app_client.post("/api/settings/capabilities/import", json={
            "configs": [
                {"capability": "ai", "provider": "claude_code"},
                {"capability": "scm", "provider": "github"},
            ],
            "skip_existing": True,
        })
        body = resp.json()
        assert body["created"] == 1
        assert body["skipped"] == 1

    async def test_import_empty_list(self, app_client):
        resp = await app_client.post("/api/settings/capabilities/import", json={
            "configs": [],
        })
        body = resp.json()
        assert body["ok"] is True
        assert body["created"] == 0
        assert body["skipped"] == 0


class TestRoundTrip:
    async def test_export_then_import(self, app_client):
        """Export from one state, clear, re-import — should restore."""
        # create configs
        await app_client.post("/api/settings/capabilities", json={
            "capability": "ai", "provider": "claude_code",
            "enabled": True, "label": "AI", "config": {"model": "opus"},
        })
        await app_client.post("/api/settings/capabilities", json={
            "capability": "scm", "provider": "github",
            "enabled": False, "config": {"token": "xxx"},
        })

        # export
        export_resp = await app_client.get("/api/settings/capabilities/export")
        exported = export_resp.json()
        assert len(exported) == 2

        # delete all
        caps = await app_client.get("/api/settings/capabilities")
        for c in caps.json():
            await app_client.delete(f"/api/settings/capabilities/{c['id']}")

        # verify empty
        empty = await app_client.get("/api/settings/capabilities/export")
        assert empty.json() == []

        # re-import
        import_resp = await app_client.post("/api/settings/capabilities/import", json={
            "configs": exported,
        })
        assert import_resp.json()["created"] == 2

        # verify restored
        restored = await app_client.get("/api/settings/capabilities/export")
        assert len(restored.json()) == 2
