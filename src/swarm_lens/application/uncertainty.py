"""Conventions for importing records that are missing actors, clock times, or other context.

The framework does not interpret datasets, so an adapter states what its records lack:

- `source["time_grade"]` on a fact says how far its `occurred_at` can be trusted: `exact` (as recorded),
  `approximate` (rounded, or recorded at a coarser grain) or `ordinal` (a stand-in that keeps only the order).
- `metadata["attribution"]` on an agent says who it stands for: `named` (a known actor), `pseudonymous`
  (a stable label for an unknown actor) or `unattributed` (no actor is known; one agent stands in for all).
- `metadata["declared_profile"]` on an `environment.updated` fact is the adapter's own statement of what the
  records lack and why, so analyses and readers see it inside the history.

None of this changes how facts are applied. A missing field is read as `exact` time and a `named` agent.
"""
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from swarm_lens.core.models import DomainError, Fact

TIME_GRADES = ("exact", "approximate", "ordinal")
ATTRIBUTIONS = ("named", "pseudonymous", "unattributed")
ORDINAL_EPOCH = "2000-01-01T00:00:00+00:00"
UNATTRIBUTED_ID = "unattributed"


def time_grade(source: dict[str, Any]) -> str:
    """The time grade a fact's provenance declares; `exact` when it declares none."""
    grade = source.get("time_grade", "exact")
    return grade if grade in TIME_GRADES else "exact"


def attribution(metadata: dict[str, Any]) -> str:
    """The attribution an agent's metadata declares; `named` when it declares none."""
    value = metadata.get("attribution", "named")
    return value if value in ATTRIBUTIONS else "named"


def provenance(grade: str, **source: Any) -> dict[str, Any]:
    """Fact provenance with a checked time grade; extra keyword arguments are kept as they are."""
    if grade not in TIME_GRADES:
        raise DomainError(f"Time grade must be one of {', '.join(TIME_GRADES)}, got {grade!r}")
    return {**source, "time_grade": grade}


class OrdinalClock:
    """Stand-in timestamps for records that keep only their order: one `step` apart from a fixed epoch.

    The epoch is deliberately far from any real recording, so an ordinal time is not mistaken for a real one.
    Facts stamped by this clock should declare `time_grade="ordinal"` (see `provenance`).
    """

    def __init__(self, start: str = ORDINAL_EPOCH, step: timedelta = timedelta(seconds=1)):
        if step <= timedelta(0):
            raise DomainError("An ordinal clock needs a positive step")
        moment = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise DomainError("An ordinal clock's start needs a timezone")
        self._next, self.step = moment.astimezone(timezone.utc), step

    def tick(self) -> str:
        """The next timestamp; each call is one step later than the last."""
        moment, self._next = self._next, self._next + self.step
        return moment.isoformat()


def unattributed_agent(at: str, *, agent_id: str = UNATTRIBUTED_ID, name: str = "Unattributed (redacted)",
                       reason: str = "The records do not say which agent acted.", **source: Any) -> Fact:
    """An `agent.added` fact for the one agent that stands in for every actor the records do not name.

    The reducer requires an agent for tool calls, so action-only records attach them to this agent.
    """
    return Fact("agent.added", {"id": agent_id, "name": name,
                                "metadata": {"attribution": "unattributed", "attribution_reason": reason}}, at, source)


def declared_profile(*, time_grade: str = "exact", attribution: str = "named", missing: Iterable[str] = (),
                     notes: str = "") -> dict[str, Any]:
    """The adapter's statement of what its records lack, for `environment.updated` metadata["declared_profile"]."""
    if time_grade not in TIME_GRADES:
        raise DomainError(f"Time grade must be one of {', '.join(TIME_GRADES)}, got {time_grade!r}")
    if attribution not in ATTRIBUTIONS:
        raise DomainError(f"Attribution must be one of {', '.join(ATTRIBUTIONS)}, got {attribution!r}")
    return {"time_grade": time_grade, "attribution": attribution, "missing": list(missing), "notes": notes}
