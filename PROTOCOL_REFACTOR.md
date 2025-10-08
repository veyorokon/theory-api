# Protocol Refactor - Clean Layered Message Format

## Core Principles

1. **World Boundary Enforcement** - Django ensures all world-scoped data within `world://{bucket}/{world_id}/`
2. **Two-Layer Messages** - Control (Django) + Data (tool I/O)
3. **Django Resolves Scopes** - Container only sees presigned URLs, never touches S3 logic
4. **Symmetric I/O** - Same resolution rules for inputs (read) and outputs (write)
5. **Caller Controls Storage** - Request declares where outputs are written
6. **Container Calculates Cost** - Total cost (API + compute), Django just stores

## Message Structure

```python
{
  "kind": "Request" | "Response" | "Log" | "Event",

  "control": {
    // Django control plane metadata
  },

  "inputs": {  // Request only - hydrated data for tool
  },

  "outputs": {  // Request: where to write, Response: what was written
  }
}
```

## Scope Resolution (Django Side Only)

### Agent/Control Plane Declares Intent
```python
# Agent wants to read from world, write to world
{
  "inputs": {
    "prompt.world": "/prev-run/prompt.txt",
    "state.local": "/agent.json",
    "model": "gpt-4o-mini"
  },
  "outputs": {
    "image.world": "/generated/image.png",
    "metadata.local": "/meta.json"
  }
}
```

### Django Resolution Rules
1. **`.world` suffix** ’ Generate presigned S3 URL at `{bucket}/{world_id}/{path}`
2. **`.local` suffix** ’ Container path `/artifacts/{run_id}/{path}`
3. **Full URI** (contains `://`) ’ Use verbatim
4. **No suffix** ’ Inline value (no resolution needed)

### Django Expands to Full URLs
```python
# Django internal config (never sent to container):
world_scope = f"s3://{BUCKET}/{run.world.id}"
local_scope = f"/artifacts/{run.id}"

# Django generates presigned URLs:
{
  "inputs": {
    "prompt": "https://s3.../bucket/w1/prev-run/prompt.txt?X-Amz-...",  // GET URL
    "state": "/artifacts/r1/agent.json",                                 // Local path
    "model": "gpt-4o-mini"                                               // Inline
  },
  "outputs": {
    "image": "https://s3.../bucket/w1/generated/image.png?X-Amz-...",   // PUT URL
    "metadata": "/artifacts/r1/meta.json"                                // Local path
  }
}
```

**Container receives fully resolved URLs - no scope logic needed.**

## Message Types

### Request (Django ’ Container)

```python
{
  "kind": "Request",

  "control": {
    "run_id": "abc-123",
    "mode": "real"  // "mock" | "real"
  },

  "inputs": {
    // Fully resolved - ready to use
    "prompt": "https://s3.../presigned-get-url",  // Fetch this
    "state": "/artifacts/r1/agent.json",          // Read this
    "model": "gpt-4o-mini"                        // Use this
  },

  "outputs": {
    // Fully resolved - ready to write
    "image": "https://s3.../presigned-put-url",   // Upload here
    "metadata": "/artifacts/r1/meta.json"         // Write here
  }
}
```

### Response (Container ’ Django)

```python
{
  "kind": "Response",

  "control": {
    "run_id": "abc-123",
    "status": "success",  // "success" | "error"
    "cost_micro": 75,     // Total: API + compute (container calculates)
    "final": true         // true = terminal, false = streaming
  },

  "outputs": {
    // Confirms what was written
    "image": "https://s3.../presigned-put-url",   // Written here
    "metadata": "/artifacts/r1/meta.json",        // Written here

    // Or inline returns (no storage)
    "tokens": 150,
    "finish_reason": "stop"
  }
}
```

### Log (Container ’ Django)

```python
{
  "kind": "Log",

  "control": {
    "run_id": "abc-123"
  },

  "data": {
    "msg": "Processing frame 10",
    "level": "info",        // debug | info | warn | error
    "timestamp": 1234567890
  }
}
```

### Event (Container ’ Django)

```python
{
  "kind": "Event",

  "control": {
    "run_id": "abc-123"
  },

  "data": {
    "phase": "checkpoint",  // started | checkpoint | completed | preempted
    "progress": 0.5         // Optional: 0.0-1.0
  }
}
```

## Order of Operations

### Full Request Flow

#### 1. Agent/Control Plane Creates Request
```python
# Agent intent (uses .world/.local suffixes)
request_intent = {
  "run_id": "r1",
  "mode": "real",
  "inputs": {
    "prompt.world": "/prev-run/prompt.txt",
    "model": "gpt-4o-mini"
  },
  "outputs": {
    "image.world": "/my-images/result.png"
  }
}
```

#### 2. Django Resolves Scopes
```python
# Django knows:
# - run.world.id = "w1"
# - BUCKET = "theory-artifacts-dev"
# - run.id = "r1"

# For inputs.prompt.world:
# 1. Strip .world suffix ’ "prompt"
# 2. Get path: "/prev-run/prompt.txt"
# 3. Full S3 key: "w1/prev-run/prompt.txt"
# 4. Generate presigned GET URL

# For outputs.image.world:
# 1. Strip .world suffix ’ "image"
# 2. Get path: "/my-images/result.png"
# 3. Full S3 key: "w1/my-images/result.png"
# 4. Generate presigned PUT URL

resolved_request = {
  "kind": "Request",
  "control": {
    "run_id": "r1",
    "mode": "real"
  },
  "inputs": {
    "prompt": "https://s3.../w1/prev-run/prompt.txt?X-Amz-Signature=...",
    "model": "gpt-4o-mini"
  },
  "outputs": {
    "image": "https://s3.../w1/my-images/result.png?X-Amz-Signature=..."
  }
}
```

#### 3. Django Sends to Container (via WebSocket)
```python
ws.send_json(resolved_request)
```

#### 4. Container Receives & Hydrates Inputs
```python
# Container's runtime_common/hydration.py
def hydrate_inputs(inputs):
    result = {}
    for key, value in inputs.items():
        if value.startswith("https://"):
            # Fetch from presigned URL
            result[key] = httpx.get(value).content
        elif value.startswith("/artifacts/"):
            # Read from local filesystem
            result[key] = Path(value).read_bytes()
        else:
            # Inline value
            result[key] = value
    return result

# Tool receives:
{
  "prompt": b"Generate a cat image",  // Fetched from S3
  "model": "gpt-4o-mini"              // Inline
}
```

#### 5. Tool Executes Logic
```python
# tools/image/generate/1/protocol/handler.py
def entry(payload, emit, ctrl):
    inputs = hydrate_inputs(payload["inputs"])

    # Generate image
    image_bytes = generate_image(inputs["prompt"], inputs["model"])

    # Calculate cost
    api_cost = 100_000  # $0.10
    compute_cost = 5_000  # $0.005

    return {
        "image": image_bytes,
        "cost_micro": api_cost + compute_cost
    }
```

#### 6. Container Writes Outputs & Returns Response
```python
# runtime_common/protocol/worker.py
result = entry(payload, emit, ctrl)

# Write outputs to destinations from Request
for key, url in payload["outputs"].items():
    if key in result:
        if url.startswith("https://"):
            # Upload to presigned PUT URL
            httpx.put(url, content=result[key])
        elif url.startswith("/artifacts/"):
            # Write to local filesystem
            Path(url).write_bytes(result[key])

# Return response
response = {
    "kind": "Response",
    "control": {
        "run_id": payload["control"]["run_id"],
        "status": "success",
        "cost_micro": result["cost_micro"],
        "final": True
    },
    "outputs": payload["outputs"]  # Confirm what was written
}
ws.send_json(response)
```

#### 7. Django Receives & Stores
```python
# apps/core/adapters/base_ws_adapter.py
envelope = ws.receive_json()

# Django stores
run.status = envelope["control"]["status"]
run.cost_micro = envelope["control"]["cost_micro"]
run.ended_at = timezone.now()
run.save()

# Return to agent
return envelope
```

### Streaming Flow

#### Container sends progressive updates
```python
# Update 1
{
  "kind": "Response",
  "control": {"run_id": "r1", "final": false},
  "outputs": {"text": "Hello"}  // Inline partial result
}

# Update 2
{
  "kind": "Response",
  "control": {"run_id": "r1", "final": false},
  "outputs": {"text": "Hello world"}
}

# Final
{
  "kind": "Response",
  "control": {
    "run_id": "r1",
    "status": "success",
    "cost_micro": 25,
    "final": true
  },
  "outputs": {
    "text": "https://s3.../..."  // Written to S3
  }
}
```

## Real-World Examples

### Example 1: LLM Text Generation

**Agent Request:**
```python
{
  "run_id": "r1",
  "mode": "real",
  "inputs": {
    "messages": [{"role": "user", "content": "Hello"}],
    "model": "gpt-4o-mini"
  },
  "outputs": {
    "response.world": "/chat/session-123/response.txt"
  }
}
```

**Django Resolves:**
```python
{
  "kind": "Request",
  "control": {"run_id": "r1", "mode": "real"},
  "inputs": {
    "messages": [{"role": "user", "content": "Hello"}],
    "model": "gpt-4o-mini"
  },
  "outputs": {
    "response": "https://s3.../w1/chat/session-123/response.txt?put-signature"
  }
}
```

**Container Streams:**
```python
{"kind": "Response", "control": {"final": false}, "outputs": {"response": "Hi"}}
{"kind": "Response", "control": {"final": false}, "outputs": {"response": "Hi there"}}
{"kind": "Response",
 "control": {"status": "success", "cost_micro": 15, "final": true},
 "outputs": {"response": "https://s3.../w1/chat/session-123/response.txt?put-signature"}}
```

### Example 2: Multi-turn Agent

**Turn 1 Request:**
```python
{
  "run_id": "r1",
  "inputs": {"message": "What's the weather?"},
  "outputs": {
    "response.world": "/chat/turn1.txt",
    "state.local": "/agent-state.json"
  }
}
```

**Django Resolves:**
```python
{
  "kind": "Request",
  "control": {"run_id": "r1"},
  "inputs": {"message": "What's the weather?"},
  "outputs": {
    "response": "https://s3.../w1/chat/turn1.txt?put",
    "state": "/artifacts/r1/agent-state.json"
  }
}
```

**Turn 1 Response:**
```python
{
  "kind": "Response",
  "control": {"status": "success", "cost_micro": 10, "final": true},
  "outputs": {
    "response": "https://s3.../w1/chat/turn1.txt?put",  // Written
    "state": "/artifacts/r1/agent-state.json"            // Written
  }
}
```

**Turn 2 Request (references Turn 1 state):**
```python
{
  "run_id": "r2",
  "inputs": {
    "message": "San Francisco",
    "state.local": "/agent-state.json"  // Read from r1
  },
  "outputs": {
    "response.world": "/chat/turn2.txt",
    "state.local": "/agent-state.json"  // Write to r2
  }
}
```

**Django Resolves (cross-run reference):**
```python
{
  "kind": "Request",
  "control": {"run_id": "r2"},
  "inputs": {
    "message": "San Francisco",
    "state": "/artifacts/r1/agent-state.json"  // Read from r1's local scope
  },
  "outputs": {
    "response": "https://s3.../w1/chat/turn2.txt?put",
    "state": "/artifacts/r2/agent-state.json"  // Write to r2's local scope
  }
}
```

### Example 3: Video Generation with Progress

**Request:**
```python
{
  "run_id": "r3",
  "inputs": {
    "prompt": "A cat playing piano",
    "duration": 10
  },
  "outputs": {
    "video.world": "/videos/cat-piano.mp4"
  }
}
```

**Event Stream:**
```python
{"kind": "Event", "control": {"run_id": "r3"}, "data": {"phase": "started"}}

{"kind": "Log", "control": {"run_id": "r3"}, "data": {"msg": "Loading model"}}

{"kind": "Event", "control": {"run_id": "r3"}, "data": {"phase": "checkpoint", "progress": 0.5}}

{"kind": "Response",
 "control": {"run_id": "r3", "status": "success", "cost_micro": 200000, "final": true},
 "outputs": {"video": "https://s3.../w1/videos/cat-piano.mp4?put"}}

{"kind": "Event", "control": {"run_id": "r3"}, "data": {"phase": "completed"}}
```

## Cost Tracking

**Container calculates total cost:**
```python
# Inside handler.py
def entry(payload, emit, ctrl):
    # Execute tool logic...

    # Calculate costs (container knows all pricing)
    api_cost_micro = calculate_openai_cost(tokens, model)    # Provider pricing
    compute_cost_micro = calculate_modal_cost(duration_ms)   # Runtime pricing

    return {
        "status": "success",
        "cost_micro": api_cost_micro + compute_cost_micro,
        "outputs": {...}
    }
```

**Django stores:**
```python
run.cost_micro = envelope["control"]["cost_micro"]
run.save()
```

**Why container calculates:**
-  Container knows provider pricing (OpenAI, Replicate, etc.)
-  Container knows runtime costs (Modal, local)
-  Django agnostic to tool internals
-  Easy to update pricing without Django changes

## World Boundary Enforcement

**Django validation before resolution:**
```python
def resolve_scopes(request_intent, run):
    for key, value in request_intent["inputs"].items():
        if key.endswith(".world"):
            # Ensure within world boundary
            if not value.startswith("/"):
                raise ValueError(f"World paths must start with /: {value}")
            # OK - will resolve to s3://{bucket}/{run.world.id}/{value}

    for key, value in request_intent["outputs"].items():
        if key.endswith(".world"):
            # Ensure within world boundary
            if not value.startswith("/"):
                raise ValueError(f"World paths must start with /: {value}")
            # OK - will resolve to s3://{bucket}/{run.world.id}/{value}
```

**Container never sees world boundary - only presigned URLs scoped by Django.**

## Implementation Checklist

### Remove
- L `Token` message type ’ use `Response` with `final: false`
- L `RunResult` wrapper ’ `Response` is the result
- L `RunOpen` ’ rename to `Request`
- L `protocol` section in messages ’ Django internal only
- L Container S3 logic ’ Django generates presigned URLs

### Add
-  Two-layer messages (`control`, `inputs`/`outputs`)
-  `Request`/`Response` message types
-  Django scope resolution (`.world`/`.local` ’ full URLs)
-  Symmetric input/output handling
-  Container cost calculation
-  Cross-run references (e.g., r2 reads from r1's local scope)

### Update
- = Django: Scope resolution before sending to container
- = `runtime_common/hydration.py`: Fetch from URLs, write to URLs
- = `runtime_common/protocol/handler.py`: Return flat outputs + cost
- = Tool handlers: Calculate total cost_micro
- = Control plane: Store cost_micro directly
- = Tests: Validate scope resolution and URL generation

### Keep
-  `Log` and `Event` message types
-  WebSocket transport
-  Streaming with `final` flag
-  Presigned URL pattern
