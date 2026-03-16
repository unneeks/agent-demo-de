# DATA_MODEL

## Core Entity: Tradition

```ts
type StrengthBand = "low" | "medium" | "high";
type VedicRelation = "outside" | "core" | "hybrid" | "reform";
type ConfidenceBand = "low" | "medium" | "high";

type Tradition = {
  id: string;
  name: string;
  category: string;
  originTime: number;
  declineTime: number | null;
  geographicOrigin: string;
  regions: string[];
  ritualStructure: string;
  socialStructure: string;
  textualDependence: StrengthBand;
  institutionalStrength: {
    start: StrengthBand;
    end: StrengthBand;
  };
  civilizationalLayer: string;
  parentTraditionIds: string[];
  influenceIds: string[];
  vedicRelation: VedicRelation;
  confidence: ConfidenceBand;
  notes: string;
};
```

## Design Notes

- `originTime` and `declineTime` use signed years. Negative values represent BCE.
- `declineTime: null` means the tradition persists to the present.
- `parentTraditionIds` captures lineage or absorption relationships.
- `influenceIds` is a temporary shortcut for Phase 1. It will become an edge
  table with typed relations and citations in later phases.
- `confidence` marks how safe the current prototype record is for visualization.
- `notes` is required so uncertainty and aggregation choices are explicit.

## Planned Additions

- `sources`: citation array for each record
- `evidenceLevel`: explicit sourcing maturity
- `geoOrigins`: normalized region/entity IDs
- `aliases`: multilingual and alternate names
- `attributes`: arbitrary key-value trait bag for advanced querying
