const baseChecklist = [
  "Define responsibilities and boundaries clearly.",
  "Respect the shared JSON contracts in the architecture spec.",
  "Handle edge cases, degraded states, and testability.",
  "Keep the implementation MVP-sized but production-shaped.",
  "Prefer explainability and transparency over false certainty."
];

const componentDefinitions = {
  browser_app_layer: {
    goal:
      "Implement the standalone SignalLayer browser chat shell with message timeline, summary bar, badge orchestration, and analysis pane state.",
    constraints: [
      "Do not mutate the original message text.",
      "Fast local pass should keep badge placement under 100ms for the visible viewport.",
      "Async backend updates must reconcile safely with optimistic local state."
    ],
    inputs: [
      "Seed chat conversation fixture",
      "Analysis API responses",
      "Client cache lookups by message hash"
    ],
    outputs: [
      "Rendered chat layout",
      "Inline annotation badges",
      "Tooltip previews",
      "Open/closed analysis pane state"
    ],
    edgeCases: [
      "message has no detectable claims",
      "multiple claims in one message",
      "stale response arrives after a newer request",
      "mobile layout collapses pane"
    ],
    tests: [
      "visible messages render without layout shift",
      "badge clicks open the matching pane state",
      "cache hits bypass duplicate network calls"
    ]
  },
  ui_component_layer: {
    goal:
      "Build reusable React components for the annotation system, evidence display, and confidence visualization.",
    constraints: [
      "Use TailwindCSS with a dark theme.",
      "Keep visuals low-intrusion and readable over chat surfaces.",
      "Components must support loading, empty, ready, and error states."
    ],
    inputs: [
      "ChatMessage props",
      "AnalysisResult props",
      "Selection and interaction handlers"
    ],
    outputs: [
      "Composable React UI primitives",
      "Accessible hover cards and pane cards"
    ],
    edgeCases: [
      "long evidence snippets",
      "very low confidence values",
      "empty evidence arrays",
      "keyboard-only interaction"
    ],
    tests: [
      "components render critical states",
      "confidence bar width is clamped",
      "tooltips do not crash on missing claim data"
    ]
  },
  backend_layer: {
    goal:
      "Implement the analysis API with stable schemas, caching, validation, and graceful fallbacks.",
    constraints: [
      "Return the required `claims` array schema.",
      "Expose CORS for the browser client in development.",
      "Keep the backend dependency footprint reasonable."
    ],
    inputs: [
      "POST /analyze payload",
      "Knowledge corpus",
      "Optional environment-backed LLM provider configuration"
    ],
    outputs: [
      "Structured analysis response",
      "Latency and cache metadata",
      "Predictable error payloads"
    ],
    edgeCases: [
      "invalid JSON body",
      "empty message",
      "provider timeout",
      "retrieval returns no results"
    ],
    tests: [
      "schema validation for valid and invalid requests",
      "cache hit path returns identical payloads",
      "pipeline fallback works without provider credentials"
    ]
  },
  ai_agent_layer: {
    goal:
      "Implement modular reasoning stages and the meta-prompt generation loop.",
    constraints: [
      "Do not rely on one large prompt for the entire pipeline.",
      "Support a deterministic fallback path when no LLM is configured.",
      "Record prompt loop iterations for inspection."
    ],
    inputs: [
      "Message text and conversation context",
      "Retrieved evidence snippets",
      "Component generation context"
    ],
    outputs: [
      "Claim extraction results",
      "Prompt registry entries",
      "Prompt refinement records"
    ],
    edgeCases: [
      "ambiguous opinion phrasing",
      "predictions written as assertions",
      "prompt refinement stalls without net improvement"
    ],
    tests: [
      "claim classifiers produce supported label set",
      "prompt registry output contains required fields",
      "fallback and provider paths share the same schema"
    ]
  },
  data_layer: {
    goal:
      "Provide the seed evidence corpus, fixtures, and cache utilities used by the MVP.",
    constraints: [
      "Keep the corpus local and easy to inspect.",
      "Use stable IDs for fixtures and documents.",
      "Cache keys must be deterministic."
    ],
    inputs: [
      "Knowledge documents",
      "Fixture chat transcripts",
      "Message text for hashing"
    ],
    outputs: [
      "Retrieval candidates",
      "Fixture payloads",
      "Cache entries"
    ],
    edgeCases: [
      "duplicate documents",
      "near-identical message hashes",
      "fixture messages with punctuation-heavy text"
    ],
    tests: [
      "retrieval ranking returns expected top hits",
      "hash function is stable",
      "fixtures conform to shared schema"
    ]
  }
};

export function generate_component_prompt(componentName, context = {}) {
  const definition = componentDefinitions[componentName];

  if (!definition) {
    throw new Error(`Unknown component prompt requested: ${componentName}`);
  }

  return {
    component: componentName,
    context,
    prompt: [
      `You are implementing the SignalLayer component '${componentName}'.`,
      `Primary goal: ${definition.goal}`,
      "",
      "Requirements:",
      ...baseChecklist.map((item) => `- ${item}`),
      "",
      "Constraints:",
      ...definition.constraints.map((item) => `- ${item}`),
      "",
      "Input formats:",
      ...definition.inputs.map((item) => `- ${item}`),
      "",
      "Output formats:",
      ...definition.outputs.map((item) => `- ${item}`),
      "",
      "Edge cases to cover:",
      ...definition.edgeCases.map((item) => `- ${item}`),
      "",
      "Testing requirements:",
      ...definition.tests.map((item) => `- ${item}`),
      "",
      `Additional context: ${JSON.stringify(context)}`
    ].join("\n")
  };
}

export function createPromptRegistry(context = {}) {
  return Object.keys(componentDefinitions).reduce((registry, componentName) => {
    registry[componentName] = generate_component_prompt(
      componentName,
      context[componentName] ?? {}
    );
    return registry;
  }, {});
}
