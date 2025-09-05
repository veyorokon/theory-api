# Facets & WorldPath

Paths use a canonical grammar: lowercase, normalized slashes, no `.` or `..`.  
Key facets organize the :term:`World` into logical namespaces.

## Path Grammar

All world addresses follow this pattern:
```
world://{tenant}/{plan}/{facet}/{subpath...}
```

### Rules

- **Lowercase only** - `world://acme/plan-123/artifacts/scene.json`
- **Normalized slashes** - No `//`, `./`, `../`  
- **Single leading slash** - `/world/...` not `world://...` in selectors
- **No trailing slash** - Unless indicating a directory by convention
- **Required components** - tenant and plan are always present

### Examples

```
world://acme/video-001/artifacts/script.json          # File artifact
world://acme/video-001/streams/camera/frames/         # Stream directory  
world://acme/video-001/plan/transitions/render-video/ # Plan data
```

## Core Facets

### `artifacts/` - Immutable Data

Stores files, JSON objects, and other persistent data:

```
world://acme/plan-123/artifacts/
  ├── script.json
  ├── scenes/
  │   ├── 001/shotlist.json
  │   └── 002/storyboard.png
  └── final/video.mp4
```

### `streams/` - Real-time Data

Handles high-frequency, ephemeral data flows:

```
world://acme/plan-123/streams/
  ├── mic/audio/           # Audio chunks
  ├── camera/frames/       # Video frames
  └── dialogue/tokens/     # Text deltas
```

### `plan/` - Execution Graph

Contains the plan itself as data:

```
world://acme/plan-123/plan/
  ├── transitions/
  │   ├── write-script/
  │   └── render-video/
  └── dependencies/
      └── script-to-video/
```

## Selectors & Leases

**Selectors** specify which paths a transition will write to:

```json
{
  "kind": "prefix", 
  "path": "/world/acme/plan-123/artifacts/scenes/"
}
```

```json  
{
  "kind": "exact",
  "path": "/world/acme/plan-123/artifacts/final.mp4"
}
```

At admission time, selectors are resolved to :term:`Lease` objects that prevent write conflicts. Only one execution can hold a lease on overlapping paths.

## Custom Facets

Applications can define custom facets for domain-specific organization:

- `senses/` - Input streams from environment
- `effectors/` - Output streams to environment  
- `memories/` - Long-term agent memories
- `conversations/` - Chat message histories

The grammar is flexible while maintaining consistency and safety.