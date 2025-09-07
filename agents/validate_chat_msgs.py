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
        
        # Handle both integer and string sequence numbers
        seq = data['seq']
        if isinstance(seq, str):
            try:
                seq = int(seq)
            except ValueError:
                return None, f"Invalid sequence number: {data['seq']}"
        if not isinstance(seq, int) or seq < 1:
            return None, f"Invalid sequence number: {data['seq']}"
        
        # Validate timestamp format (allow various legacy formats)
        try:
            ts = str(data['ts'])
            # Try various common timestamp formats
            if ts.endswith('Z'):
                # ISO with Z suffix
                datetime.fromisoformat(ts.replace('Z', '+00:00'))
            elif '+' in ts or ts.endswith('00:00'):
                # ISO with timezone
                datetime.fromisoformat(ts)
            elif 'T' in ts:
                # ISO format without timezone
                datetime.fromisoformat(ts)
            else:
                # Try parsing as basic date/time
                datetime.fromisoformat(ts)
        except Exception as e:
            # For legacy messages, be more lenient with timestamps
            return None, f"Legacy timestamp format: {data['ts']}"
        
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
            # Legacy messages without front matter are allowed for older chats
            if "Missing YAML front matter" in error and seq_num <= 50:
                # For legacy messages, just mark as legacy without strict validation
                return f"⚠️  {filepath}: Legacy message (no front matter)"
            # Handle legacy timestamp formats as warnings for older messages
            elif "timestamp format" in error.lower() and seq_num <= 50:
                return f"⚠️  {filepath}: Legacy message ({error})"
            return f"❌ {filepath}: {error}"
        
        # For messages with front matter, validate strictly
        # Check sequence number matches (handle both int and string)
        if data:
            front_matter_seq = data['seq']
            if isinstance(front_matter_seq, str):
                try:
                    front_matter_seq = int(front_matter_seq)
                except ValueError:
                    pass
            if front_matter_seq != seq_num:
                return f"❌ {filepath}: Sequence mismatch (file: {seq_num}, front matter: {data['seq']})"
        
        # Check target role matches
        if data and data['to'] != target_role:
            return f"❌ {filepath}: Target role mismatch (file: {target_role}, front matter: {data['to']})"
        
        # Check for header after front matter
        body = content[content.index('\n---\n')+5:] if '---\n' in content else content
        if not HEADER_PATTERN.search(body[:100]):
            # For older messages, treat missing header as legacy format
            if seq_num <= 50:
                return f"⚠️  {filepath}: Legacy message format (missing TO <ROLE>: header)"
            else:
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
    
    errors = []
    warnings = []
    
    for dirpath in sys.argv[1:]:
        print(f"\nValidating: {dirpath}")
        print("-" * 40)
        results = validate_chat_directory(dirpath)
        for result in results:
            print(result)
            if result.startswith("❌"):
                errors.append(result)
            elif result.startswith("⚠️"):
                warnings.append(result)
    
    if warnings:
        print(f"\n⚠️  {len(warnings)} legacy message(s) found (non-fatal)")
    
    if errors:
        print(f"\n❌ {len(errors)} validation error(s) found")
        sys.exit(1)
    else:
        total_chats = len(sys.argv) - 1
        print(f"\n✅ All message files valid across {total_chats} chat(s)")


if __name__ == "__main__":
    main()