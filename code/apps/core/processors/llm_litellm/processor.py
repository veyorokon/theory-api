"""
LLM LiteLLM processor implementation for Modal.

Processes messages with LiteLLM and writes outputs to artifact storage.
"""
import json
import os
import sys
import time
import hashlib
from typing import Any, Dict, List

import litellm


def compute_cid(content: bytes) -> str:
    """Compute content identifier for data."""
    try:
        import blake3
        return 'b3:' + blake3.blake3(content).hexdigest()
    except ImportError:
        return 's256:' + hashlib.sha256(content).hexdigest()


def process(inputs_json: str, write_prefix: str) -> None:
    """
    Process LLM request using LiteLLM and write outputs to /work/out/.
    
    Args:
        inputs_json: JSON string with processor inputs
        write_prefix: Prefix path for writing outputs (unused, outputs go to /work/out/)
    """
    try:
        # Parse inputs
        inputs = json.loads(inputs_json)
        
        # Extract parameters
        messages = inputs.get('messages', [])
        model = inputs.get('model', 'openai/gpt-4o-mini')
        temperature = inputs.get('temperature', 0.7)
        max_tokens = inputs.get('max_tokens', 1000)
        
        # Process any artifact references in messages
        processed_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                # Handle content array format
                if 'content' in msg and isinstance(msg['content'], list):
                    processed_content = []
                    for item in msg['content']:
                        if isinstance(item, dict) and '$artifact' in item:
                            # Convert artifact reference to text placeholder
                            processed_content.append({
                                'type': 'text',
                                'text': f"[Attachment: {item['$artifact']}]"
                            })
                        else:
                            processed_content.append(item)
                    processed_messages.append({
                        'role': msg.get('role', 'user'),
                        'content': processed_content
                    })
                else:
                    processed_messages.append(msg)
            else:
                processed_messages.append(msg)
        
        # Call LiteLLM
        start_time = time.time()
        response = litellm.completion(
            model=model,
            messages=processed_messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        end_time = time.time()
        
        # Extract response text
        response_text = response.choices[0].message.content
        
        # Create output directory
        import os
        os.makedirs('/work/out/text', exist_ok=True)
        
        # Write response text to file
        with open('/work/out/text/response.txt', 'w') as f:
            f.write(response_text)
        
        # Write metadata to file
        metadata = {
            'model': model,
            'tokens_in': response.usage.prompt_tokens if response.usage else 0,
            'tokens_out': response.usage.completion_tokens if response.usage else 0,
            'duration_ms': int((end_time - start_time) * 1000)
        }
        
        with open('/work/out/meta.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
    except Exception as e:
        # Write error to stderr and exit with error code
        import sys
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    """Command-line interface for processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='LLM LiteLLM processor')
    parser.add_argument('--inputs', required=True, help='JSON inputs')
    parser.add_argument('--write-prefix', required=True, help='Write prefix for outputs')
    
    args = parser.parse_args()
    
    # Read inputs from file or use as direct JSON
    inputs_json = args.inputs
    if inputs_json.startswith('/') or inputs_json.startswith('./'):
        # Looks like a file path, read it
        try:
            with open(inputs_json, 'r') as f:
                inputs_json = f.read()
        except Exception as e:
            print(f"Failed to read inputs file: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Process and write files
    process(inputs_json, args.write_prefix)