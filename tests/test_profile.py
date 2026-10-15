"""The data profile and the import conventions it reads: what a history can support, from its events alone."""
from datetime import timedelta

from fastapi.testclient import TestClient
import pytest

from swarm_lens import Fact, Framework, PluginService
from swarm_lens.adapters.jobs import JobStore
from swarm_lens.application.profile import FORMAT, profile, warnings
from swarm_lens.application.uncertainty import (OrdinalClock, attribution, declared_profile, provenance, time_grade,
                                                unattributed_agent)
from swarm_lens.cli import build_app
from swarm_lens.core.models import DomainError
from swarm_lens.plugins.data_profile import DataProfilePlugin
from swarm_lens.web.api import event_summary
from tests.conftest import AT, Facts


def statuses(report):
    return {name: dimension["status"] for name, dimension in report["dimensions"].items()}


def verdicts(report):
    return {item["analysis"]: item["verdict"] for item in report["supports"]}


def chat(seconds=(0, 5, 9, 30)):
    """Two named agents messaging in one channel, one tool call with a result, at distinct exact times."""
    at = [f"2026-01-01T12:00:{s:02d}+00:00" for s in seconds]
    return [Fact("agent.added", {"id": "a", "name": "A"}, at[0]),
            Fact("agent.added", {"id": "b", "name": "B"}, at[0]),
            Fact("channel.created", {"id": "c", "name": "Shared", "members": ["a", "b"]}, at[0]),
            Fact("message.created", {"id": "m1", "channel_id": "c", "sender_id": "a", "content": "hi"}, at[1]),
            Fact("message.created", {"id": "m2", "channel_id": "c", "sender_id": "b", "content": "hello",
                                     "reply_to_id": "m1"}, at[2]),
            Fact("tool.recorded", {"id": "t1", "agent_id": "a", "tool_name": "search", "status": "completed",
                                   "result": "ok"}, at[3])]


def redacted(rows=4, answered=2):
    """Action-only records: payloads by one unattributed agent, some answered, with ordinal stand-in times."""
    clock = OrdinalClock()
    start = clock.tick()
    facts = [Fact("environment.updated", {"task": "t", "metadata": {"declared_profile": declared_profile(
                 time_grade="ordinal", attribution="unattributed", missing=["timestamps"])}}, start),
             unattributed_agent(start)]
    for index in range(rows):
        running = index < answered
        facts.append(Fact("tool.started" if running else "tool.recorded",
                          {"id": f"p{index}", "agent_id": "unattributed", "tool_name": "payload",
                           "status": "running" if running else "unknown"}, clock.tick(), provenance("ordinal")))
        if running:
            facts.append(Fact("tool.completed", {"id": f"p{index}", "status": "completed", "result": "r"},
                              clock.tick(), provenance("ordinal")))
    return facts


def test_conventions_default_to_exact_named_and_reject_unknown_values():
    assert time_grade({}) == "exact" and time_grade({"time_grade": "ordinal"}) == "ordinal"
    assert time_grade({"time_grade": "someday"}) == "exact"
    assert attribution({}) == "named" and attribution({"attribution": "pseudonymous"}) == "pseudonymous"
    assert provenance("approximate", adapter="x") == {"adapter": "x", "time_grade": "approximate"}
    with pytest.raises(DomainError, match="Time grade"):
        provenance("roughly")
    with pytest.raises(DomainError, match="Attribution"):
        declared_profile(attribution="anonymous")
    agent = unattributed_agent(AT, reason="Redacted")
    assert agent.kind == "agent.added" and agent.data["metadata"] == {
        "attribution": "unattributed", "attribution_reason": "Redacted"}


def test_ordinal_clock_is_increasing_and_far_from_real_recordings():
    clock = OrdinalClock(step=timedelta(milliseconds=10))
    first, second = clock.tick(), clock.tick()
    assert first.startswith("2000-01-01T00:00:00") and second > first
    with pytest.raises(DomainError, match="positive step"):
        OrdinalClock(step=timedelta(0))
    with pytest.raises(DomainError, match="timezone"):
        OrdinalClock("2000-01-01T00:00:00")


def test_dry_run_checks_facts_with_the_reducer_and_saves_nothing(framework):
    events = Framework.dry_run(Facts(*chat()))
    assert [event.position for event in events] == list(range(1, 7))
    assert not framework.store.runs()
    with pytest.raises(DomainError, match="Unknown tool caller"):
        Framework.dry_run(Facts(Fact("tool.recorded", {"id": "t", "agent_id": "ghost", "tool_name": "x"}, AT)))


def test_a_full_conversation_supports_every_analysis():
    report = profile(Framework.dry_run(Facts(*chat())))
    assert report["format"] == FORMAT and report["events"] == 6 and report["declared"] is None
    assert statuses(report) == {"actors": "present", "time": "present", "conversation": "present", "actions": "present"}
    assert set(verdicts(report).values()) == {"supported"}
    assert report["dimensions"]["conversation"]["evidence"]["between_agents"] == 2
    assert warnings(report, "conversation", "actors") == []


def test_redacted_action_records_are_read_as_unattributed_untimed_and_unconversational():
    report = profile(Framework.dry_run(Facts(*redacted())))
    assert statuses(report) == {"actors": "absent", "time": "absent", "conversation": "absent", "actions": "present"}
    assert verdicts(report) == {"timing": "unsupported", "per-agent": "unsupported",
                                "conversation": "unsupported", "actions": "supported"}
    assert report["dimensions"]["actors"]["evidence"]["unattributed"] == 1
    assert report["dimensions"]["time"]["evidence"]["ordinal"] == 6
    assert report["declared"]["attribution"] == "unattributed"
    assert [line.split(":")[0] for line in warnings(report, "conversation", "actors")] == ["Conversation", "Actors"]
    assert profile(Framework.dry_run(Facts(*redacted(answered=1))))["dimensions"]["actions"]["status"] == "partial"


def test_partial_ratings_for_one_speaker_shared_timestamps_and_approximate_times(framework, branch):
    report = profile(framework.history(branch.id))  # One agent, every event at the same instant.
    assert statuses(report) == {"actors": "present", "time": "absent", "conversation": "partial", "actions": "absent"}
    facts = chat()
    facts[4] = Fact(facts[4].kind, facts[4].data, facts[4].occurred_at, provenance("approximate"))
    assert profile(Framework.dry_run(Facts(*facts)))["dimensions"]["time"]["status"] == "partial"
    facts[1] = Fact("agent.added", {"id": "b", "name": "B", "metadata": {"attribution": "pseudonymous"}}, AT)
    assert profile(Framework.dry_run(Facts(*facts)))["dimensions"]["actors"]["evidence"]["pseudonymous"] == 1


def test_human_and_system_messages_are_not_unattributed_agent_actions():
    facts = [*chat()[:3], Fact("message.created", {"id": "h", "channel_id": "c", "role": "human",
                                                   "sender_name": "Admin", "content": "deleted"}, AT)]
    report = profile(Framework.dry_run(Facts(*facts)))
    assert report["dimensions"]["actors"]["evidence"]["actions"] == 0
    assert report["dimensions"]["conversation"]["evidence"]["human_messages"] == 1


def test_plugin_stores_the_profile_as_its_report(framework, branch, tmp_path):
    plugins = PluginService(framework, (DataProfilePlugin(),),
                            jobs=lambda name, label: JobStore(tmp_path / "jobs.sqlite", name, label))
    record = plugins.analyze("data-profile", branch.id, 1, 7)
    assert record["output"]["report"]["format"] == FORMAT
    assert record["output"]["report"]["events"] == 7
    assert plugins.branch_jobs(branch.id, "data-profile")[0]["status"] == "completed"


def test_bundled_view_profiles_a_branch_on_demand(tmp_path):
    with TestClient(build_app(tmp_path)) as client:
        assert "data-profile" in [plugin["id"] for plugin in client.get("/api/plugins").json()["plugins"]]
        web = {plugin["id"]: plugin for plugin in client.get("/api/workspace").json()["capabilities"]["web_plugins"]}
        assert web["data-profile"]["ui"]["module"] == "/assets/plugins/data-profile/index.js"
        branch = client.post("/api/traces", json={"name": "Pasted", "text": "a transcript"}).json()["branch"]
        body = client.get("/api/plugins/data-profile/profile", params={"branch_id": branch["id"]}).json()
        assert body["cursor"] == 2 and body["dimensions"]["conversation"]["status"] == "absent"
        assert client.get("/api/plugins/data-profile/profile",
                          params={"branch_id": branch["id"], "cursor": 1}).json()["events"] == 1
        assert client.get("/api/plugins/data-profile/profile", params={"branch_id": "missing"}).status_code in (400, 404)


def test_event_summaries_carry_the_declared_time_grade():
    exact, ordinal = Framework.dry_run(Facts(*redacted(rows=1, answered=0)))[1:3]
    assert event_summary(exact)["time_grade"] == "exact"
    assert event_summary(ordinal)["time_grade"] == "ordinal"
