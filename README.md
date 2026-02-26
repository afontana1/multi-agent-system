# agentic-runtime

A modular package implementing a hybrid agentic runtime with:
- HFSM lifecycle control
- behavior trees for execution and repair
- event-sourced blackboard with typed patches
- async expert agents
- utility-based routing
- pluggable retry/backoff
- chat-history-aware context compilation

## Quick start

```python
import asyncio
from agentic_runtime.example import run_example

asyncio.run(run_example())
```
