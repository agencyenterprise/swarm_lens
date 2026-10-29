"""The data profile web plugin: a route that profiles a branch on demand, and its view in static/."""
from pathlib import Path

from fastapi import APIRouter, Query

from swarm_lens.application.profile import profile
from swarm_lens.plugins.data_profile import DataProfilePlugin
from swarm_lens.web.extensions import PluginServices, WebExtension


def data_profile_extension(framework) -> WebExtension:
    router = APIRouter(prefix="/api/plugins/data-profile", tags=["Data profile"])

    @router.get("/profile")
    def branch_profile(branch_id: str = Query(min_length=1, max_length=100), cursor: int | None = Query(None, ge=0)):
        """Computed from events 1..cursor (the head by default); nothing is saved and no model is called."""
        branch = framework.store.branch(branch_id)
        cursor = branch.head if cursor is None else min(cursor, branch.head)
        return {"branch_id": branch_id, "cursor": cursor, **profile(framework.history(branch_id, cursor))}

    return WebExtension("data-profile", router, lambda: {"title": "Data profile", "version": DataProfilePlugin.version},
                        assets=Path(__file__).parent / "static")


def create(services: PluginServices):
    """The analyzer, so a profile can be saved with a branch's analyses, and the on-demand view."""
    return [DataProfilePlugin(), data_profile_extension(services.framework)]
