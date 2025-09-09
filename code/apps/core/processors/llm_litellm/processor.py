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


def process(inputs_json: str, write_prefix: str) -> str:
    """
    Process LLM request using LiteLLM.
    
    Args:
        inputs_json: JSON string with processor inputs
        write_prefix: Prefix path for writing outputs
        
    Returns:
        JSON string with execution result
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
        
        # Prepare outputs
        outputs = {}
        
        # Write response text
        response_path = f"{write_prefix}text/response.txt"
        outputs[response_path] = response_text
        response_cid = compute_cid(response_text.encode('utf-8'))
        
        # Write metadata
        metadata = {
            'model': model,
            'messages_count': len(messages),
            'response_tokens': response.usage.completion_tokens if response.usage else 0,
            'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
            'total_tokens': response.usage.total_tokens if response.usage else 0,
            'duration_seconds': end_time - start_time,
            'timestamp': time.time()
        }
        metadata_json = json.dumps(metadata, indent=2)
        metadata_path = f"{write_prefix}metadata.json"
        outputs[metadata_path] = metadata_json
        metadata_cid = compute_cid(metadata_json.encode('utf-8'))
        
        # Prepare result
        result = {
            'status': 'success',
            'outputs': outputs,
            'seed': int(time.time() * 1000) % 2**32,
            'memo_key': f"llm-{model}-{hash(json.dumps(processed_messages, sort_keys=True))}",
            'env_fingerprint': f"litellm-{litellm.__version__}-{model}",
            'output_cids': [response_cid, metadata_cid],
            'estimate_micro': 1000,
            'actual_micro': int(response.usage.total_tokens * 0.002 * 1000) if response.usage else 500
        }
        
        return json.dumps(result)
        
    except Exception as e:
        # Return error result
        error_result = {
            'status': 'error',
            'error': str(e),
            'outputs': {},
            'seed': 0,
            'memo_key': '',
            'env_fingerprint': 'error',
            'output_cids': [],
            'estimate_micro': 1000,
            'actual_micro': 100
        }
        return json.dumps(error_result)


if __name__ == '__main__':
    """Command-line interface for processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='LLM LiteLLM processor')
    parser.add_argument('--inputs', required=True, help='JSON inputs')
    parser.add_argument('--write-prefix', required=True, help='Write prefix for outputs')
    
    args = parser.parse_args()
    
    # Process and print result
    result = process(args.inputs, args.write_prefix)
    print(result)