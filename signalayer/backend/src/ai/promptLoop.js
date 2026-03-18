import { createPromptRegistry } from "../../../shared/promptRegistry.js";

export function runPromptLoop(componentName, context) {
  const registry = createPromptRegistry({ [componentName]: context });
  const seed = registry[componentName];
  const refinementNeeded = !context?.interfacesDefined || !context?.testsDefined;

  return {
    seedPrompt: seed.prompt,
    refinements: refinementNeeded
      ? [
          {
            iteration: 1,
            prompt: `${seed.prompt}\n\nRefinement: tighten interfaces, edge cases, and explicit testing expectations before implementation.`
          }
        ]
      : []
  };
}
