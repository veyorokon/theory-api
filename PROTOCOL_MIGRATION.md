# Protocol Migration Plan

## Overview

Migrate from verbose multi-wrapper protocol to clean two-layer Request/Response format with Django-side scope resolution.

## Runtime Files Affected

### Critical Runtime Changes

**`code/libs/runtime_common/` - All containers use this**

1. **`protocol/ws.py`** - WebSocket message handling
   - Parse new `Request` message structure (control/inputs/outputs)
   - Emit new `Response` message structure
   - Remove `RunOpen`, `Token`, `RunResult` types

2. **`protocol/handler.py`** - Tool handler contract
   - Update entry() signature to return new Response format
   - Return `{kind, control, outputs}` instead of flat envelope

3. **`protocol/worker.py`** - Worker process
   - Handle new Response format from handler
   - Write outputs to presigned URLs/local paths

4. **`hydration.py`** - Input/output resolution
   - Update to fetch from presigned URLs (not construct them)
   - Write to presigned PUT URLs (not construct S3 keys)

5. **`envelope.py`** - Envelope builders (DEPRECATED - remove)
   - `success_envelope()` → DELETE
   - `error_envelope()` → DELETE
   - Move to Response message builders

### Tool-Specific Files

**Every tool's `protocol/handler.py` needs updating:**
- `tools/llm/litellm/1/protocol/handler.py`
- `tools/image/*/protocol/handler.py` (future)
- etc.

## Database Changes

### 1. Run Model Updates

#### Fields to Remove
```python
# code/apps/runs/models.py

# DELETE these fields:
meta = models.JSONField(default=dict)  # Replaced by control layer
usage = models.JSONField(null=True, blank=True)  # Tool-specific, not needed
```

#### Migration
```python
# Create migration
python manage.py makemigrations runs --name remove_meta_and_usage

# Migration content:
class Migration(migrations.Migration):
    dependencies = [
        ('runs', '0002_runoutput'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='run',
            name='meta',
        ),
        migrations.RemoveField(
            model_name='run',
            name='usage',
        ),
    ]
```

### 2. RunOutput Model (Legacy - Remove)

```python
# Migration
python manage.py makemigrations runs --name remove_legacy_runoutput

class Migration(migrations.Migration):
    dependencies = [
        ('runs', '0003_remove_meta_and_usage'),
    ]

    operations = [
        migrations.DeleteModel(
            name='RunOutput',
        ),
    ]
```

## Code Changes

### Django Side

#### 1. Run.finalize() Method

**File: `code/apps/runs/models.py`**

```python
def finalize(self, envelope: dict) -> None:
    """Update run from terminal Response envelope."""
    control = envelope.get("control", {})

    # Status from control layer
    status = control.get("status")
    if status == "success":
        self.status = self.Status.SUCCEEDED
    elif status == "error":
        self.status = self.Status.FAILED
    else:
        self.status = self.Status.FAILED

    self.ended_at = timezone.now()

    # Cost from control layer (container calculates)
    self.cost_micro = control.get("cost_micro", 0)

    # Error details
    if status == "error":
        error = envelope.get("error", {})
        self.error_code = error.get("code", "UNKNOWN")
        self.error_message = error.get("message", "")

    self.save()

    # Create artifacts from outputs
    outputs = envelope.get("outputs", {})
    for key, value in outputs.items():
        # Artifact creation (unchanged)
        ...
```

#### 2. Scope Resolution Service

**New file: `code/apps/runs/scope_resolver.py`**

```python
from typing import Dict, Any
from django.conf import settings
from apps.runs.models import Run
from backend.storage.service import storage_service


def resolve_request(request_intent: Dict[str, Any], run: Run) -> Dict[str, Any]:
    """
    Convert agent's request intent to container-ready Request message.
    """
    resolved_inputs = {}
    resolved_outputs = {}

    # Resolve inputs (where to READ from)
    for key, value in request_intent.get("inputs", {}).items():
        if key.endswith(".world"):
            base_key = key[:-6]
            s3_key = f"{run.world.id}/{value.lstrip('/')}"
            url = storage_service.get_download_url(
                key=s3_key,
                bucket=settings.ARTIFACTS_BUCKET,
                expires_in=3600
            )
            resolved_inputs[base_key] = url

        elif key.endswith(".local"):
            base_key = key[:-6]
            path = f"/artifacts/{run.id}/{value.lstrip('/')}"
            resolved_inputs[base_key] = path

        else:
            resolved_inputs[key] = value

    # Resolve outputs (where to WRITE to)
    for key, value in request_intent.get("outputs", {}).items():
        if key.endswith(".world"):
            base_key = key[:-6]
            s3_key = f"{run.world.id}/{value.lstrip('/')}"
            url = storage_service.get_upload_url(
                key=s3_key,
                bucket=settings.ARTIFACTS_BUCKET,
                expires_in=3600,
                content_type="application/octet-stream"
            )
            resolved_outputs[base_key] = url

        elif key.endswith(".local"):
            base_key = key[:-6]
            path = f"/artifacts/{run.id}/{value.lstrip('/')}"
            resolved_outputs[base_key] = path

    # Build container-ready Request
    return {
        "kind": "Request",
        "control": {
            "run_id": str(run.id),
            "mode": request_intent.get("mode", run.mode)
        },
        "inputs": resolved_inputs,
        "outputs": {k: v for k, v in resolved_outputs.items() if v is not None}
    }
```

#### 3. ToolRunner Integration

**File: `code/apps/core/tool_runner.py`**

```python
from apps.runs.scope_resolver import resolve_request

class ToolRunner:
    def invoke(
        self,
        *,
        ref: str,
        mode: str,
        request_intent: dict,
        run: Run,
        stream: bool = False,
        ...
    ):
        # Resolve scopes to presigned URLs
        container_request = resolve_request(request_intent, run)

        # Get adapter and invoke
        adapter_instance, oci = self._pick_adapter(...)

        if stream:
            return adapter_instance.invoke(ref, container_request, timeout_s, oci, stream=True)
        else:
            envelope = adapter_instance.invoke(ref, container_request, timeout_s, oci, stream=False)
            return envelope
```

### Runtime/Container Side

#### 1. WebSocket Protocol

**File: `code/libs/runtime_common/protocol/ws.py`**

```python
@app.websocket("/run")
async def run_ws(ws: WebSocket):
    await ws.accept(subprotocol="theory.run.v1")

    # Receive Request
    msg = await ws.receive_json()

    if msg.get("kind") != "Request":
        await ws.close(code=1002)
        return

    control = msg.get("control", {})
    run_id = control.get("run_id")

    if not run_id:
        await ws.close(code=1008)
        return

    # Build payload for handler
    payload = {
        "run_id": run_id,
        "mode": control.get("mode", "mock"),
        "inputs": msg.get("inputs", {}),
        "outputs": msg.get("outputs", {})
    }

    # Register and ack
    run = await registry.get_or_create(run_id)
    await registry.add_connection(run_id, connection_id, ws, ConnectionRole.CLIENT)

    await ws.send_json({
        "kind": "Ack",
        "control": {"run_id": run_id}
    })

    # Start worker
    await registry.update_state(run_id, RunState.RUNNING)
    proc, events_q, cancel_ev = spawn_worker(payload)
    await registry.bind_worker(run_id, proc, cancel_ev)

    # Pump events
    async def pump():
        while True:
            ev = await loop.run_in_executor(None, events_q.get)
            if ev is None:
                break

            # Update state if terminal Response
            if ev.get("kind") == "Response" and ev.get("control", {}).get("final"):
                status = ev["control"].get("status")
                new_state = RunState.COMPLETED if status == "success" else RunState.ERROR
                await registry.update_state(run_id, new_state)

            await registry.emit(run_id, ev)

    asyncio.create_task(pump())

    # Keep connection open
    while True:
        await asyncio.sleep(30)
```

#### 2. Handler Contract

**File: `code/libs/runtime_common/protocol/handler.py`**

```python
def entry(payload: Dict[str, Any], emit: Callable | None = None, ctrl=None) -> Dict[str, Any]:
    """
    Generic handler - override in tool's protocol/handler.py

    Args:
        payload: {
            "run_id": str,
            "mode": "mock" | "real",
            "inputs": {
                "key": <presigned_url> | <local_path> | <inline_value>
            },
            "outputs": {
                "key": <presigned_put_url> | <local_path>
            }
        }

    Returns:
        {
            "kind": "Response",
            "control": {
                "run_id": str,
                "status": "success" | "error",
                "cost_micro": int,
                "final": bool
            },
            "outputs": {
                "key": <value>
            },
            "error": {  // Only if status == "error"
                "code": str,
                "message": str
            }
        }
    """
    run_id = payload["run_id"]

    if emit:
        emit({"kind": "Event", "control": {"run_id": run_id}, "data": {"phase": "started"}})
        emit({"kind": "Log", "control": {"run_id": run_id}, "data": {"msg": "Using generic handler"}})

    return {
        "kind": "Response",
        "control": {
            "run_id": run_id,
            "status": "success",
            "cost_micro": 0,
            "final": True
        },
        "outputs": {}
    }
```

#### 3. Worker Process

**File: `code/libs/runtime_common/protocol/worker.py`**

```python
def _worker_main(payload: dict, q: Queue, cancel_ev: Event):
    """Worker process - calls handler and sends result."""
    from protocol.handler import entry

    def _emit(ev: dict):
        q.put(ev)

    try:
        # Call handler
        response = entry(payload, emit=_emit, ctrl=cancel_ev)

        # Ensure Response has final=true
        if response.get("kind") == "Response":
            if "control" not in response:
                response["control"] = {}
            response["control"]["final"] = True

        # Send terminal Response
        q.put(response)

    except Exception as e:
        # Send error Response
        q.put({
            "kind": "Response",
            "control": {
                "run_id": payload.get("run_id", ""),
                "status": "error",
                "cost_micro": 0,
                "final": True
            },
            "error": {
                "code": "ERR_HANDLER",
                "message": str(e)
            }
        })
    finally:
        q.put(None)  # Signal done
```

#### 4. Hydration Updates

**File: `code/libs/runtime_common/hydration.py`**

```python
def hydrate_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch inputs from presigned URLs or local paths.

    Args:
        inputs: {
            "key": "https://s3.../presigned-get" | "/artifacts/..." | <inline>
        }

    Returns:
        Hydrated dict with actual values
    """
    result = {}

    for key, value in inputs.items():
        if isinstance(value, str) and value.startswith("https://"):
            # Fetch from presigned GET URL
            response = httpx.get(value, timeout=30)
            response.raise_for_status()
            result[key] = response.content

        elif isinstance(value, str) and value.startswith("/artifacts/"):
            # Read from local filesystem
            result[key] = Path(value).read_bytes()

        else:
            # Inline value
            result[key] = value

    return result


def write_outputs(outputs_schema: Dict[str, str], results: Dict[str, Any]) -> None:
    """
    Write outputs to presigned PUT URLs or local paths.

    Args:
        outputs_schema: {
            "key": "https://s3.../presigned-put" | "/artifacts/..."
        }
        results: Tool's output data
    """
    for key, url in outputs_schema.items():
        if key not in results:
            continue

        data = results[key]

        # Convert to bytes
        if isinstance(data, str):
            content = data.encode("utf-8")
        elif isinstance(data, (dict, list)):
            content = json.dumps(data).encode("utf-8")
        elif isinstance(data, bytes):
            content = data
        else:
            content = json.dumps(data).encode("utf-8")

        # Write to destination
        if url.startswith("https://"):
            # Upload to presigned PUT URL
            response = httpx.put(url, content=content)
            response.raise_for_status()

        elif url.startswith("/artifacts/"):
            # Write to local filesystem
            path = Path(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
```

#### 5. Tool Handler Example

**File: `tools/llm/litellm/1/protocol/handler.py`**

```python
import os
from libs.runtime_common.hydration import hydrate_inputs, write_outputs

def entry(payload, emit, ctrl):
    run_id = payload["run_id"]
    mode = payload["mode"]

    # Hydrate inputs
    inputs = hydrate_inputs(payload["inputs"])
    messages = inputs.get("messages", [])
    model = inputs.get("model", "gpt-4o-mini")

    # Get output schema
    outputs_schema = payload.get("outputs", {})

    if emit:
        emit({"kind": "Event", "control": {"run_id": run_id}, "data": {"phase": "started"}})

    # Generate response
    if mode == "mock":
        text = f"Mock: {messages[-1]['content'][:50] if messages else ''}"
        api_cost = 0
    else:
        import litellm
        resp = litellm.completion(model=model, messages=messages)
        text = resp.choices[0].message.content

        # Calculate API cost (container knows pricing)
        usage = resp.usage
        api_cost = (usage.prompt_tokens * 0.15 + usage.completion_tokens * 0.60) * 1_000_000 // 1_000_000

    # Calculate compute cost (container knows Modal pricing)
    compute_cost = 100  # Example: $0.0001

    # Write outputs
    write_outputs(outputs_schema, {"response": text})

    # Return Response
    return {
        "kind": "Response",
        "control": {
            "run_id": run_id,
            "status": "success",
            "cost_micro": api_cost + compute_cost,
            "final": True
        },
        "outputs": {
            "response": outputs_schema.get("response"),  # Confirm location
            "tokens": len(text.split())  // Inline output
        }
    }
```

## Migration Steps

### Phase 1: Database
```bash
python manage.py makemigrations runs --name remove_meta_and_usage
python manage.py makemigrations runs --name remove_legacy_runoutput
python manage.py migrate
```

### Phase 2: Runtime Updates (Container Side)
1. ✅ Update `protocol/ws.py` - parse Request, emit Response
2. ✅ Update `protocol/handler.py` - new entry() contract
3. ✅ Update `protocol/worker.py` - handle Response format
4. ✅ Update `hydration.py` - fetch from URLs, write to URLs
5. ✅ Remove `envelope.py` (deprecated)

### Phase 3: Django Updates (Control Plane)
1. ✅ Add `scope_resolver.py` service
2. ✅ Update `Run.finalize()` method
3. ✅ Update `ToolRunner.invoke()` to use resolver
4. ✅ Update adapters to handle Request/Response

### Phase 4: Tool Updates
1. ✅ Update `tools/llm/litellm/1/protocol/handler.py`
2. ✅ Update other tools as needed

### Phase 5: Testing
```bash
# Local adapter
make start-tools ADAPTER=local
make test-integration

# Modal adapter
make start-tools ADAPTER=modal ENV=dev
make test-integration
```

## Validation Checklist

### Runtime
- [ ] Request messages parsed correctly
- [ ] Response messages emitted correctly
- [ ] Log/Event messages work
- [ ] Hydration fetches from presigned URLs
- [ ] Output writing to presigned PUT URLs works
- [ ] Local paths (/artifacts/) work
- [ ] Streaming responses work (final flag)

### Django
- [ ] Scope resolver generates valid presigned URLs
- [ ] World boundary validation works
- [ ] Run.finalize() extracts cost from control
- [ ] Artifacts created from outputs
- [ ] GraphQL queries work

### End-to-End
- [ ] Full request → response cycle works
- [ ] Cost tracking accurate
- [ ] Multi-turn agents work
- [ ] Error envelopes handled
- [ ] All integration tests pass

## Rollback Plan

```bash
# Revert migrations
python manage.py migrate runs 0002

# Restore old code
git revert <protocol-refactor-commits>

# Rebuild containers
docker build ...
make start-tools
```
