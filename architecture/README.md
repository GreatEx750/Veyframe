# Veyframe architecture diagrams

Editable SVG sources and PNG exports for the project README and submission write-up.

- `project-high-level.svg` / `.png` — customer-facing overview from brief to delivery.
- `architecture-diagram.svg` / `.png` — deployed Google Cloud services, AI boundary, media workers, and durable storage.
- `agent-workflow-diagram.svg` / `.png` — human review around Google ADK agents, typed validation, and deterministic execution.

The diagrams describe the implemented Veyframe runtime. Google ADK runs within the FastAPI service; the current deployment does not claim Agent Engine. Parallel Search is shown as a direct partner SDK integration. Model outputs cross into execution only after typed schema validation.
