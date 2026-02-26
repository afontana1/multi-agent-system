# Background: Why were old Game Dev AI so realistic?

What made those old games feel “smart” wasn’t one magic AI algorithm — it was a **stack of simple systems** working together, plus really good encounter design.

Halo is a classic example: Bungie explicitly described the problem as managing AI complexity and used a **hierarchical finite state machine / behavior tree–style graph** (they even call it a behavior DAG), with lots of attention to scalability, memory/knowledge, and tools for level designers.

## The core ingredients behind “realistic” NPCs

### 1) Decision-making hierarchies (FSMs / HFSMs / Behavior Trees)

Old shooters often used:

* **FSMs** (idle, patrol, combat, retreat, search)
* **Hierarchical FSMs** (combat contains sub-states like flank, suppress, reload, take cover)
* **Behavior Trees** (modular “if/then” behavior blocks)

Why this works:

* It’s **fast** enough for real-time gameplay
* It’s **authorable** (designers can reason about it)
* It keeps behavior **modular** instead of spaghetti code

A big reason behavior trees became popular is exactly that plain FSMs become hard to extend as complexity grows. The BT survey calls this out directly.

---

### 2) A “combat loop” instead of true intelligence

NPCs usually aren’t “thinking” like humans. They’re cycling through a loop like:

1. **Perceive** (see/hear player? teammate down? grenade nearby?)
2. **Update memory** (last known player position, threat level, cover spots)
3. **Choose behavior** (attack / flank / search / retreat)
4. **Move + animate + shoot**
5. **Re-evaluate**

Halo’s writeup talks about this in terms of **decision-making, memory/knowledge models, and scalable control structures**.

That loop creates the illusion of tactical thinking.

---

### 3) Navigation + pathfinding (navmeshes + A*)

To move believably, NPCs need to know **where they can go** and **how to get there**:

* **Navmesh** = the walkable world represented as connected convex polygons
* **A*** = the pathfinding algorithm that finds an efficient route through that graph

Navmeshes are especially important because they simplify 3D movement into a cleaner graph problem; pathfinding can then use A* (or variants). ([Wikipedia][3])

This is why enemies can:

* route around obstacles
* take sensible paths
* not get stuck constantly

---

### 4) Tactical scoring (cover, line of sight, distance, danger)

A lot of “smartness” is just **scoring options**:

* Which cover is closest?
* Which position has line of sight?
* Am I too exposed?
* Is the player too close for this weapon?
* Is a grenade threat active?

Even in older games, many decisions are effectively:

> “Pick the highest-scoring behavior/position right now.”

Halo’s article mentions child behaviors competing by **relevancy/desire-to-run**, which is basically an early/explicit version of this scoring idea.

---

### 5) Perception and memory are more important than “IQ”

Realistic behavior comes from NPCs seeming to **know things**:

* “I saw the player go behind that crate”
* “I heard gunfire from the left”
* “My squadmate is dead”
* “I lost line of sight, now I search”

Games usually maintain a lightweight **world state / blackboard / knowledge model** for each actor (or squad). Halo specifically discusses knowledge representation as a core part of their AI architecture.

---

### 6) Squad coordination (the secret sauce)

The best old campaign AI feels smart because enemies don’t all do the same thing.

Common patterns:

* **Role assignment** (one suppresses, one flanks, one advances)
* **Shared targets** / shared threat info
* **Local rules** (“don’t all use the same cover node”)
* **Barks** (“He’s over there!”) to make coordination visible to the player

This is less about deep AI and more about **controlled coordination + presentation**.

---

### 7) Animation, audio, and timing sell the illusion

A huge part of “realistic” is not logic — it’s **readability**:

* enemies lean before shooting
* they pause/react after a grenade lands
* voice lines communicate state (“Reloading!”, “Flank him!”)
* slight delays make them feel human rather than robotic

So the AI system is often designed around **behavior legibility**, not raw optimality.

---

## Software patterns these games relied on

### Data-driven AI

A lot of old AAA games exposed behavior through:

* script files
* tag systems / data tables
* level editor markers
* per-encounter tuning

For Battlefront-era games, you can see this in the mod tools: Pandemic exposed a lot via **Lua scripting**, mission scripts, object definition files, and their proprietary level editor (“ZeroEditor”). The mod tools docs list Lua commands/callbacks, mission script breakdowns, ODF docs, spline-following for AI flyers, etc.

That tells you the architecture was heavily **designer-facing and data-driven**, not hardcoded all in C++.

---

### Separation of concerns

Good game AI is usually split into systems:

* **Decision** (what to do)
* **Navigation** (where to go)
* **Steering** (how to move frame-to-frame)
* **Animation** (how it looks)
* **Combat logic** (when/how to fire)
* **Scripting/encounters** (story beats, spawn timing)

This modularity is exactly why those games could scale to many enemy types and scenarios.

---

### “Hackability” (yes, really)

Bungie literally calls out a principle like this: hacks will happen, so build a system that can contain them. That’s very game-dev-realistic.

Why it matters:

* shipping games need exceptions
* bosses, scripted setpieces, and edge cases break pure architectures
* the trick is to make hacks **visible and controlled**, not random

---

## Design principles that make the AI feel realistic (even if it isn’t)

### 1) Believability > optimal play

NPCs should feel:

* cautious when wounded
* aggressive when confident
* surprised when flanked

They do **not** need perfect aim/pathing.

---

### 2) Bounded intelligence

Games intentionally limit AI:

* reaction delays
* imperfect perception cones
* cooldowns on grenade throws
* “commitment” times before changing behavior

These limits make NPCs feel fair and human.

---

### 3) Designer control beats pure simulation

The most memorable campaign moments are often heavily guided:

* where enemies spawn
* what weapons they carry
* how far they advance
* when allies push
* scripted fallback points

That’s not “cheating” — it’s good game direction.

---

### 4) CPU budgeting and LOD for AI

On older hardware, AI had tiny CPU budgets. So teams used:

* lower update rates for distant NPCs
* simplified thinking off-screen
* cheap heuristics over expensive planning
* precomputed navigation

This is a huge reason hierarchical, modular approaches won.

---

## Halo vs. Battlefront feel 

### Halo (campaign)

Feels smart because of:

* strong behavior hierarchy
* robust combat state switching
* clear perception/search behavior
* polished presentation (barks, reactions, animation)
* lots of iteration on “30 seconds of fun” style combat moments (Bungie literally framed it this way in their AI retrospective material)

### Battlefront (classic)

Feels alive because of:

* many agents moving through shared objectives
* strong mission scripting and mode logic
* pathing/flow through command posts and lanes
* vehicle + infantry + map scripting interactions
* data-driven mission setup (Lua/ODF/editor tooling) rather than one deep per-soldier brain

So Halo’s “realism” is often **micro-tactical enemy behavior**, while Battlefront’s is more **macro-battlefield chaos + objective flow**.

---

## Mental model

Think of campaign NPC AI as:

**Perception + Memory + Behavior Hierarchy + Pathfinding + Tactical Scoring + Animation/Audio polish + Encounter scripting**

That combination is what creates the realism.


# Hierarchical State Machines

**Hierarchical FSMs (HFSMs)** are basically a smarter, more scalable version of regular state machines.

## Quick recap: regular FSM

A normal finite state machine is:

* **States**: Idle, Patrol, Attack, Reload
* **Transitions**: rules for switching states
  (e.g. “if player visible → Attack”)

This works great at first, but gets messy fast.

### The problem with plain FSMs

As behaviors grow, you get:

* too many states
* too many transitions
* repeated logic everywhere

Example:

* `AttackWithRifle`
* `AttackWithPistol`
* `AttackWhileInCover`
* `AttackWhileFlanking`
* `AttackLowHealth`

Now every one of those needs transitions to:

* Reload
* Retreat
* Search
* Dead
* Stunned

That turns into a spaghetti graph.

---

## What “hierarchical” means

An HFSM lets states contain **substates**.

So instead of one giant flat list, you group behavior into layers.

### Example structure

* **Alive** (top-level)

  * **Passive**

    * Idle
    * Patrol
    * Investigate
  * **Combat**

    * AcquireTarget
    * Attack
    * TakeCover
    * Flank
    * Reload
  * **Flee**

    * RunToSafeSpot
    * Recover
* **Dead**

Now your NPC can be in:

* `Alive > Combat > TakeCover`

That’s much cleaner than one giant flat state list.

---

## Why HFSMs feel so good in games

### 1) Shared logic lives higher up

If you put logic in `Combat`, all combat substates inherit it.

For example, while in any combat substate:

* keep facing threat
* update last known player position
* allow grenade reaction
* check health

You don’t repeat this in `Attack`, `Flank`, `TakeCover`, etc.

---

### 2) Easier transitions

Instead of wiring every substate to every other substate, you can transition at the parent level.

Example:

* Any substate under `Alive` can transition to `Dead`
* Any substate under `Combat` can transition to `Flee` if morale breaks

That cuts a ton of complexity.

---

### 3) Better designer thinking

Designers naturally think in layers:

* “Is this unit in combat or not?”
* “If in combat, is it attacking or repositioning?”
* “If attacking, is it burst-firing or suppressing?”

HFSMs match that mental model.

---

## A practical NPC example (shooter enemy)

### Top-level states

* `Spawn`
* `Alive`
* `Dead`

### Inside `Alive`

* `Passive`
* `Alert`
* `Combat`
* `Retreat`

### Inside `Combat`

* `ChooseAction`
* `Attack`
* `TakeCover`
* `Flank`
* `Reload`
* `SearchLastKnownPosition`

### How it plays out

1. NPC starts in `Alive > Passive > Patrol`
2. Hears gunfire → transitions to `Alive > Alert`
3. Sees player → enters `Alive > Combat > ChooseAction`
4. Picks `TakeCover`
5. From cover, switches to `Attack`
6. Loses sight of player → `SearchLastKnownPosition`
7. Low health + alone → `Retreat`
8. Dies anytime → `Dead` (top-level transition)

That’s the “realistic behavior” illusion.

---

## Key HFSM concepts

### Entry / Update / Exit

Each state usually has:

* **Enter**: run once when state starts
  (play bark, choose destination)
* **Update**: run every tick
  (check line of sight, fire, move)
* **Exit**: cleanup when leaving
  (stop animation, clear timers)

Because of hierarchy, parent and child can both run these.

Example:

* `Combat.Update()` handles threat tracking
* `TakeCover.Update()` handles moving to cover

---

### Parent fallback behavior

If a child state doesn’t handle something, the parent can.

Example:

* `Flank` doesn’t know what to do when grenade lands
* parent `Combat` catches grenade event and forces `EvadeGrenade`

This is one of the biggest reasons HFSMs scale well.

---

### Event-driven vs polling

HFSMs can switch states by:

* **Polling** (every frame check conditions)
* **Events** (OnSeeEnemy, OnDamageTaken, OnGrenadeNearby)

Most games use a mix:

* events for immediate reactions
* polling for ongoing decisions

---

## Common patterns used with HFSMs

### 1) Blackboard (shared memory)

A little data store the states read/write:

* current target
* last known player position
* cover point
* fear/morale
* squad role

HFSM = *decision structure*
Blackboard = *memory*

These two together are super common.

---

### 2) Timers and cooldowns

Without timers, AI looks twitchy.

Examples:

* commit to cover for at least 1.2s
* don’t throw grenades more than once every 8s
* re-check flank option every 2s

This gives behavior rhythm.

---

### 3) Utility scoring inside a state

A nice hybrid pattern is:

* HFSM decides broad mode (`Combat`)
* utility scores decide exact action (`Attack` vs `Flank` vs `TakeCover`)

So you get structure + flexibility.

---

## Why old games used HFSMs a lot

HFSMs are great for old (and modern) games because they are:

* **Fast** (cheap CPU)
* **Predictable** (important for debugging)
* **Authorable** (designers can tune them)
* **Readable** (you can visualize state transitions)
* **Controllable** (easy to script around)

That’s perfect for campaign shooters where “believable and fun” matters more than perfect AI.

---

## Weaknesses of HFSMs (and why BTs became popular)

HFSMs can still get messy if:

* you have too many cross-state transitions
* lots of exceptions (“except in this case…”)
* reusable behavior chunks are hard to share cleanly

Behavior Trees often handle modular reuse better.

But HFSMs are still excellent, especially when:

* the game has clear modes (patrol/alert/combat/flee)
* you want tight control
* the team needs strong debugging visibility

---

## Tiny pseudocode example

```cpp
State Alive {
  onUpdate() {
    if (health <= 0) transition(Dead);
  }

  State Combat {
    onEnter() { blackboard.inCombat = true; }

    onUpdate() {
      updateThreatMemory();
      if (moraleBroken()) transition(Alive.Retreat);
    }

    State TakeCover {
      onEnter() { coverPos = findBestCover(); moveTo(coverPos); }

      onUpdate() {
        if (grenadeNearby()) transition(Alive.Combat.EvadeGrenade);
        else if (atCover()) transition(Alive.Combat.Attack);
      }
    }

    State Attack {
      onUpdate() {
        if (!canSeeTarget()) transition(Alive.Combat.Search);
        else if (ammo == 0) transition(Alive.Combat.Reload);
        else fireBurst();
      }
    }
  }
}
```

That’s the essence: **broad state at the top, detailed behavior below**.


# Behavior Trees

Behavior Trees (BTs) are the next step in the same evolution: they solve the “FSM spaghetti” problem by making behavior **modular, composable, and easier to reuse**.

They didn’t fully replace HFSMs everywhere — a lot of games still use HFSMs, or hybrids — but BTs became very popular because they scale better for large AI behavior sets.

## The core idea

Instead of a graph of states and transitions, a BT is a **tree of decisions** that gets “ticked” (evaluated) repeatedly.

Each node returns one of 3 results:

* **Success**
* **Failure**
* **Running** (still doing this)

That “Running” result is the key trick that makes BTs great for real-time behavior.

---

## Why BTs became popular

HFSMs are good, but they tend to break down when:

* many states need the same sub-behavior
* transitions explode across modes
* exceptions pile up (“do X unless Y unless Z”)
* designers want reusable behavior chunks

BTs fix this by letting you build behavior out of **small reusable nodes**.

### What BTs corrected for vs HFSMs

### 1) Reuse

In HFSMs, “MoveToCover” logic often gets duplicated in multiple states.

In BTs, `MoveTo(CoverPoint)` can be one reusable action node used anywhere.

---

### 2) Fewer explicit transitions

HFSMs require lots of hand-authored transitions (`Attack -> Reload`, `Attack -> Search`, etc.).

BTs don’t usually require explicit edges for every switch. Instead, the tree is re-evaluated each tick, and the highest-priority valid branch runs.

That removes a ton of transition wiring.

---

### 3) Better modularity

You can package subtrees like:

* `Combat`
* `Search`
* `GrenadeReaction`
* `VehicleBehavior`

…and reuse them across enemy types.

This is huge for large games.

---

### 4) Clear priority behavior

BTs naturally express “interrupts” and priorities:

* If dead → die
* Else if grenade nearby → dive away
* Else if see enemy → fight
* Else patrol

That priority ordering is built into tree structure (top-to-bottom).

In an HFSM, this often becomes many cross-state transitions.

---

## Basic BT structure

There are a few core node types.

## 1) Composite nodes (control flow)

### Selector (Fallback)

Tries children in order until one **succeeds** or **runs**.

Use it for “pick the first thing that works.”

Example:

* `HandleDeath`
* `HandleGrenade`
* `Combat`
* `Patrol`

If `HandleDeath` fails (not dead), it tries the next.

---

### Sequence

Runs children in order. If one fails, the sequence fails. If all succeed, it succeeds. If one is still running, sequence returns running.

Use it for “do these steps in order.”

Example:

1. Find cover
2. Move to cover
3. Face enemy
4. Fire burst

---

## 2) Leaf nodes (actual logic)

### Condition nodes

Checks something:

* `CanSeeEnemy?`
* `AmmoEmpty?`
* `IsHealthLow?`

Returns success/failure.

---

### Action nodes

Does something:

* `MoveTo(target)`
* `FireBurst()`
* `Reload()`

Usually returns:

* `Running` while in progress
* `Success` when done
* `Failure` if impossible

---

## 3) Decorators (modifiers)

These wrap one child and alter behavior.

Common decorators:

* **Inverter** (success ↔ failure)
* **Repeat** (loop child)
* **Cooldown** (don’t allow child too often)
* **Succeeder** (always return success)
* **Timeout** (fail if too long)

Decorators are one reason BTs are so flexible.

---

## Example shooter enemy BT (simplified)

```text
Selector (root)
├── Sequence: Dead
│   ├── Condition: IsDead
│   └── Action: PlayDeath
├── Sequence: EvadeGrenade
│   ├── Condition: GrenadeNearby
│   └── Action: DiveToSafety
├── Sequence: Combat
│   ├── Condition: CanSeeEnemy
│   └── Selector
│       ├── Sequence
│       │   ├── Condition: AmmoEmpty
│       │   └── Action: Reload
│       ├── Sequence
│       │   ├── Condition: NeedsCover
│       │   └── Action: MoveToCover
│       └── Action: FireBurst
├── Sequence: Search
│   ├── Condition: HasLastKnownEnemyPos
│   └── Action: SearchArea
└── Action: Patrol
```

This is very readable:

* urgent things first
* combat if possible
* search if target lost
* patrol otherwise

---

## The “tick” model (how BTs run every frame/tick)

A BT is usually evaluated repeatedly (e.g. every AI update tick):

1. Start at root
2. Traverse according to selector/sequence rules
3. Run one or more leaf actions
4. Return `Success/Failure/Running`
5. Next tick, continue

### Why `Running` matters

Without `Running`, actions would be instant. But in games:

* moving takes time
* reloading takes time
* flanking takes time

`Running` lets an action persist across ticks cleanly.

---

## BTs and memory

BTs are often paired with a **blackboard** (shared memory), just like HFSMs:

* target entity
* last known position
* chosen cover
* time since seen
* squad role

The BT reads/writes blackboard values, but the blackboard itself is separate.

So:

* **BT = decision/control logic**
* **Blackboard = data/memory**

---

## Why BTs feel “smart”

Because they make it easy to combine:

* **priority** (selectors)
* **multi-step behavior** (sequences)
* **reactivity** (re-ticking every frame)
* **stateful actions** (`Running`)
* **memory** (blackboard)

That produces believable behavior without “real intelligence.”

---

## Important nuance: BTs didn’t make AI more intelligent

They mostly made AI **easier to build and maintain**.

That’s the real win:

* faster iteration
* fewer bugs
* easier debugging
* more reuse across enemies

Which leads to better-feeling AI because teams can tune more.

---

## BTs vs HFSMs in structure

### HFSM mindset

“Which state am I in, and what transitions are allowed?”

### BT mindset

“What’s the highest-priority thing I can do right now, and what steps does it require?”

Both work. BTs just tend to be easier to scale.

---

## Common BT issues (they’re not magic)

BTs solve a lot, but they introduce new problems too.

### 1) Too much re-evaluation

Because trees tick constantly, expensive checks can hurt performance.

Fix:

* tick at lower AI rates (e.g. 5–20 Hz)
* cache results in blackboard
* use event-driven updates for some conditions

---

### 2) “Priority thrashing”

An NPC may keep switching because the root selector re-picks a different branch every tick.

Example:

* briefly sees enemy → Combat
* loses LOS for 1 frame → Search
* sees enemy again → Combat

Fix:

* cooldown decorators
* commitment timers
* hysteresis (stickiness)
* “latched” decisions in blackboard

---

### 3) Hidden state in actions

If action nodes store lots of internal state, debugging gets tricky.

Fix:

* keep action nodes small
* store meaningful state in blackboard
* expose debug visualization

---

### 4) Giant unreadable trees

BTs can also become spaghetti if poorly managed.

Fix:

* subtree reuse
* naming conventions
* layered trees (high-level mode tree + lower-level action trees)
* tooling/visual editors

---

## Why many games use hybrids (HFSM + BT)

This is super common.

Example:

* **HFSM** for broad mode: `Passive / Alert / Combat / Scripted`
* **BT** inside `Combat` for tactical decisions

Why hybrid works:

* HFSM gives strong top-level control
* BT gives flexible behavior composition

So BTs didn’t “kill” HFSMs — they often **complemented** them.

---

## Design principles behind good BTs

### 1) Put urgent reactions high in the tree

Death, stun, grenade, scripted interrupts first.

---

### 2) Keep leaf nodes dumb and reusable

Good leafs:

* `MoveTo`
* `Reload`
* `FireBurst`
* `PickCover`

Bad leafs:

* `DoEntireCombatBehaviorForElite`

---

### 3) Use blackboard for coordination

Don’t make the tree compute everything every tick.
Store:

* selected target
* assigned flank side
* squad suppression role

---

### 4) Add commitment and timing

Pure BTs can feel twitchy.
Use:

* cooldown decorators
* min-duration decorators
* action commitments

---

### 5) Make behavior legible, not optimal

Same as HFSMs:

* readable timing
* obvious reactions
* clear animation/audio sync

Believability beats perfect tactics.

---

## Tiny pseudocode version (BT semantics)

```cpp
Status RootTick() {
  if (IsDead()) return PlayDeath();

  if (GrenadeNearby())
    return DiveToSafety();   // Running until safe

  if (CanSeeEnemy()) {
    if (AmmoEmpty()) return Reload();
    if (NeedsCover()) return MoveToCover();
    return FireBurst();
  }

  if (HasLastKnownEnemyPos())
    return SearchArea();

  return Patrol();
}
```

That’s not a full BT implementation, but it captures the BT style:
**ordered priorities + stepwise actions + repeated ticking**.

Behavior Trees became popular because they made game AI behavior **more modular, reusable, and maintainable** than large HFSMs, while preserving the fast, deterministic-ish, real-time behavior needed for games.

# Instructions: Applying to Agentic AI

---

## Current Brittleness

Your current design is likely brittle because it’s doing too much in one pass:

* **Orchestrator** decides routing up front
* Sub-agents run
* **Synthesizer** merges outputs

That works for simple cases, but breaks when reality gets messy:

* a sub-agent fails or returns partial info
* new evidence changes what should happen next
* one sub-agent’s output implies another should run
* conflicting outputs need adjudication
* “urgent” behaviors (safety, validation, clarification) should interrupt normal flow

That’s exactly the same reason game AI moved beyond flat FSMs.

---

## The game AI translation to agent systems

Here’s the direct mapping:

### Game AI → Agentic AI

* **NPC** → your agent system
* **Perception** → input parsing / tool outputs / environment signals
* **Blackboard (memory)** → shared working state / task state / evidence store
* **HFSM / BT** → orchestration policy / control flow
* **Action nodes** → sub-agent calls / tool calls
* **Tick loop** → iterative planning + re-evaluation loop
* **Animation/audio polish** → response formatting + explanations + confidence signaling

This is the key shift:

> Don’t treat orchestration as a one-shot router.
> Treat it as a **reactive control system** with memory.

---

## The biggest upgrade: move from “pipeline” to “control loop”

Your current architecture is a pipeline:

**Request → Route → Execute → Synthesize**

More robust architecture (game AI style):

**Observe → Update blackboard → Choose next action → Execute → Update blackboard → Repeat until done**

That one change makes the system much less brittle.

---

## What to borrow from HFSMs

HFSMs are great for **high-level modes** in agent systems.

### Use HFSM for top-level modes

Example:

* `Intake`
* `Plan`
* `Execute`
* `Validate`
* `Repair`
* `Respond`
* `Escalate` (if blocked / ambiguous / unsafe)

Then each mode can have substates.

### Example HFSM for your system

* `Active`

  * `Intake`

    * ParseRequest
    * ExtractConstraints
  * `Plan`

    * BuildTaskGraph
    * Prioritize
  * `Execute`

    * RunSubAgent
    * AwaitResults
    * RetryOrFallback
  * `Validate`

    * CheckCompleteness
    * CheckConsistency
    * CheckSafety
  * `Repair`

    * FillMissingData
    * ResolveConflicts
  * `Respond`

    * Synthesize
    * Format
* `Failed`
* `Done`

### Why this helps

HFSM gives you:

* **clear lifecycle**
* **debuggability**
* **predictable transitions**
* a place for “global” logic (timeouts, safety, retries, budget checks)

This is ideal for avoiding “random orchestration spaghetti.”

---

## What to borrow from Behavior Trees

BTs are great for **decision-making inside a mode** (especially Execute/Validate/Repair).

They help with:

* priorities
* fallback behavior
* retries
* interruption handling

### Example BT inside `Execute`

Root selector:

1. If unsafe risk → run SafetyChecker
2. If missing required info → run Clarifier / retrieval agent
3. If plan has unresolved dependencies → run dependency agent
4. If primary specialist applicable → run it
5. If primary fails → run fallback specialist
6. If enough evidence → move to Validate
7. Else → ask for clarification / partial response

That’s classic BT:

* **Selector** = fallback priority
* **Sequence** = multi-step execution
* **Decorators** = retry limits, timeouts, cooldowns

---

## The most important concept for agent systems: the blackboard

Game AI’s blackboard concept is probably the single best thing you can steal.

Right now your orchestrator is likely making decisions from raw text + local assumptions.

Instead, create a **shared blackboard** (structured task state) that all agents read/write.

## Blackboard fields (example)

* `user_goal`
* `constraints` (time, format, budget, tools)
* `subtasks`
* `dependencies`
* `evidence` (facts, citations, tool outputs)
* `open_questions`
* `conflicts`
* `confidence_by_claim`
* `completion_status`
* `failure_reasons`
* `retry_counts`
* `safety_flags`

Then:

* orchestrator/HFSM/BT reads blackboard
* sub-agents append evidence/results
* validator sets flags
* synthesizer reads structured state, not raw blobs

This removes a lot of brittleness because decisions become **state-based**, not “whatever the last agent said.”

---

## Why your current synthesizer may be a hidden failure point

In many agent systems, the synthesizer becomes a “magic glue” step that tries to fix everything at the end.

That’s brittle because synthesis is being asked to:

* merge conflicting outputs
* infer missing facts
* repair plan mistakes
* decide what’s trustworthy

That should mostly happen **before synthesis**, in a `Validate/Repair` loop.

### Better role for synthesizer

Make it mostly:

* formatting
* compression
* explanation
* user-facing organization

Not truth arbitration.

Truth arbitration belongs in **validation nodes**.

---

## A practical hybrid architecture (HFSM + BT + blackboard)

This is the pattern I’d recommend:

## 1) HFSM for lifecycle control

Top-level states:

* `Intake`
* `Plan`
* `Execute`
* `Validate`
* `Repair`
* `Respond`
* `Done/Fail`

This keeps the system stable and debuggable.

## 2) BTs inside `Execute` and `Repair`

Use BTs for dynamic decisions like:

* choose specialist
* retry/fallback
* fill missing fields
* resolve conflicts
* request clarification

This avoids hardcoding giant transition graphs.

## 3) Blackboard as source of truth

All agents write structured outputs to a shared state.
No direct agent-to-agent hidden coupling.

---

## Design principles from games that will make your system less brittle

### 1) Priority-first handling

Put urgent/critical checks first, always:

* safety/policy
* missing required inputs
* tool failure
* contradiction detection
* hallucination risk

Game equivalent: death/grenade interrupts.

---

### 2) Bounded commitment

Don’t re-plan every step; don’t commit forever.

Use “commitment windows”:

* commit to a chosen sub-agent for N steps / until completion / timeout
* then re-evaluate

This prevents thrashing (“call A, no B, no A, no B…”).

---

### 3) Deterministic arbitration rules

If two sub-agents disagree, define deterministic rules:

* source priority (official docs > web summary > model inference)
* recency preference
* confidence thresholds
* validator tie-breakers

This is the equivalent of explicit transition priority in HFSMs.

---

### 4) Data-driven routing, not hardcoded routing

Don’t encode routing in giant if/else blocks.

Instead define:

* capabilities
* preconditions
* costs
* expected outputs
* failure modes

Then pick sub-agents by scoring.

That’s game-style utility scoring.

---

### 5) Separate “decision” from “action”

A common brittleness source is sub-agents doing planning *and* execution *and* synthesis.

Split it:

* control layer decides what to do
* sub-agent executes one role
* validator checks
* synthesizer presents

This is the same separation as decision/nav/animation in games.

---

### 6) Build for partial success

Game AI always degrades gracefully (fallback anims, simpler pathing, etc.).

Your agent system should too:

* produce partial answer with clear gaps
* mark unresolved claims
* ask targeted follow-up only when necessary
* provide best-effort output instead of hard fail

---

## Concrete BT-style control logic for an agent system

Here’s a simple mental model:

### Root Selector

1. **Safety branch**

   * If unsafe/high-risk → policy handling
2. **Completion branch**

   * If answer complete + validated → synthesize/respond
3. **Repair branch**

   * If conflicts/missing pieces → repair subtree
4. **Execution branch**

   * Run next planned sub-agent
5. **Clarification branch**

   * Ask user only if blocked
6. **Fallback response**

   * Return best effort + caveats

This is dramatically less brittle than a fixed pipeline because it can **react**.

---

## Add “utility scoring” for sub-agent selection

This is where game AI really shines.

Instead of “if keyword X then call agent Y,” score candidate sub-agents:

### Score dimensions

* relevance to task
* required inputs available?
* estimated cost/latency
* confidence from past success
* novelty (does it add new evidence?)
* overlap/redundancy penalty

Pick the top one (or top few) and write the choice + rationale to the blackboard.

This makes your system:

* more adaptive
* easier to debug
* easier to extend with new agents

---

## Add a squad model

Game squads coordinate through shared roles. Your sub-agents should too.

Instead of letting all agents act independently, assign roles:

* `Retriever`
* `Reasoner`
* `Verifier`
* `Formatter`
* `Critic`

And enforce role contracts:

* Retriever cannot synthesize final claims
* Verifier cannot introduce new unsupported claims
* Formatter cannot change factual content

This prevents “everyone does everything” drift.

---

## A minimal implementation shape

If you want something practical, build these pieces first:

### 1) Blackboard schema

JSON/object schema for task state.

### 2) Tick loop

A loop that:

* reads blackboard
* selects next node (BT/HFSM)
* executes one action
* writes results
* repeats until terminal

### 3) Node interface

Every node returns:

* `SUCCESS`
* `FAILURE`
* `RUNNING`

And writes structured updates to blackboard.

### 4) Validation layer

A dedicated validator/critic step that can set:

* `missing_fields`
* `conflicts`
* `unsupported_claims`

### 5) Deterministic priorities

Explicit ordering for:

* interrupts
* retries
* fallbacks
* finalization

---

## Where people go wrong (agent systems version of FSM spaghetti)

* Orchestrator holds too much hidden state
* Agents return freeform text instead of structured outputs
* No shared blackboard
* No validator/repair loop
* Replanning every step (thrash)
* No transition priorities
* Synthesizer forced to “clean up” all upstream errors

If any of that sounds familiar, you’re not off track — you’re just at the same point game AI teams were before they introduced better control structures.

---

## Recommended architecture

If I had to suggest one next step:

### Keep your current components, but wrap them in a hybrid controller

* **HFSM** for lifecycle (`Intake/Plan/Execute/Validate/Repair/Respond`)
* **BT** for decisions inside `Execute` and `Repair`
* **Blackboard** for shared state/evidence
* **Utility scoring** for sub-agent selection
* **Validator** as a first-class subsystem (not part of synthesizer)

That gives you:

* structure (HFSM)
* flexibility (BT)
* robustness (validation/repair loop)
* extensibility (data-driven agent registry)

## Integrating Chat History

Perfect place to add it — and it’s a **big upgrade** if you treat chat history as **memory + evidence**, not just extra prompt text.

Right now it sounds like you pass:

* current user question
* full chat history

…into the orchestrator. That works, but it’s brittle because the history is probably being used as an unstructured blob.

## The key shift

Don’t treat chat history as “context text.”

Treat it as **an input stream that gets parsed into the blackboard**.

So instead of:

**[question + history] → orchestrator**

You want:

**[question + history] → memory/perception layer → blackboard → controller (HFSM/BT)**

---

## Why this matters

Raw chat history causes common failure modes:

* important constraints get buried
* old info overrides newer corrections
* the system forgets what was already done
* agents repeat work
* “synthesizer” has to rediscover facts from text

Games solved a similar problem by separating:

* **world observations** from
* **working memory** from
* **decision logic**

---

# How to integrate chat history cleanly

## 1) Split chat history into memory types

Not all history is equal. Put it into buckets.

### A) Stable user preferences / standing constraints

Stuff that persists across turns:

* desired output style
* domain preferences
* “always include citations”
* budget/latency preferences
* coding language preference

This is like **long-lived memory**.

### B) Task state / progress

What has already happened in this task:

* subtasks completed
* tools already called
* failed attempts
* known blockers
* open questions

This is like the **mission state** in a game.

### C) Evidence / facts discovered

Structured facts from prior turns or tools:

* extracted claims
* citations
* computed values
* file references

This is your **blackboard evidence store**.

### D) Conversational residue (low value)

Politeness, side comments, exploration branches that are no longer relevant.

This should usually **not** drive orchestration decisions.

---

## 2) Add a “Context Compiler” step before orchestration

This is the missing layer in many agent systems.

### Context Compiler responsibilities

Given `{current_question, chat_history}`, produce a structured object:

* `current_intent`
* `active_task`
* `constraints`
* `assumptions`
* `known_facts`
* `open_issues`
* `completed_steps`
* `candidate_next_steps`
* `history_summary` (compressed)
* `conflicts_in_history`
* `recency_ordered_corrections`

Think of it like turning messy dialogue into a **game AI blackboard**.

---

## 3) Use recency + authority rules for conflicting history

Chat history often contains contradictions:

* user changes requirements
* earlier agent output was wrong
* later tool output corrects earlier inference

You need explicit arbitration rules.

### Example rules

1. **User corrections override prior agent assumptions**
2. **Tool/factual evidence overrides agent freeform text**
3. **Most recent explicit constraint wins**
4. **Deprecated plans remain logged but inactive**
5. **Conflicts get flagged, not silently merged**

This is just like deterministic transition priority in HFSMs.

---

## 4) Store “what happened” as events, not just messages

Instead of only keeping raw text turns, create an **event log** alongside chat history.

### Event examples

* `USER_CONSTRAINT_ADDED`
* `TASK_PLANNED`
* `SUBAGENT_CALLED`
* `TOOL_RESULT_RECEIVED`
* `VALIDATION_FAILED`
* `CONFLICT_DETECTED`
* `ANSWER_DRAFTED`
* `USER_CORRECTION`

Each event can include structured payloads.

This is huge because your controller can reason over:

* **events** (structured, machine-usable)
  instead of
* raw text (messy, ambiguous)

---

## 5) Maintain layered memory, not one giant history blob

A good pattern is:

## Memory layers

### Layer 1: Working memory (short horizon)

Current task state, active subtasks, open issues
(used every tick)

### Layer 2: Episodic memory (task history)

Past steps, failures, retries, decisions
(used for debugging / replanning)

### Layer 3: Semantic memory (stable facts/preferences)

User preferences, standing constraints, project facts
(used across turns/tasks)

This maps almost directly to:

* blackboard
* event log
* persistent profile

---

## 6) Track provenance for everything from history

This is critical.

Every fact/constraint in the blackboard should carry:

* `source` (user turn, agent, tool)
* `timestamp/turn`
* `confidence`
* `status` (`active`, `superseded`, `uncertain`)

Example:

```json
{
  "constraint": "Use Python output",
  "source": "user_turn_12",
  "confidence": 1.0,
  "status": "active"
}
```

Why this helps:

* easier conflict resolution
* easier debugging
* safer synthesis
* agents can prefer higher-authority facts

Game analogy: “knowledge model” with certainty + recency.

---

## 7) Don’t pass full history to every sub-agent

This is a major brittleness source.

Instead, pass each sub-agent a **task-specific view** of memory:

* relevant task goal
* relevant constraints
* relevant evidence
* only the needed history snippets
* explicit output schema

This is like giving an NPC only the sensory/blackboard info it needs, not the entire world simulation dump.

### Example

Retriever agent gets:

* search objective
* keywords
* current evidence gaps
* prior failed queries

Verifier agent gets:

* claims to verify
* evidence store
* source ranking policy

Formatter agent gets:

* validated facts
* desired format
* tone preferences

---

## 8) Add a “history summarizer” that is state-aware, not generic

Summarizing history is useful, but generic summaries lose control signals.

Instead, summarize by **blackboard fields**.

### Good history summary output

* **Current goal**
* **Constraints**
* **What’s done**
* **What failed**
* **What remains**
* **Known facts**
* **Conflicts**
* **Latest user changes**

That summary can be regenerated each tick or when token budget is tight.

---

## 9) Make history integration incremental (tick-based)

Don’t fully re-parse the entire history every turn if you can avoid it.

Use an incremental approach:

1. Process only new messages
2. Emit events
3. Update blackboard
4. Mark superseded facts/constraints
5. Recompute only affected summaries

This improves:

* speed
* consistency
* determinism

---

## 10) Detect “conversation mode” from history and feed it into control

History often tells you what kind of control behavior you need.

Examples:

* User is iterating on a draft → favor edit/transform loop
* User is debugging code → favor hypothesis/test/repair loop
* User is asking factual questions → favor retrieve/verify/synthesize
* User is brainstorming → allow looser exploration, less aggressive validation

This can become a top-level HFSM mode or a blackboard field:

* `interaction_mode = drafting | research | debugging | planning | tutoring`

That makes orchestration much less brittle.

---

## Add a Memory/Context layer in front of your orchestrator

### Pipeline

1. **Ingest**

   * current question
   * chat history
   * tool outputs (if any)

2. **Context Compiler**

   * extract task state, constraints, facts, corrections, open issues
   * update event log + blackboard

3. **Orchestrator/Controller**

   * decides next sub-agent(s) based on blackboard, not raw history

4. **Sub-agent execution**

   * each gets a scoped memory view

5. **Validator**

   * updates blackboard with completeness/conflicts

6. **Synthesizer**

   * reads validated blackboard state

---

## Minimal blackboard fields for chat-history-aware orchestration

If you want a simple version, start with these:

### `conversation`

* `current_user_request`
* `interaction_mode`
* `turn_index`

### `task`

* `goal`
* `subtasks`
* `completed_subtasks`
* `open_questions`
* `status`

### `constraints`

* list of `{key, value, source_turn, active}`

### `facts`

* list of `{claim, source, confidence, status}`

### `artifacts`

* tool outputs / docs / code snippets / references

### `execution`

* `agents_called`
* `results_by_agent`
* `retry_counts`
* `failures`

### `validation`

* `missing_items`
* `conflicts`
* `unsupported_claims`
* `ready_to_respond`

### `history_summary`

* compact structured summary for prompting sub-agents

That alone will make a big difference.

---

## Design principles for history handling (borrowed from game AI)

### 1) Memory is selective

Don’t keep everything equally “hot.”
Promote only decision-relevant info to working memory.

### 2) Recency matters, but authority matters more

Latest message isn’t always truth.
Tool results / explicit user corrections often outrank prior agent text.

### 3) Separate observation from belief

Raw chat turn = observation
Extracted structured fact/constraint = belief
Validated fact = trusted belief

This is a *huge* conceptual upgrade.

### 4) Re-evaluate from state, not from transcript

The transcript is for auditability.
The blackboard is for control.

---

Before your orchestrator runs, insert a lightweight step:

### `build_context_state(chat_history, current_question) -> blackboard_patch`

It should at minimum extract:

* latest user goal
* active constraints
* prior completed work
* unresolved issues
* explicit corrections

Even this small change will reduce brittleness a lot.