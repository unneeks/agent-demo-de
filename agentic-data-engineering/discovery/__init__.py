"""Repository discovery -- turns a real project into real graph state.

Every source kind (dbt SQL, Terraform, CI/CD YAML, Dockerfiles, docker-compose,
Markdown) is interpreted by one uniform agent-based extraction path
(`discovery.extraction`), never a per-tool parser. `discovery.walk` finds and
classifies files, deterministically. `discovery.resolve` resolves symbolic
relationship targets against what a run has already extracted,
deterministically. `discover_project` (`discovery.orchestrate`) wires all of
it together and writes exclusively through `ProjectGraphService` -- nothing
here touches `persistence.ports` directly.
"""

from discovery.errors import DiscoveryError
from discovery.orchestrate import discover_project
from discovery.result import DiscoveryFailure, DiscoveryReport, DiscoveryResult, DiscoverySkip

__all__ = [
    "DiscoveryError",
    "DiscoveryFailure",
    "DiscoveryReport",
    "DiscoveryResult",
    "DiscoverySkip",
    "discover_project",
]
