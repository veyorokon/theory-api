# Agents & Cognition

Agents are just processors that may:
- subscribe to world deltas,
- choose tools (plan) and/or act,  
- optionally follow cognition graphs defining tool availability per "stage".

**No special casing**: agents use the same Transition + Predicate machinery.

## Agents as Processors

An :term:`Agent` is simply a :term:`Processor` with additional capabilities:

```yaml  
# registry/tools/agent.dialogue.yaml
id: "agent.dialogue@1"
name: "Conversational Agent"
adapter: "modal"
entry_point: "agents.dialogue_agent"
capabilities:
  - "subscribe_to_world_deltas"
  - "propose_transitions"
  - "multi_stage_cognition"
```

Unlike simple tools, agents can:

1. **React to Events** - Subscribe to world changes and decide when to act
2. **Plan Ahead** - Propose new transitions based on current state  
3. **Multi-modal** - Process text, audio, video through unified interfaces
4. **Stateful** - Maintain context across multiple interactions

## Cognition Stages

Agents can follow cognition graphs that define available tools per stage:

```{mermaid}
stateDiagram-v2
  [*] --> Observe
  Observe --> Plan: new_world_delta
  Plan --> Act: transition_ready
  Act --> Observe: action_complete
  Observe --> NoOp: no_action_needed
  NoOp --> Observe: wait
```

### Stage-based Tool Access

```yaml
# Agent cognition configuration
stages:
  observe:
    tools: ["sense.vision@1", "sense.audio@1", "memory.recall@1"]
    predicates:
      admission: []  # Always available
      
  plan: 
    tools: ["reason.chain@1", "plan.propose@1", "memory.store@1"]
    predicates:
      admission:
        - id: "cognition.stage_ready@1"
          args: {required_inputs: ["observations"]}
          
  act:
    tools: ["speech.generate@1", "vision.generate@1", "world.write@1"]
    predicates:
      admission:
        - id: "plan.exists@1"
          args: {min_confidence: 0.7}
```

### Stage Transitions

Agents move between stages based on:
- **World events** - New messages, sensor data, external triggers
- **Internal state** - Confidence levels, memory thresholds  
- **Policy** - Time limits, resource constraints

## Conversational Agents

Real-time conversational agents demonstrate the pattern:

### World Layout
```
world://acme/conversation-123/
├── streams/
│   ├── mic/audio/          # Input audio chunks
│   └── speaker/audio/      # Output audio chunks
├── artifacts/  
│   ├── messages/           # Persistent conversation history
│   └── summaries/          # Periodic conversation summaries
└── plan/
    └── transitions/
        ├── process-audio/  # Real-time audio processing
        └── generate-reply/ # Response generation
```

### Agent Flow

1. **Audio chunk arrives** → `artifact.produced` event
2. **Agent observes** → processes audio, updates internal state
3. **Agent plans** → decides whether to respond based on conversation context  
4. **Agent acts** → generates speech, writes to output stream
5. **Streams flow** → audio delivered to user via WebRTC

### Multi-Agent Coordination

Multiple agents can coordinate through the same World:

```yaml
agents:
  dialogue_agent:
    subscribes: ["streams/mic/*", "artifacts/messages/*"] 
    produces: ["streams/speaker/*"]
    
  memory_agent:  
    subscribes: ["artifacts/messages/*"]
    produces: ["artifacts/summaries/*", "artifacts/memories/*"]
    
  emotion_agent:
    subscribes: ["streams/camera/*", "streams/mic/*"]  
    produces: ["artifacts/emotional_state/*"]
```

Each agent operates independently but coordinates through shared World state and events.

## Implementation Example

```python
class DialogueAgent(BaseProcessor):
    def __init__(self):
        self.stage = "observe"
        self.context_buffer = []
        
    def process(self, context: ExpandedContext) -> ProcessorResult:
        # Stage-based processing
        if self.stage == "observe":
            return self.observe(context)
        elif self.stage == "plan":  
            return self.plan(context)
        elif self.stage == "act":
            return self.act(context)
            
    def observe(self, context: ExpandedContext) -> ProcessorResult:
        # Process new world deltas
        new_messages = self.get_new_messages(context)
        self.context_buffer.extend(new_messages)
        
        # Decide next stage
        if self.should_respond():
            self.stage = "plan"
            return ProcessorResult(
                success=True,
                next_stage="plan",
                internal_state=self.get_state()
            )
        else:
            return ProcessorResult(success=True, action="no_op")
            
    def plan(self, context: ExpandedContext) -> ProcessorResult:
        # Generate response plan
        response_plan = self.generate_response_plan(self.context_buffer)
        
        self.stage = "act" 
        return ProcessorResult(
            success=True,
            next_stage="act",
            proposed_transitions=[response_plan]
        )
        
    def act(self, context: ExpandedContext) -> ProcessorResult:
        # Execute the planned response
        audio_response = self.synthesize_speech(context.inputs["response_text"])
        
        self.stage = "observe"
        return ProcessorResult(
            success=True,
            artifacts=[
                Artifact(path="streams/speaker/audio", data=audio_response)
            ]
        )
```

This demonstrates how agents integrate seamlessly with Visureel's execution model while providing sophisticated, multi-stage behaviors.