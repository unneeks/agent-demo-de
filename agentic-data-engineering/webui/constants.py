"""Constants shared between the HTML routes (`webui/routes/`) and the JSON
API routes (`webui/api/routes/`) -- kept in exactly one place so the two
surfaces can never silently drift on something load-bearing.
"""

from __future__ import annotations

#: Dimensions no route in this codebase can ever honestly assess -- no
#: assembler for any of them exists anywhere (docs/orchestrator.md's "what
#: this is not"). Named explicitly so a template or a JSON response can
#: single them out rather than presenting all six GateReadiness dimensions
#: as equally trustworthy.
UNASSESSABLE_DIMENSIONS = {"ARTIFACTS", "CHECKLISTS", "EVIDENCE", "APPROVALS"}
