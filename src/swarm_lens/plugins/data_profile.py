"""The data profile as a stored analysis: what the analyzed events can support, as one report."""
from swarm_lens.application.profile import profile
from swarm_lens.plugins import Report


class DataProfilePlugin:
    id, version = "data-profile", "1.0.0"
    title = "Data profile"
    description = "Which actors, timestamps, conversations and actions the history holds, and what that supports."

    def analyze(self, view, start, end, params):
        yield Report(profile(view.events(start, end)))


def create(services):
    return DataProfilePlugin()
