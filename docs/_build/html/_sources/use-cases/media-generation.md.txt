# Media Generation

**Goal:** Produce a 60s marketing video.

**Plan facet:**
- `transitions/script`: `tool:text.llm@1` → `world://artifacts/script.json`
- `transitions/shotlist`: `tool:media.shotlist@1` (depends on script)  
- `transitions/render`: `tool:media.render@1` → `world://artifacts/final.mp4`

**Predicates:**
- admission: `artifact.exists(script.json)`
- success: `file.exists(final.mp4)`

## Scenario

A marketing team needs to produce a 60-second promotional video for a new product launch. The video should include:
- Engaging script tailored to target audience
- Shot list with visual descriptions
- Rendered video with transitions and audio

## Plan Structure

```{mermaid}
graph TD
    A[write-script] --> B[generate-shotlist]
    B --> C[render-frames]
    C --> D[compose-video]
    
    A --> E[world://artifacts/script.json]
    B --> F[world://artifacts/shotlist.json]
    C --> G[world://artifacts/frames/]
    D --> H[world://artifacts/final.mp4]
```

## Transitions

### 1. Script Generation

```yaml
id: write-script
processor_ref: tool:text.llm@1
inputs:
  prompt: "Write a 60-second marketing script for ${product_description}"
  model: "gpt-4"
write_set:
  - kind: exact
    path: world://artifacts/script.json
predicates:
  admission:
    - id: budget.available@1
      args: {required_usd_micro: 5000}  # $0.05
  success:
    - id: json.schema_ok@1
      args: 
        path: world://artifacts/script.json
        schema_ref: media.script@1
```

### 2. Shot List Generation  

```yaml
id: generate-shotlist
processor_ref: tool:media.shotlist@1
dependencies: [write-script]
inputs:
  script_path: world://artifacts/script.json
write_set:
  - kind: exact
    path: world://artifacts/shotlist.json
predicates:
  admission:
    - id: artifact.exists@1
      args: {path: world://artifacts/script.json}
  success:
    - id: json.schema_ok@1
      args:
        path: world://artifacts/shotlist.json
        schema_ref: media.shotlist@1
```

### 3. Frame Rendering

```yaml
id: render-frames
processor_ref: tool:img.generate@1
dependencies: [generate-shotlist]
inputs:
  shotlist_path: world://artifacts/shotlist.json
  style: "professional marketing"
write_set:
  - kind: prefix
    path: world://artifacts/frames/
predicates:
  admission:
    - id: artifact.exists@1
      args: {path: world://artifacts/shotlist.json}
  success:
    - id: file.count_min@1
      args:
        path: world://artifacts/frames/
        min_files: 10
```

### 4. Video Composition

```yaml
id: compose-video
processor_ref: tool:ffmpeg.render@1
dependencies: [render-frames]
inputs:
  frames_dir: world://artifacts/frames/
  script_path: world://artifacts/script.json
  output_format: "mp4"
  duration_s: 60
write_set:
  - kind: exact
    path: world://artifacts/final.mp4
predicates:
  admission:
    - id: file.count_min@1
      args:
        path: world://artifacts/frames/
        min_files: 10
  success:
    - id: file.exists@1
      args: {path: world://artifacts/final.mp4}
    - id: media.duration_between@1
      args:
        path: world://artifacts/final.mp4
        min_ms: 58000
        max_ms: 62000
```

## Flow (High Level)

1. **Propose transitions** - Marketing team creates plan with product details
2. **Script generation** - LLM generates compelling marketing copy  
3. **Shot planning** - AI creates visual shot list based on script
4. **Frame rendering** - Image generation creates individual frames
5. **Video composition** - FFmpeg combines frames with timing and transitions
6. **Quality checks** - Success predicates validate output quality

## Artifacts Produced

- `script.json` - Marketing script with timing and dialogue
- `shotlist.json` - Visual descriptions for each scene  
- `frames/` - Individual rendered images
- `final.mp4` - Completed 60-second marketing video

## Budget & Resources

- **Script generation**: ~$0.05 (5,000 tokens @ $0.01/1k)
- **Image generation**: ~$2.00 (20 images @ $0.10 each)
- **Rendering**: ~$0.10 (compute time)
- **Total estimate**: ~$2.15

## Error Handling

If any transition fails:
- **Script issues**: Retry with refined prompt
- **Image generation**: Fall back to stock imagery  
- **Rendering failures**: Adjust parameters and retry
- **Budget exceeded**: Pause and require approval

```{include} ../../_generated/examples/media-dag.md
```