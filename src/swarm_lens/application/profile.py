"""What a branch's history can support: which kinds of evidence it holds, and how far each can be trusted.

The profile reads imported events only, never the source dataset, so it works on every run. It counts what the
history holds along four dimensions (actors, time, conversation and actions), rates each `present`, `partial`
or `absent`, and turns the ratings into plain verdicts for common analyses. An adapter's declarations (see
`uncertainty`) refine the counts: an ordinal time grade is never read as real time, and an unattributed agent
never counts as a named actor.
"""
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from swarm_lens.core.models import Event
from .uncertainty import attribution, time_grade

FORMAT = "swarm-lens.data-profile/v1"
ACTIVITY = ("message.", "tool.", "memory.", "observation.")
# A dimension counts as present at or above this share of its evidence, and partial above zero.
PRESENT_SHARE = 0.9
TIED_LIMIT = 0.5


def _share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _status(share: float, present: float = PRESENT_SHARE) -> str:
    return "present" if share >= present else "partial" if share > 0 else "absent"


def actors(events: list[Event], agents: dict[str, str]) -> dict[str, Any]:
    """Who acted: the share of activity events tied to a named or pseudonymous agent."""
    acting = attributed = 0
    for event in events:
        if not event.kind.startswith(ACTIVITY) or event.kind in ("tool.completed",):
            continue
        actor = event.data.get("sender_id") or event.data.get("agent_id") or event.data.get("owner_id")
        if event.kind == "message.created" and event.data.get("role") in ("human", "system"):
            continue  # People and simulators are known speakers, not agents to attribute.
        acting += 1
        attributed += agents.get(actor) in ("named", "pseudonymous")
    kinds = Counter(agents.values())
    share = _share(attributed, acting)
    note = (f"{attributed} of {acting} agent actions name the agent." if acting
            else "No agent actions were recorded.")
    return {"status": _status(share), "evidence": {"agents": len(agents), **{k: kinds.get(k, 0) for k in
                                                   ("named", "pseudonymous", "unattributed")},
                                                   "actions": acting, "attributed": attributed,
                                                   "attributed_share": share}, "note": note}


def time(events: list[Event]) -> dict[str, Any]:
    """When things happened: declared time grades, ties and order of the activity events' timestamps."""
    activity = [event for event in events if event.kind.startswith(ACTIVITY)]
    grades = Counter(time_grade(event.source) for event in activity)
    stamps = [event.occurred_at for event in activity]
    tied = sum(1 for before, after in zip(stamps, stamps[1:]) if before == after)
    backwards = sum(1 for before, after in zip(stamps, stamps[1:]) if after < before)
    real = grades["exact"] + grades["approximate"]
    tied_share = _share(tied, max(len(stamps) - 1, 0))
    if not activity:
        status, note = "absent", "No activity events have timestamps."
    elif grades["ordinal"] * 2 >= len(activity):
        status, note = "absent", "Timestamps are stand-ins that keep only the order of events."
    elif len(set(stamps)) <= 1 and len(stamps) > 1:
        status, note = "absent", "Every activity event has the same timestamp."
    elif grades["approximate"] or grades["ordinal"] or tied_share > TIED_LIMIT:
        status, note = "partial", "Some timestamps are approximate, stand-ins, or shared by many events."
    else:
        status, note = "present", "Timestamps are recorded as they happened."
    return {"status": status, "evidence": {"events": len(activity), "exact": grades["exact"],
                                           "approximate": grades["approximate"], "ordinal": grades["ordinal"],
                                           "real_share": _share(real, len(activity)),
                                           "distinct_timestamps": len(set(stamps)), "tied_share": tied_share,
                                           "out_of_order": backwards}, "note": note}


def conversation(events: list[Event]) -> dict[str, Any]:
    """Who talked to whom: agent messages in channels where two or more agents posted."""
    senders, by_channel, roles = Counter(), defaultdict(set), Counter()
    agent_messages = []
    for event in events:
        if event.kind != "message.created":
            continue
        data = event.data
        roles[data.get("role", "agent")] += 1
        if data.get("role", "agent") == "agent" and data.get("sender_id"):
            senders[data["sender_id"]] += 1
            by_channel[data["channel_id"]].add(data["sender_id"])
            agent_messages.append(data["channel_id"])
    shared = {channel for channel, members in by_channel.items() if len(members) > 1}
    between = sum(1 for channel in agent_messages if channel in shared)
    messages = sum(roles.values())
    share = _share(between, len(agent_messages))
    if not messages:
        status, note = "absent", "The history holds no messages."
    elif not between:
        status, note = "partial", "Messages exist, but no channel has messages from two or more agents."
    else:
        status = _status(share, 0.5)
        note = f"{between} of {len(agent_messages)} agent messages are in channels that two or more agents post to."
    return {"status": status, "evidence": {"messages": messages, "agent_messages": len(agent_messages),
                                           "human_messages": roles["human"], "system_messages": roles["system"],
                                           "senders": len(senders), "shared_channels": len(shared),
                                           "between_agents": between, "between_share": share}, "note": note}


def actions(events: list[Event]) -> dict[str, Any]:
    """What agents did: tool calls, how many reached a final status, and recorded observations."""
    calls, final = set(), set()
    observations = 0
    for event in events:
        if event.kind in ("tool.recorded", "tool.started"):
            calls.add(event.data["id"])
        if event.kind in ("tool.recorded", "tool.completed") and event.data.get("status") in ("completed", "failed"):
            final.add(event.data["id"])
        observations += event.kind == "observation.recorded"
    share = _share(len(final), len(calls))
    if calls:
        status = "present" if share >= 0.5 else "partial"
        note = f"{len(final)} of {len(calls)} tool calls have a recorded result."
    elif observations:
        status, note = "partial", "No tool calls; only free-form observations were recorded."
    else:
        status, note = "absent", "No tool calls or observations were recorded."
    return {"status": status, "evidence": {"tool_calls": len(calls), "with_result": len(final),
                                           "result_share": share, "observations": observations}, "note": note}


VERDICTS = {"present": "supported", "partial": "caution", "absent": "unsupported"}


def supports(dimensions: dict[str, dict]) -> list[dict[str, str]]:
    """Plain verdicts for common analyses, each with the dimension it rests on."""
    def verdict(analysis: str, needs: str, purpose: str) -> dict[str, str]:
        dimension = dimensions[needs]
        return {"analysis": analysis, "needs": needs, "verdict": VERDICTS[dimension["status"]],
                "reason": f"{purpose} {dimension['note']}"}

    return [verdict("timing", "time", "Rates, delays and gaps need real timestamps."),
            verdict("per-agent", "actors", "Comparing agents needs actions tied to agents."),
            verdict("conversation", "conversation", "Conversation analyses such as MAST need agents messaging each other."),
            verdict("actions", "actions", "Action analyses need tool calls and their results.")]


def declared(events: Iterable[Event]) -> dict[str, Any] | None:
    """The adapter's latest declared profile, from environment metadata; None when it declared none."""
    statement = None
    for event in events:
        if event.kind == "environment.updated":
            statement = (event.data.get("metadata") or {}).get("declared_profile", statement)
    return statement


def profile(events: list[Event]) -> dict[str, Any]:
    """The data profile of a history, as JSON-ready data."""
    agents: dict[str, str] = {}
    for event in events:
        if event.kind in ("agent.added", "agent.updated") and event.data.get("id"):
            agents[event.data["id"]] = attribution(event.data.get("metadata") or {})
    dimensions = {"actors": actors(events, agents), "time": time(events),
                  "conversation": conversation(events), "actions": actions(events)}
    return {"format": FORMAT, "events": len(events), "dimensions": dimensions,
            "supports": supports(dimensions), "declared": declared(events)}


def warnings(report: dict[str, Any], *needs: str) -> list[str]:
    """Plain warnings for the dimensions an analysis rests on that are not fully present."""
    return [f"{name.capitalize()}: {report['dimensions'][name]['note']}" for name in needs
            if report["dimensions"][name]["status"] != "present"]
