import pytest

from worker.store import Store
from worker.tools.files import EXPORT_COLUMNS, WorkspaceFiles
from worker.verify.probes import Probes


@pytest.mark.asyncio
async def test_workspace_probe_keeps_empty_csv_header_and_approval_state(tmp_path):
    store = Store(tmp_path / "worker.db")
    WorkspaceFiles(tmp_path / "workspace").write_csv("empty.csv", [])
    probes = Probes(probe_key="test", register_session="test", workspace=tmp_path / "workspace",
                    store=store)
    try:
        rows = await probes.workspace_csv("exports/empty.csv")
        assert rows == []
        assert rows.columns == list(EXPORT_COLUMNS)
        assert not await probes.approval_recorded("r1")
        store.save_approval("a1", "r1", {"status": "approved"})
        assert await probes.approval_recorded("r1")
    finally:
        await probes.close()
