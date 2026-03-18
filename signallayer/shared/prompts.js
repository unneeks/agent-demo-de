const BASE_COMPONENT_TEMPLATE = {
  requirements: [],
  constraints: [],
  inputs: {},
  outputs: {},
  edgeCases: [],
  testing: []
};

export function generateComponentPrompt(componentName, context = {}) {
  const {
    role = "SignalLayer subsystem",
    objective = "Implement the component to satisfy the declared interface and product principles.",
    requirements = [],
    constraints = [],
    inputs = {},
    outputs = {},
    edgeCases = [],
    testing = [],
    dependencies = []
  } = context;

  return {
    component: componentName,
    role,
    objective,
    requirements: [...BASE_COMPONENT_TEMPLATE.requirements, ...requirements],
    constraints: [...BASE_COMPONENT_TEMPLATE.constraints, ...constraints],
    inputs: { ...BASE_COMPONENT_TEMPLATE.inputs, ...inputs },
    outputs: { ...BASE_COMPONENT_TEMPLATE.outputs, ...outputs },
    edgeCases: [...BASE_COMPONENT_TEMPLATE.edgeCases, ...edgeCases],
    testing: [...BASE_COMPONENT_TEMPLATE.testing, ...testing],
    dependencies,
    prompt: [
      `Component: ${componentName}`,
      `Role: ${role}`,
      `Objective: ${objective}`,
      "",
      "Requirements:",
      ...requirements.map((item, index) => `${index + 1}. ${item}`),
      "",
      "Constraints:",
      ...constraints.map((item, index) => `${index + 1}. ${item}`),
      "",
      "Input Contract:",
      JSON.stringify(inputs, null, 2),
      "",
      "Output Contract:",
      JSON.stringify(outputs, null, 2),
      "",
      "Edge Cases:",
      ...edgeCases.map((item, index) => `${index + 1}. ${item}`),
      "",
      "Testing Requirements:",
      ...testing.map((item, index) => `${index + 1}. ${item}`),
      "",
      dependencies.length
        ? `Dependencies: ${dependencies.join(", ")}`
        : "Dependencies: none",
      "",
      "Implementation expectations: keep interfaces explicit, preserve host stability, and prefer explainable behavior over hidden heuristics."
    ].join("\n")
  };
}

export function validateComponentResult(componentName, implementation = {}, registry = promptRegistry) {
  const spec = registry[componentName];
  if (!spec) {
    return {
      valid: false,
      missing: [`Unknown component: ${componentName}`]
    };
  }

  const missing = [];

  for (const requirement of spec.requirements) {
    const key = requirement.toLowerCase();
    const summary = JSON.stringify(implementation).toLowerCase();
    if (!summary.includes(key.split(" ").slice(0, 2).join(" "))) {
      missing.push(requirement);
    }
  }

  return {
    valid: missing.length === 0,
    missing
  };
}

export function generateRefinementPrompt(componentName, implementation = {}, registry = promptRegistry) {
  const validation = validateComponentResult(componentName, implementation, registry);
  if (validation.valid) {
    return {
      component: componentName,
      prompt: `Component ${componentName} satisfies the registered requirements. No refinement needed.`
    };
  }

  return {
    component: componentName,
    prompt: [
      `Refine component: ${componentName}`,
      "The current implementation is incomplete.",
      "Missing or weak requirements:",
      ...validation.missing.map((item, index) => `${index + 1}. ${item}`),
      "",
      "Rework the component while preserving existing contracts and tests."
    ].join("\n")
  };
}

const promptContexts = {
  extension_layer: {
    role: "Chrome extension runtime",
    objective: "Parse WhatsApp Web messages, inject lightweight badges, and coordinate backend analysis without altering original content.",
    requirements: [
      "Use MutationObserver to detect visible message nodes.",
      "Assign stable message IDs and hashes for caching.",
      "Inject badges, tooltips, and a sidebar trigger with minimal layout shift.",
      "Support a two-pass flow: immediate local heuristic plus async backend enrichment."
    ],
    constraints: [
      "Do not modify original message text content.",
      "Keep UI injection under 100ms p95 for newly observed messages.",
      "Avoid duplicate analysis calls for the same messageHash.",
      "Degrade gracefully if selectors fail or backend is unavailable."
    ],
    inputs: {
      dom: "WhatsApp chat message elements",
      events: ["hover", "click", "mutation"],
      cache: "messageHash -> analysis result"
    },
    outputs: {
      normalizedMessages: "MessageRecord[]",
      analysisRequests: "AnalyzeRequest[]",
      uiStateUpdates: "Badge/tooltip/sidebar state"
    },
    edgeCases: [
      "Messages containing emojis, links, or line breaks.",
      "Re-rendered WhatsApp nodes causing duplicate observers.",
      "Quoted replies where visible text differs from underlying claim."
    ],
    testing: [
      "Simulate WhatsApp DOM with multiple message layouts.",
      "Verify duplicate mutations do not create duplicate badges.",
      "Verify failures keep the host page usable."
    ],
    dependencies: ["shared/contracts", "backend /analyze"]
  },
  ui_component_layer: {
    role: "React UI system",
    objective: "Render compact, dark-themed analysis surfaces that feel native-adjacent but clearly separate from WhatsApp UI.",
    requirements: [
      "Implement AnnotationBadge, MessageDecorator, TooltipCard, AnalysisPane, ClaimCard, EvidenceList, and ConfidenceBar.",
      "Use progressive disclosure so low-attention users can ignore the overlay.",
      "Represent loading, no-claim, low-confidence, conflict, and error states."
    ],
    constraints: [
      "Avoid obscuring message text or native controls.",
      "Keep visuals readable in dense chat layouts.",
      "Prefer isolated styling and deterministic rendering."
    ],
    inputs: {
      viewModels: "MessageAnalysisViewModel",
      actions: "open/close/retry/select-claim"
    },
    outputs: {
      elements: "Rendered extension nodes",
      callbacks: "User interaction events"
    },
    edgeCases: [
      "Very long evidence snippets.",
      "No claims detected.",
      "Conflicting evidence with low confidence."
    ],
    testing: [
      "Render each component state.",
      "Verify sidebar opens without shifting host content excessively.",
      "Verify tooltip truncation and overflow handling."
    ],
    dependencies: ["extension store", "shared contracts"]
  },
  backend_layer: {
    role: "Analysis API service",
    objective: "Accept structured analyze requests and return normalized claim analysis with latency metadata and cache state.",
    requirements: [
      "Expose POST /analyze and GET /health.",
      "Validate request payloads and always return stable JSON shapes.",
      "Implement in-memory messageHash caching.",
      "Support fast pass plus deeper reasoning pass."
    ],
    constraints: [
      "Keep implementation lightweight enough to run locally.",
      "Return no_claims instead of empty ambiguous success payloads.",
      "Do not crash on malformed or empty context arrays."
    ],
    inputs: {
      request: {
        message: "string",
        context: "MessageContext[]",
        messageId: "string",
        conversationId: "string",
        messageHash: "string"
      }
    },
    outputs: {
      response: "AnalyzeResponse"
    },
    edgeCases: [
      "Blank message text.",
      "Repeated analyze calls with same hash.",
      "Reasoning exceptions in one sub-step."
    ],
    testing: [
      "Contract test for happy path response shape.",
      "Validation test for bad requests.",
      "Cache hit test."
    ],
    dependencies: ["ai agent layer", "data layer"]
  },
  ai_agent_layer: {
    role: "Reasoning orchestrator",
    objective: "Break analysis into transparent steps so the product can explain why a badge or confidence score was produced.",
    requirements: [
      "Separate extraction, classification, retrieval, counter generation, and scoring.",
      "Allow heuristic fallback when no LLM is configured.",
      "Emit evidence with stance labels."
    ],
    constraints: [
      "Do not rely on a single monolithic prompt.",
      "Prefer deterministic heuristics when confidence is low.",
      "Make confidence sensitive to conflicting evidence and weak retrieval."
    ],
    inputs: {
      message: "MessageRecord",
      context: "MessageContext[]",
      retrievalHits: "EvidenceHit[]"
    },
    outputs: {
      claims: "Claim[]",
      trace: "ReasoningTrace"
    },
    edgeCases: [
      "Opinion mixed with factual clause.",
      "Prediction stated as certainty.",
      "Contradictory conversational context."
    ],
    testing: [
      "Unit tests for claim type classification.",
      "Confidence scoring regression tests.",
      "Fallback mode without external LLM."
    ],
    dependencies: ["retrieval index", "optional llm client"]
  },
  data_layer: {
    role: "Shared data and retrieval support",
    objective: "Provide stable schemas, deterministic hashing, lightweight corpus search, and cache-safe utilities.",
    requirements: [
      "Define reusable contracts shared by backend and extension.",
      "Provide a small curated evidence corpus for MVP retrieval.",
      "Support simple text scoring for RAG-lite search."
    ],
    constraints: [
      "Must work fully offline for local MVP.",
      "Avoid schema drift across runtime boundaries."
    ],
    inputs: {
      documents: "KnowledgeDocument[]",
      records: "MessageRecord|AnalyzeResponse"
    },
    outputs: {
      evidenceHits: "EvidenceHit[]",
      hashes: "string",
      normalizedContracts: "plain JSON"
    },
    edgeCases: [
      "Punctuation-heavy messages.",
      "Near-duplicate hashes with small edits.",
      "Corpus misses causing empty evidence."
    ],
    testing: [
      "Hash stability tests.",
      "Retrieval ranking tests.",
      "Schema shape tests."
    ],
    dependencies: ["none"]
  }
};

export const promptRegistry = Object.fromEntries(
  Object.entries(promptContexts).map(([name, context]) => [
    name,
    generateComponentPrompt(name, context)
  ])
);
