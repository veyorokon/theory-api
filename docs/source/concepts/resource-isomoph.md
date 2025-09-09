# Resource Isomorph — Adapters for KV, Queue, Volume, Secrets

> One interface, many backends. World stays pure (/artifacts, /streams). Scratch is replaceable. Adapters prevent abstraction bleed.

---

## 1) Purpose

Unify access to **infrastructure primitives** behind thin **adapters** so processors run unchanged on **local | modal | aws/minio**. Keep **World** (artifacts/streams) immutable and auditable; keep **scratch** (KV/Queue/temp volumes) ephemeral and swappable. Prevent provider-specific logic from leaking into tools/processors.

---

## 2) Scope / Non-Goals

**In-scope**

* Interfaces + minimal semantics for **KV**, **Queue**, **Volume/ArtifactStore**, **Secrets**.
* Adapter implementations: **local** (dev), **modal**, **aws/minio** (S3/MinIO + SQS) — phased.
* Event sampling of scratch into **World** for audit/predicates.

**Out-of-scope (MVP)**

* Leases enforcement (still façade).
* FIFO/DLQ guarantees across all queues (offer at-least-once first).
* Cron/timers, workflows, or cross-plan orchestration.

---

## 3) World vs Scratch (hard boundary)

* **World** = **/artifacts/** (immutable files/JSON) + **/streams/** (live, sampled to ledger).
  Addressable by **WorldPath**, governed by **policy**, recorded in the **ledger**, participates in **receipts/determinism**.

* **Scratch** = **KV**, **Queue**, **temp volumes**.
  Plan-scoped coordination. Not addressable by WorldPath. Not policy-gated directly. If it matters, **sample** into World (event/artifact).

* **Secrets** = out-of-band; only **names** appear in policy/receipts/fingerprint (no values stored).

---

## 4) Interfaces (authoritative surface)

> Names are stable; implementations are replaceable. All methods are **plan-scoped** unless noted.

```python
# KV (ephemeral, plan-scoped)
class KVAdapter(Protocol):
    def get(self, *, plan_id: str, key: str) -> bytes | None: ...
    def put(self, *, plan_id: str, key: str, value: bytes, ttl_s: int | None = None) -> None: ...
    def delete(self, *, plan_id: str, key: str) -> None: ...
    def incr(self, *, plan_id: str, key: str, by: int = 1, ttl_s: int | None = None) -> int: ...

# Queue (at-least-once, plan-scoped)
class QueueAdapter(Protocol):
    def publish(self, *, plan_id: str, topic: str, body: bytes, idempotency_key: str | None = None) -> str: ...
    def consume(self, *, plan_id: str, topic: str, max_messages: int = 1, visibility_timeout_s: int = 30) -> list[dict]: ...
    def ack(self, *, plan_id: str, topic: str, receipt_handle: str) -> None: ...
    def nack(self, *, plan_id: str, topic: str, receipt_handle: str, delay_s: int = 0) -> None: ...

# ArtifactStore (WorldPath -> bytes, immutable)
class ArtifactStore(Protocol):
    def put_bytes(self, *, world_path: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get_bytes(self, *, world_path: str) -> bytes: ...
    def presign(self, *, world_path: str, ttl_s: int = 3600) -> str: ...
    def compute_cid(self, *, data: bytes) -> str: ...

# Secrets (names-only)
class SecretResolver(Protocol):
    def get(self, name: str) -> str  # raises if missing
```

**WorldPath rules** apply inside `ArtifactStore` (lowercase, NFC, single decode, reject `%2F`, no `.`/`..`, leading `/`, facet-rooted, prefix ends `/`).

---

## 5) Adapter Matrix (isomorph)

| Primitive         | **local** (dev)                            | **modal**                                     | **aws/minio**             |
| ----------------- | ------------------------------------------ | --------------------------------------------- | ------------------------- |
| **KV**            | Redis (docker-compose) / in-proc for tests | `modal.Dict`                                  | Redis/ElastiCache         |
| **Queue**         | Redis Streams / local SQS emulator         | `modal.Queue`                                 | SQS                       |
| **ArtifactStore** | MinIO (S3 API) via our shim                | Presigned URLs back to the same ArtifactStore | S3/MinIO                  |
| **Secrets**       | OS env / `.env`                            | Modal secrets                                 | AWS Secrets Manager / env |

**Runtime adapters** (execute processors): `local | mock | modal` — **all** run **containers**; processors never import provider SDKs in Django.

---

## 6) Semantics (contracts we guarantee)

* **KV:** read-your-writes (local strong), TTL optional, no global ordering.
* **Queue:** **at-least-once**, visibility timeout, no strict ordering (FIFO/DLQ later).
* **ArtifactStore:** immutable by path; returns **CID** on write; presign for read.
* **Secrets:** resolved before dispatch; injected as env vars to containers; names go into `env_fingerprint`.

If a predicate needs scratch truth, **sample**: write a small artifact (JSON) or emit a ledger event. Predicates read **World**, not scratch.

---

## 7) Events & Sampling (audit path)

Emit plan-scoped events when scratch state matters:

* `scratch.queue.published` `{topic, bytes, approx_size}` (no sensitive payload in event)
* `scratch.kv.changed` `{key, op}`
* `streams.sampled` `{series, watermark, every_n}`
* `artifact.written` `{path, cid, size}` (already covered by writes)

All events use **`kind` + `ts`**, JCS-hashed (BLAKE3), with `seq/prev_hash/this_hash`.

---

## 8) Determinism & Receipts

* ArtifactStore computes **BLAKE3 CIDs** for outputs; determinism receipt at settle includes `input_cids`, `output_cids`, and **`env_fingerprint`** ({image\_digest, gpu(model,count,mem\_gb)? , cpu, memory\_gb, timeout\_s, region, present\_env\_keys(sorted), py\_ver, django\_ver, …} JCS→hash).
* Scratch state is **not** part of determinism; only sampled artifacts/events are.

---

## 9) Policy & Safety

* **Admission** gates only **WorldPath selectors** (`/artifacts/**`, `/streams/**`).
* Scratch usage (KV/Queue/Secrets) is allowed per processor registry; required secret **names** are listed there.
* Leases remain façade (flag available; enforcement later).
* Budget reserve→settle applies to processor execution; read-only tools (queries) do not reserve.

---

## 10) Error Handling & Backpressure

* **Queue**: nack with `delay_s` for retry; emit `scratch.queue.retry` events; optional max retries → `scratch.queue.deadletter` later.
* **KV**: transient errors surface to adapter; processors fail fast; orchestrator may retry based on policy.
* **Streams** (separate slice): track `watermark_idx`, `chunk_count`, `dropped_chunks`; one counter persisted in DB; sample to ledger every N frames.

---

## 11) Testing & CI

* **Unit (SQLite):** in-proc or Docker Redis; MinIO mocked; ArtifactStore path canonicalization tests; KV/Queue happy-path tests.
* **Acceptance (Postgres):** run with MinIO + Redis compose services.
* **Docs drift:** registry renders processor/runtime/adapter/secrets/outputs.
* **Guards:** forbid importing legacy “providers” for SDKs in Django; only **adapters** remain.

---

## 12) Repo Layout (authoritative)

```
code/apps/core/adapters/
  base.py                # RuntimeAdapter ABC
  local_adapter.py
  modal_adapter.py
  mock_adapter.py

code/apps/core/resources/
  kv.py                  # KVAdapter impls (local/modal/aws)
  queue.py               # QueueAdapter impls
  secrets.py             # SecretResolver
  __init__.py

code/apps/storage/artifact_store.py   # WorldPath <-> (bucket,key), CID, presign

code/apps/core/processors/<name>/
  Dockerfile
  processor.py
  requirements.txt

code/apps/core/registry/
  processors/*.yaml      # image.oci, runtime, adapter.modal, secrets, outputs
```

---

## 13) Migration Plan (thin slices)

1. **0021**

   * Land **RuntimeAdapter** + **local/modal/mock** adapters (containers everywhere).
   * Add **ArtifactStore** shim (WorldPath canonicalization, CID, presign).
   * Introduce **resources/** package with KV/Queue/Secrets interfaces (local impls for tests).
   * Remove `hello_llm`; docs point to `run_processor`.
   * `artifact.jmespath_ok@1` live.

2. **0022**

   * First GPU processor on Modal (Multitalk): uses adapters + ArtifactStore; no direct provider calls.

3. **0014/0024**

   * Streaming smoke (sampled events), CAS receipts (CIDs in receipts/events).

4. **Cleanup**

   * Remove in-Django LiteLLM “provider”; add CI guard; docs\_export covers registry fields.

---

## 14) ADR Triggers (if we change these, write an ADR)

* Expanding **World** beyond `/artifacts/**` and `/streams/**`.
* Making **KV/Queue** policy-controlled or part of selectors.
* Strong delivery guarantees (global FIFO) that constrain adapters.
* Leases **enforcement** semantics.

---

## 15) Quick Examples

**Publish to queue (scratch) → sample into World later**

* Processor uses `QueueAdapter.publish(plan_id, topic, body, idempotency_key)`.
* Orchestrator emits `scratch.queue.published` (no sensitive body).
* A periodic job writes `/artifacts/metrics/queue_stats.json` with counts → predicates can assert via `artifact.jmespath_ok@1`.

**Write artifact (World)**

* Processor uploads bytes via presigned URL from `ArtifactStore.put_bytes` → returns `/artifacts/outputs/…` and **CID**.
* Success predicates: `artifact.exists@1`, `artifact.jmespath_ok@1`.
* Receipts include `output_cids`.

---

## 16) TL;DR

* **World = artifacts + streams.**
* **Scratch = KV/Queue/temp volumes;** if it matters, **sample to World**.
* **Adapters** give one interface across **local | modal | aws/minio**.
* **Processors run in containers**; SDKs live inside images.
* **Secrets by name**; **events** use `kind+ts` with JCS+BLAKE3; **receipts** include CIDs and env fingerprint.
