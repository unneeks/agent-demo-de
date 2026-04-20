import { stringify } from "yaml";
import type { GeneratedWorkflow, MigrationPlan, WorkflowJobPlan } from "../types";

export function generateWorkflow(plan: MigrationPlan): GeneratedWorkflow {
  const workflow = {
    name: `Migrated ${plan.pipeline.name}`,
    on: {
      push: {
        branches: [
          "main",
          "master"
        ]
      },
      pull_request: null,
      workflow_dispatch: null
    },
    jobs: Object.fromEntries(plan.jobs.map(job => [job.id, toWorkflowJob(job)]))
  };

  return {
    path: plan.targetWorkflowPath,
    yaml: stringify(workflow, {
      nullStr: "",
      lineWidth: 0
    })
  };
}

function toWorkflowJob(job: WorkflowJobPlan): Record<string, unknown> {
  const workflowJob: Record<string, unknown> = {
    name: job.name,
    "runs-on": job.runsOn,
    steps: job.steps
  };

  if (job.container) {
    workflowJob.container = job.container;
  }
  if (job.services) {
    workflowJob.services = job.services;
  }
  if (job.environment) {
    workflowJob.environment = job.environment;
  }

  return workflowJob;
}
