#!/usr/bin/env python3
"""
Validate chat message files follow the communication protocol.
Usage: python validate_chat_msgs.py path/to/chat/dir [path/to/another/chat/dir ...]
"""

import sys
import yaml
import re
from pathlib import Path
from datetime import datetime

MESSAGE_PATTERN = re.compile(r'^(\d{3})-to-(engineer|architect|twin)\.md$')
HEADER_PATTERN = re.compile(r'^-- TO (ENGINEER|ARCHITECT|TWIN):')


def validate_front_matter(content):
    """Extract and validate YAML front matter."""
    if not content.startswith('---\n'):
        return None, "Missing YAML front matter"
    
    try:
        end_idx = content.index('\n---\n', 4)
        front_matter = content[4:end_idx]
        data = yaml.safe_load(front_matter)
        
        required = ['from', 'to', 'chat', 'seq', 'ts', 'purpose']
        for field in required:
            if field not in data:
                return None, f"Missing required field: {field}"
        
        # Validate field values
        if data['from'] not in ['architect', 'engineer', 'twin']:
            return None, f"Invalid 'from' value: {data['from']}"
        
        if data['to'] not in ['architect', 'engineer', 'twin']:
            return None, f"Invalid 'to' value: {data['to']}"
        
        if not isinstance(data['seq'], int) or data['seq'] < 1:
            return None, f"Invalid sequence number: {data['seq']}"
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(data['ts'].replace('Z', '+00:00'))
        except:
            return None, f"Invalid timestamp format: {data['ts']}"
        
        return data, None
    
    except ValueError as e:
        return None, f"Invalid YAML: {e}"
    except Exception as e:
        return None, f"Error parsing front matter: {e}"


def validate_message_file(filepath):
    """Validate a single message file."""
    path = Path(filepath)
    filename = path.name
    
    # Check filename pattern
    match = MESSAGE_PATTERN.match(filename)
    if not match:
        return f"❌ {filepath}: Invalid filename pattern (expected: XXX-to-role.md)"
    
    seq_str, target_role = match.groups()
    seq_num = int(seq_str)
    
    try:
        with open(path, 'r') as f:
            content = f.read()
        
        # Validate front matter
        data, error = validate_front_matter(content)
        if error:
            # Legacy messages without front matter are allowed
            if "Missing YAML front matter" in error and seq_num <= 20:
                return f"⚠️  {filepath}: Legacy message (no front matter)"
            return f"❌ {filepath}: {error}"
        
        # Check sequence number matches
        if data and data['seq'] != seq_num:
            return f"❌ {filepath}: Sequence mismatch (file: {seq_num}, front matter: {data['seq']})"
        
        # Check target role matches
        if data and data['to'] != target_role:
            return f"❌ {filepath}: Target role mismatch (file: {target_role}, front matter: {data['to']})"
        
        # Check for header after front matter
        body = content[content.index('\n---\n')+5:] if '---\n' in content else content
        if not HEADER_PATTERN.search(body[:100]):
            return f"❌ {filepath}: Missing or invalid TO <ROLE>: header"
        
        return f"✅ {filepath}"
    
    except Exception as e:
        return f"❌ {filepath}: Error reading file: {e}"


def validate_chat_directory(dirpath):
    """Validate all message files in a chat directory."""
    path = Path(dirpath)
    if not path.is_dir():
        return [f"ERROR: Not a directory: {dirpath}"]
    
    results = []
    message_files = sorted(path.glob('*-to-*.md'))
    
    if not message_files:
        return [f"ℹ️  {dirpath}: No message files found"]
    
    # Check sequence continuity
    sequences = []
    for msg_file in message_files:
        match = MESSAGE_PATTERN.match(msg_file.name)
        if match:
            sequences.append(int(match.group(1)))
    
    if sequences:
        sequences.sort()
        for i, seq in enumerate(sequences):
            if i > 0 and seq != sequences[i-1] + 1:
                results.append(f"⚠️  {dirpath}: Gap in sequence between {sequences[i-1]:03d} and {seq:03d}")
    
    # Validate each message file
    for msg_file in message_files:
        results.append(validate_message_file(msg_file))
    
    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    all_results = []
    for dirpath in sys.argv[1:]:
        print(f"\nValidating: {dirpath}")
        print("-" * 40)
        results = validate_chat_directory(dirpath)
        for result in results:
            print(result)
            if result.startswith("❌"):
                all_results.append(result)
    
    if all_results:
        print(f"\n{len(all_results)} validation error(s) found")
        sys.exit(1)
    else:
        print(f"\n✅ All message files valid across {len(sys.argv)-1} chat(s)")


if __name__ == "__main__":
    main()