---

description: "Task list for deploying the Home Sweet Home agent as a Flux-managed workload"
---

# Tasks: Agent Workload Deployment

**Input**: Design documents from `/specs/006-agent-deployment/`

**Prerequisites**: plan.md, spec.md

**Tests**: No unit tests are added; validation is `scripts/validate.sh` plus in-cluster probe
checks described in the acceptance criteria.

## Phase 1: Setup

- [X] T001 Create `apps/agent/` directory and `apps/agent/kustomization.yaml`
- [X] T002 Add `agent` to `apps/kustomization.yaml`

---

## Phase 2: Foundational Resources

- [X] T003 [P] Create `apps/agent/namespace.yaml` for the `agent` namespace
- [X] T004 [P] Create `apps/agent/configmap.yaml` with non-secret configuration and cluster DNS endpoints
- [X] T005 [P] Create `apps/agent/service.yaml` ClusterIP on port 3400

---

## Phase 3: User Story 1 and 2 - Workload and Probes (Priority: P1)

**Goal**: The agent runs as a hardened Deployment and becomes Ready with unauthenticated probes.

**Independent Test**: Reconcile and confirm the pod is Ready; request `/healthz` and `/readyz` from
another pod.

- [X] T006 [US1] Create `apps/agent/deployment.yaml` with the pinned image, ConfigMap/Secret env, probes,
      security context, node selector, resources, and termination grace period
- [X] T007 [US2] Verify the Service selects the Deployment and probes target port 3400

---

## Phase 4: User Story 3 and 4 - Endpoints and Security (Priority: P2)

**Goal**: In-cluster DNS endpoints and cluster security conventions are applied.

**Independent Test**: Inspect rendered manifests and resolve each endpoint from the agent pod.

- [X] T008 [US3] Verify ConfigMap endpoint URLs use Service DNS and the Home Assistant `/api/mcp` path
- [X] T009 [US4] Verify non-root uid/gid 1000, read-only root, dropped capabilities, no service
      account token, and requests/limits

---

## Phase 5: User Story 5 - Out-of-band Secrets (Priority: P2)

**Goal**: Credentials are referenced but never committed, and the manual creation path is documented.

**Independent Test**: Scan the repository and review the documented `kubectl create secret` commands.

- [X] T010 [US5] Wire `AGENT_AUTH_TOKENS`, `LLM_API_KEY`, and optional `HOME_ASSISTANT_MCP_TOKEN`
      through `secretKeyRef` with no committed values
- [X] T011 [US5] Document `agent-auth`, `agent-llm`, and `agent-home-assistant` creation in `docs/07`

---

## Phase 6: User Story 6 - Image Automation (Priority: P3)

**Goal**: New matching tags roll into the Deployment automatically.

**Independent Test**: Confirm the ImageRepository, ImagePolicy, and ImageUpdateAutomation match the
existing workload pattern and the setter marker is present.

- [X] T012 [US6] Create `apps/agent/image-automation.yaml` for the agent image and `./apps/agent` path
- [X] T013 [US6] Add the Flux setter marker to the Deployment image field

---

## Phase 7: User Story 7 - Documentation and Validation (Priority: P3)

**Goal**: Operators can deploy, verify, update, troubleshoot, and recover the agent; validation passes.

**Independent Test**: Run `scripts/validate.sh` and follow the new document.

- [X] T014 [US7] Create `docs/14-agent.md` with secrets, verification, image updates, troubleshooting,
      and recovery
- [X] T015 [US7] Update `docs/README.md`, `docs/09-limitations.md`, and `README.md`
- [X] T016 [US7] Run `scripts/validate.sh` and fix any findings

---

## Dependencies & Execution Order

- Phase 1 must complete before Phase 2.
- Phase 2 must complete before Phase 3.
- Phase 6 depends on Phase 3 (Deployment image field).
- Phase 7 depends on all manifest work.

## Parallel Opportunities

- T003, T004, and T005 touch different files and can be created together.
- T014 and T015 touch different documentation files and can be done together after manifests exist.

## Implementation Strategy

Deliver the manifests first, then documentation, then run validation. The workload is declarative,
so in-cluster verification follows reconciliation.
