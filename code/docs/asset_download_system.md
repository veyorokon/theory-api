# Asset Download System

The Theory asset download system provides secure, bounded downloading of external assets with comprehensive security controls, deterministic naming, and configurable policies.

## Overview

The asset download system consists of four main components:

1. **Asset Downloader** (`libs.runtime_common.asset_downloader`) - Core downloading with SSRF protection
2. **Asset Naming** (`libs.runtime_common.asset_naming`) - Deterministic, content-addressed naming
3. **Asset Policy** (`libs.runtime_common.asset_policy`) - Configurable policies and environment controls
4. **Processor Integration** - Integration with processors like `replicate_generic`

## Security Features

### SSRF Protection

The system protects against Server-Side Request Forgery (SSRF) attacks by:

- **Scheme Allowlisting**: Only `http` and `https` schemes allowed by default
- **Network Blocking**: Automatic blocking of private networks and localhost:
  - `127.0.0.0/8` (localhost)
  - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (private networks)
  - `169.254.0.0/16` (link-local)
  - `224.0.0.0/4` (multicast)
  - IPv6 equivalents
- **DNS Resolution Validation**: All hostnames resolved to IP addresses and checked against blocked networks

### Resource Limits

Configurable limits prevent resource exhaustion:

- **Size Limits**: Maximum download size (default 50MB)
- **Timeout Limits**: Request timeout (default 30s)
- **Asset Count Limits**: Maximum assets per execution (default 10)
- **Streaming Downloads**: Large files streamed in chunks to avoid memory issues

## Deterministic Naming

Assets are named deterministically using content-addressed naming:

### Content Hashing

- **BLAKE3** hashing used when available (falls back to SHA256)
- **Deterministic**: Same content always produces same hash
- **Collision Resistant**: Different content produces different hashes

### Filename Generation

```python
# Example: 08227cf4b90a_replicate.webp
{content_hash[:12]}_{domain_hint}.{extension}
```

Components:
- **Content Hash Prefix**: First 12 characters of content hash
- **Domain Hint**: Sanitized source domain (e.g., "replicate" from "replicate.delivery")
- **Extension**: Determined from Content-Type header or URL

### Asset Receipts

Complete metadata tracking for each downloaded asset:

```python
@dataclass
class AssetReceipt:
    content_hash: str           # Full content hash
    content_size: int           # Size in bytes
    source_url: str            # Original URL
    download_timestamp: str     # ISO timestamp
    filename: str              # Deterministic filename
    content_type: Optional[str] # MIME type
    extension: str             # File extension
    metadata: Dict[str, str]   # Additional metadata
```

## Policy Configuration

### Policy Hierarchy

Policies are resolved in priority order:

1. **Environment Override** (highest priority)
2. **Processor-Specific Policy**
3. **Default Policy** (lowest priority)

### Default Policies

#### Global Default
```python
AssetPolicy(
    enabled=True,
    max_bytes=50 * 1024 * 1024,  # 50MB
    timeout_s=30,
    max_assets_per_execution=10,
    allowed_schemes=["https"],
    allowed_content_types=["image/*", "application/json", "text/*"],
    use_deterministic_names=True,
)
```

#### Replicate Processor
```python
AssetPolicy(
    enabled=True,
    max_bytes=100 * 1024 * 1024,  # 100MB for high-res images
    timeout_s=60,                 # Longer timeout for AI generation
    max_assets_per_execution=20,
    allowed_content_types=["image/*", "video/*", "application/json"],
)
```

#### LLM Processors
```python
AssetPolicy(
    enabled=False,  # Most LLM processors don't generate downloadable assets
    max_bytes=10 * 1024 * 1024,
    timeout_s=15,
)
```

### Environment-Specific Policies

#### CI Environment
```python
AssetPolicy(
    enabled=False,  # Disable downloads in CI
    max_bytes=1 * 1024 * 1024,
    timeout_s=10,
)
```

#### Unit Tests
```python
AssetPolicy(
    enabled=False,  # Always disabled in unit tests
    max_bytes=0,
    timeout_s=1,
)
```

## Usage Examples

### Basic Asset Download

```python
from libs.runtime_common.asset_downloader import download_asset, AssetDownloadConfig

# Configure download
config = AssetDownloadConfig(
    enabled=True,
    max_bytes=10 * 1024 * 1024,  # 10MB limit
    timeout_s=30,
)

# Download asset
try:
    content, content_type = download_asset("https://example.com/image.png", config)
    print(f"Downloaded {len(content)} bytes of {content_type}")
except AssetDownloadError as e:
    print(f"Download failed: {e}")
```

### Policy-Based Configuration

```python
from libs.runtime_common.asset_policy import get_asset_download_config

# Get config for specific processor
config = get_asset_download_config("replicate/generic@1")

# Download with policy-based config
content, content_type = download_asset(url, config)
```

### Deterministic Naming

```python
from libs.runtime_common.asset_naming import create_asset_receipt

# Create asset receipt with deterministic naming
receipt = create_asset_receipt(
    content=content,
    source_url="https://replicate.delivery/path/image.webp",
    content_type="image/webp",
    additional_metadata={"asset_index": "0"}
)

print(f"Filename: {receipt.filename}")  # e.g., "08227cf4b90a_replicate.webp"
print(f"Hash: {receipt.content_hash}")
print(f"Size: {receipt.content_size}")
```

### Processor Integration

```python
# In processor implementation
from libs.runtime_common.asset_policy import get_asset_download_config
from libs.runtime_common.asset_downloader import download_asset
from libs.runtime_common.asset_naming import create_asset_receipt

# Get policy-based configuration
dl_cfg = get_asset_download_config("replicate/generic@1")

if dl_cfg.enabled:
    for idx, url in enumerate(asset_urls):
        try:
            # Download asset
            data, content_type = download_asset(url, dl_cfg)

            # Create deterministic receipt
            receipt = create_asset_receipt(
                content=data,
                source_url=url,
                content_type=content_type,
                additional_metadata={"asset_index": str(idx)}
            )

            # Use deterministic filename
            rel = f"outputs/assets/{idx:02d}_{receipt.filename}"
            outputs.append(OutputItem(
                relpath=rel,
                bytes_=data,
                meta={
                    "source_url": url,
                    "content_hash": receipt.content_hash,
                    "content_size": str(receipt.content_size),
                    "download_timestamp": receipt.download_timestamp,
                }
            ))

        except AssetDownloadError:
            # Skip failed assets, continue processing
            continue
```

## Environment Detection

The system automatically detects execution environments:

- **CI**: `CI=true` environment variable
- **Smoke**: `SMOKE=true` environment variable
- **Unit Tests**: `DJANGO_SETTINGS_MODULE=*.unittest`
- **Integration Tests**: `DJANGO_SETTINGS_MODULE=*.test`

Different environments get different default policies to ensure security and performance.

## Error Handling

### Exception Hierarchy

```python
AssetDownloadError          # Base exception
├── SSRFProtectionError     # SSRF security violation
└── ResourceLimitError      # Resource limit exceeded
```

### Error Examples

```python
# SSRF protection
try:
    download_asset("http://localhost/internal", config)
except SSRFProtectionError as e:
    print(f"Blocked by SSRF protection: {e}")

# Resource limits
try:
    download_asset("https://example.com/huge-file", config)
except ResourceLimitError as e:
    print(f"Resource limit exceeded: {e}")

# General download errors
try:
    download_asset("https://nonexistent.example.com/file", config)
except AssetDownloadError as e:
    print(f"Download failed: {e}")
```

## Testing

### Unit Tests

Comprehensive unit tests cover:

- **Configuration validation**
- **SSRF protection mechanisms**
- **Resource limit enforcement**
- **Deterministic naming properties**
- **Policy resolution logic**
- **Environment detection**

### Test Coverage

```bash
# Run asset system tests
cd code
DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest tests/unit/test_asset_system_simple.py -v

# Run all asset-related tests
python -m pytest tests/unit/test_asset_*.py -v
```

## Integration with Processors

### Replicate Generic Processor

The `replicate_generic` processor demonstrates full integration:

1. **Policy-Based Configuration**: Uses `get_asset_download_config("replicate/generic@1")`
2. **Secure Downloads**: All downloads go through SSRF protection
3. **Deterministic Naming**: Assets named using content hashes
4. **Complete Receipts**: Full metadata including source URLs and timestamps
5. **Graceful Failures**: Failed downloads don't break execution

### Adding Asset Downloads to New Processors

To add asset downloads to a new processor:

1. **Import required modules**:
   ```python
   from libs.runtime_common.asset_policy import get_asset_download_config
   from libs.runtime_common.asset_downloader import download_asset, AssetDownloadError
   from libs.runtime_common.asset_naming import create_asset_receipt
   ```

2. **Get policy configuration**:
   ```python
   dl_cfg = get_asset_download_config("your/processor@1")
   ```

3. **Download and name assets**:
   ```python
   if dl_cfg.enabled:
       data, content_type = download_asset(url, dl_cfg)
       receipt = create_asset_receipt(data, url, content_type)
   ```

4. **Update processor policy** (if needed):
   Edit `libs.runtime_common.asset_policy.py` to add processor-specific policies.

## Security Best Practices

1. **Always Use Policy System**: Don't hardcode download configurations
2. **Environment Awareness**: Test that CI/unittest environments disable downloads
3. **Graceful Degradation**: Handle download failures without breaking execution
4. **Resource Monitoring**: Monitor download sizes and counts in production
5. **SSRF Validation**: Never bypass SSRF protection mechanisms
6. **Content Validation**: Validate downloaded content types when possible

## Migration from Legacy Systems

### From Manual Asset Downloads

**Before**:
```python
import requests
response = requests.get(url)
content = response.content
filename = f"asset_{idx}.bin"
```

**After**:
```python
config = get_asset_download_config("your/processor@1")
content, content_type = download_asset(url, config)
receipt = create_asset_receipt(content, url, content_type)
filename = receipt.filename  # Deterministic, content-addressed
```

### Benefits of Migration

- **Security**: Automatic SSRF protection
- **Consistency**: Deterministic naming across all environments
- **Observability**: Complete asset receipts and metadata
- **Configuration**: Centralized policy management
- **Testing**: Environment-aware disable/enable

## Performance Considerations

- **Streaming**: Large files are streamed in chunks to avoid memory issues
- **Timeouts**: Configurable timeouts prevent hanging requests
- **Size Limits**: Prevents downloading unexpectedly large files
- **Lazy Imports**: `requests` library only imported when needed
- **Content Addressing**: Enables future deduplication across executions

## Future Enhancements

Potential future improvements:

1. **Content Deduplication**: Skip downloading if content hash already exists
2. **Retry Logic**: Configurable retry policies for transient failures
3. **Content Validation**: MIME type validation against actual content
4. **Bandwidth Limiting**: Rate limiting for large downloads
5. **Asset Caching**: Local caching of frequently accessed assets
6. **Metrics Collection**: Download success/failure metrics
7. **Content Scanning**: Optional malware/virus scanning integration
