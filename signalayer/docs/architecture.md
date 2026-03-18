# SignalLayer Architecture

SignalLayer is implemented as a standalone browser chat application rather than a WhatsApp overlay. That preserves the product behavior from the original brief, but removes the fragility of DOM scraping and gives us first-party control over performance, theming, and message instrumentation.

## Subsystem notes

- Browser app layer: owns chat rendering, client-side caching, fast badge classification, and analysis-pane orchestration.
- UI component layer: packages the annotation, tooltip, pane, card, and confidence components into a low-intrusion visual system.
- Backend layer: exposes `POST /analyze` and normalizes the reasoning pipeline into a stable contract.
- AI agent layer: runs the modular claim pipeline and the meta-prompt loop used to generate and refine component prompts.
- Data layer: ships the seed evidence corpus, fixture conversations, and memoized result cache.

## Key interface contracts

- `ChatMessage`: `{ id, author, text, timestamp }`
- `AnalyzeRequest`: `{ message, context, conversationId, messageId }`
- `AnalysisResponse`: `{ messageId, summary, claims, meta }`
- `Claim`: `{ id, text, type, confidence, summary, counter, evidence, status }`

## Notable failure handling

- No claims: return an empty claims list with a reassuring summary instead of an error.
- Conflicting evidence: mark the claim as `contested` and show support plus counterpoints side-by-side.
- Low confidence: keep the badge visible but muted, and explain why confidence is low.
- Backend failure: the browser app preserves the fast local classification and offers retry from the pane.
