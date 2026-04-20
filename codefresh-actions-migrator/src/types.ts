export interface CodefreshPipeline {
  sourcePath: string;
  name: string;
  version: string;
  steps: CodefreshStep[];
  variables: Record<string, unknown>;
}

export interface CodefreshStep {
  id: string;
  type: string;
  title?: string;
  image?: string;
  commands?: string[];
  environment?: Record<string, string>;
  when?: unknown;
  raw: Record<string, unknown>;
}

export interface MigrationPlan {
  pipeline: CodefreshPipeline;
  targetWorkflowPath: string;
  jobs: WorkflowJobPlan[];
  warnings: string[];
  requiredSecrets: string[];
  confidence: number;
}

export interface StepMapping {
  sourceStepId: string;
  sourceType: string;
  targetKind: string;
  confidence: number;
  yamlFragment: string;
  warnings: string[];
}

export interface KnowledgePattern {
  id: string;
  match: {
    type?: string;
    commandIncludes?: string;
  };
  actionTemplate: Record<string, unknown>;
  requiredSecrets: string[];
  notes: string;
}

export interface WorkflowJobPlan {
  id: string;
  name: string;
  runsOn: string;
  steps: GitHubActionStep[];
  mappings: StepMapping[];
  services?: Record<string, unknown>;
  container?: string;
  environment?: string;
}

export interface GitHubActionStep {
  name?: string;
  uses?: string;
  run?: string;
  with?: Record<string, unknown>;
  env?: Record<string, string>;
}

export interface GeneratedWorkflow {
  path: string;
  yaml: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}
