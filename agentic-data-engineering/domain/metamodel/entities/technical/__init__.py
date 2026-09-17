"""Technical Twin: what has actually been built.

Everything here is *discovered*, never declared, so every class extends
``ProvenancedEntity``. An adapter that reads a dbt manifest records ``OBSERVED``;
one that concludes a dependency from a naming convention records ``INFERRED``
with a confidence.
"""

from domain.metamodel.entities.technical.assets import (
    DataAsset,
    Pipeline,
    SchemaDefinition,
)
from domain.metamodel.entities.technical.change import Change, Deployment, Incident
from domain.metamodel.entities.technical.infrastructure import (
    ArchitectureElement,
    CloudResource,
    Infrastructure,
)
from domain.metamodel.entities.technical.profile import DataProfile
from domain.metamodel.entities.technical.project import CodeArtifact, Project, Repository
from domain.metamodel.entities.technical.tests import Test

__all__ = [
    "ArchitectureElement",
    "Change",
    "CloudResource",
    "CodeArtifact",
    "DataAsset",
    "DataProfile",
    "Deployment",
    "Incident",
    "Infrastructure",
    "Pipeline",
    "Project",
    "Repository",
    "SchemaDefinition",
    "Test",
]
