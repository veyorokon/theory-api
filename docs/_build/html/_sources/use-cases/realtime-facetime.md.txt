# Real-time FaceTime Agent

**World streams:**
- `/senses/mic/audio`, `/senses/camera/frames` (inputs)
- `/effectors/mouth/audio`, `/effectors/face/video` (outputs)

**Transitions:**
- `agent.dialogue_turn@1` (micro-transitions), `tts.synthesize@1`, `video.diffusion.stream@1`.

**Low latency:** Modal Workers ↔ Channels/WebRTC Gateway; artifact series for buffering.

## Scenario

Create a real-time AI agent that can have natural conversations through video calls:
- **See** the user via camera feed
- **Hear** the user via microphone  
- **Speak** back with synthesized voice
- **Show** facial expressions and gestures

Target latency: <200ms end-to-end for natural conversation flow.

## World Layout

```
world://acme/facetime-session-123/
├── streams/
│   ├── senses/
│   │   ├── mic/audio/          # Input audio chunks (48kHz)
│   │   └── camera/frames/      # Input video frames (30fps)
│   └── effectors/
│       ├── mouth/audio/        # Output audio chunks  
│       └── face/video/         # Output video frames
├── artifacts/
│   ├── conversation/
│   │   ├── messages/           # Persistent chat history
│   │   └── summaries/          # Conversation summaries
│   └── state/
│       ├── emotion.json        # Current emotional state
│       └── context.json        # Conversation context
└── plan/
    └── transitions/
        ├── audio-process/      # Real-time audio processing
        ├── vision-process/     # Real-time video processing  
        ├── dialogue-turn/      # Conversation logic
        ├── speech-synthesis/   # Audio generation
        └── face-generation/    # Video generation
```

## Real-time Processing Pipeline

```{mermaid}
sequenceDiagram
    participant U as User
    participant WS as WebRTC/WebSocket
    participant S as Stream Processor
    participant A as Agent  
    participant TTS as Speech Synthesis
    participant FG as Face Generation
    
    U->>WS: Audio/Video chunks
    WS->>S: Append to world streams
    S->>A: Process audio → text
    A->>A: Generate response
    A->>TTS: Synthesize speech
    A->>FG: Generate facial animation  
    TTS->>WS: Audio chunks
    FG->>WS: Video frames
    WS->>U: Real-time A/V stream
```

## Micro-Transitions

### Audio Processing

```yaml
id: process-audio-chunk
processor_ref: tool:speech.transcribe@1
trigger: stream_event
inputs:
  audio_chunk: streams/senses/mic/audio/latest
  language: "en"
write_set:
  - kind: exact  
    path: world://artifacts/conversation/audio-transcript.json
predicates:
  success:
    - id: json.schema_ok@1
      args:
        path: world://artifacts/conversation/audio-transcript.json
        schema_ref: speech.transcript@1
```

### Dialogue Turn

```yaml
id: dialogue-turn
processor_ref: agent:conversational@1
trigger: artifact_changed  
inputs:
  transcript: world://artifacts/conversation/audio-transcript.json
  conversation_history: world://artifacts/conversation/messages/
  emotional_state: world://artifacts/state/emotion.json
write_set:
  - kind: exact
    path: world://artifacts/conversation/response.json
predicates:
  admission:
    - id: artifact.exists@1
      args: {path: world://artifacts/conversation/audio-transcript.json}
  success:
    - id: json.schema_ok@1
      args:
        path: world://artifacts/conversation/response.json
        schema_ref: dialogue.response@1
```

### Speech Synthesis

```yaml  
id: synthesize-speech
processor_ref: tool:tts.elevenlabs@1
trigger: artifact_changed
inputs:
  text: world://artifacts/conversation/response.json#text
  voice_id: "natural_conversation"
  streaming: true
write_set:
  - kind: prefix
    path: world://streams/effectors/mouth/audio/
predicates:
  admission:
    - id: artifact.exists@1  
      args: {path: world://artifacts/conversation/response.json}
  success:
    - id: stream.has_data@1
      args: 
        path: world://streams/effectors/mouth/audio/
        min_chunks: 1
```

### Face Generation

```yaml
id: generate-face
processor_ref: tool:video.liveportrait@1
trigger: artifact_changed
inputs:
  response_text: world://artifacts/conversation/response.json#text
  emotional_tone: world://artifacts/conversation/response.json#emotion
  base_face: world://artifacts/avatar/base_face.jpg
write_set:
  - kind: prefix  
    path: world://streams/effectors/face/video/
predicates:
  admission:
    - id: artifact.exists@1
      args: {path: world://artifacts/conversation/response.json}
  success:
    - id: stream.has_data@1
      args:
        path: world://streams/effectors/face/video/
        min_chunks: 5  # ~200ms of video at 25fps
```

## Latency Optimization

### Stream Buffering

```python  
class StreamBuffer:
    def __init__(self, target_latency_ms=150):
        self.target_latency = target_latency_ms
        self.buffer = collections.deque()
        
    def should_process(self, current_chunk):
        """Decide if we have enough data to start processing."""
        buffer_duration = self.estimate_duration()
        return buffer_duration >= self.target_latency
```

### Parallel Processing

Multiple agents work simultaneously:
- **Audio Agent** - Processes speech → text
- **Vision Agent** - Analyzes facial expressions/gestures  
- **Dialogue Agent** - Generates responses
- **Synthesis Agent** - Creates audio output
- **Animation Agent** - Creates video output

### WebRTC Integration

```{mermaid}
graph LR  
    subgraph "Modal Workers"
        AP[Audio Processor]
        DA[Dialogue Agent]  
        TTS[Speech Synthesis]
        FG[Face Generator]
    end
    
    subgraph "Django Channels"
        WS[WebSocket Consumer]
        SB[Stream Buffer]  
    end
    
    subgraph "Client"
        WebRTC[WebRTC Client]
        UI[React UI]
    end
    
    WebRTC <--> WS
    WS <--> SB
    SB <--> AP
    AP --> DA
    DA --> TTS  
    DA --> FG
    TTS --> SB
    FG --> SB
    SB <--> WS
```

## Performance Targets

- **Audio latency**: <100ms (mic → processing → response)
- **Video latency**: <150ms (camera → analysis → face generation)  
- **End-to-end**: <200ms (user speech → agent response)
- **Frame rate**: 25fps minimum for smooth video
- **Audio quality**: 48kHz, 16-bit for clarity

## Resource Requirements

```yaml
resources:
  audio_processor:
    cpu: "1000m"    # 1 CPU core
    memory: "2Gi"   # 2GB RAM
    
  dialogue_agent:  
    cpu: "2000m"    # 2 CPU cores (for LLM)
    memory: "4Gi"   # 4GB RAM
    
  speech_synthesis:
    cpu: "1000m"
    memory: "1Gi"
    
  face_generation:
    gpu: "T4"       # NVIDIA T4 for real-time inference
    memory: "8Gi"
```

## Budget Controls

```yaml  
budget:
  max_usd_micro: 50000     # $0.05 per minute of conversation
  hard_timeout_s: 3600     # 1 hour max session
  
rate_limits:
  max_tokens_per_minute: 1000
  max_audio_chunks_per_second: 50
  max_video_frames_per_second: 30
```

```{include} ../../_generated/examples/realtime-sequence.md
```