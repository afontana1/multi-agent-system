# Docs

Project documentation lives here.

Current architecture notes:

- agents can be provided as config/specs or as concrete instances
- `BaseLLMAgent` delegates memory, context building, tool execution, and finalization to policy objects
- planning and routing are also policy-driven
- an optional `CoordinatorAgent` can replan across multiple rounds using structured agent capability metadata and blackboard task status

Core narrative documentation:

- `system_overview.md`: full explanation of architecture, design, usage, and runtime behavior
- `developer_guide.md`: formal guide for extending agents, policies, coordinator logic, and tools

Files:

- `docs.md`: existing written notes moved from the repository root
- `system_overview.md`: architecture and usage guide for the runtime
- `developer_guide.md`: extension and implementation guide for developers
- `diagrams/high_level_sequence.md`: high-level request-to-response flow
- `diagrams/detailed_sequence.md`: more detailed runtime/tool/MCP sequence
- `diagrams/class_diagram.md`: main class relationships in the runtime
- `diagrams/component_diagram.md`: runtime components and external integrations
- `diagrams/composite_structure_diagram.md`: internal structural composition of the system
- `diagrams/object_diagram.md`: example runtime instance snapshot
- `diagrams/package_diagram.md`: package/module dependency view
- `diagrams/profile_diagram.md`: project-specific UML stereotypes
- `diagrams/activity_diagram.md`: request-processing workflow
- `diagrams/communication_diagram.md`: message-oriented collaboration view
- `diagrams/interaction_diagram.md`: simplified interaction overview
- `diagrams/state_diagram.md`: runtime lifecycle states
- `diagrams/timing_diagram.md`: coarse timing of request execution
