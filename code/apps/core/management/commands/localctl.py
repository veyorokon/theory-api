from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.utils import run_utils
from apps.core.management.utils import capture_stdout
from backend.middleware import logging as core_logging
from libs.runtime_common.envelope import resolve_mode, ModeSafetyError


# Port state file location
PORT_STATE_FILE = Path(__file__).parent.parent.parent.parent.parent / ".theory" / "local_ports.json"


def _container_name(ref: str, image_ref: str) -> str:
    """Generate stable container name matching LocalWsAdapter logic."""
    slug = re.sub(r"[^a-z0-9\-]+", "-", ref.replace("/", "-").lower())
    h = hashlib.sha1(image_ref.encode()).hexdigest()[:8]
    return f"theory-proc-{slug}-{h}"


def _load_port_state() -> Dict[str, int]:
    """Load port state from file."""
    if not PORT_STATE_FILE.exists():
        return {}
    try:
        with open(PORT_STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_port_state(state: Dict[str, int]) -> None:
    """Save port state to file."""
    PORT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PORT_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _port_in_use(port: int) -> bool:
    """Check if port is currently in use on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def _allocate_port(ref: str, override: int | None = None) -> int:
    """
    Allocate host port for tool ref.

    - If override provided: use it and save to state
    - If ref exists in state: reuse existing port (idempotent)
    - Else: find next available port >= 40000, save to state
    """
    if override:
        state = _load_port_state()
        state[ref] = override
        _save_port_state(state)
        return override

    state = _load_port_state()

    # Reuse existing allocation
    if ref in state:
        return state[ref]

    # Find next available port >= 40000
    used_ports = set(state.values())
    port = 40000
    while port in used_ports or _port_in_use(port):
        port += 1

    # Save allocation
    state[ref] = port
    _save_port_state(state)
    return port


def _extract_host_port(ports_str: str) -> int | None:
    """Extract host port from Docker ports string."""
    # "0.0.0.0:40000->8000/tcp, [::]:40000->8000/tcp" → 40000
    match = re.search(r":(\d+)->", ports_str)
    return int(match.group(1)) if match else None


def _get_newest_build_tag(ref: str) -> str:
    """Get latest local build tag for ref."""
    from apps.core.utils.adapters import _get_newest_build_tag

    return _get_newest_build_tag(ref)


def _find_containers(ref: str | None = None, all_theory: bool = False) -> List[Dict[str, str]]:
    """
    Find running containers.

    Args:
        ref: Filter by specific processor ref (uses label)
        all_theory: Find all theory-local containers (labeled or orphaned)

    Returns:
        List of dicts with keys: container_id, name, status, ports, ref
    """
    if ref:
        # Filter by specific ref label
        cmd = [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.theory.ref={ref}",
            "--format",
            '{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}|{{.Label "com.theory.ref"}}',
        ]
    elif all_theory:
        # Find ALL theory containers: labeled + name pattern + image ancestor
        # Use docker ps with multiple filters isn't OR, so run separately and dedupe
        results = []

        # 1. Labeled containers
        r1 = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "label=com.theory.ref",
                "--format",
                '{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}|{{.Label "com.theory.ref"}}',
            ],
            capture_output=True,
            text=True,
        )
        results.append(r1.stdout)

        # 2. Containers by name pattern (theory-proc-*)
        r2 = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=theory-proc-",
                "--format",
                '{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}|{{.Label "com.theory.ref"}}',
            ],
            capture_output=True,
            text=True,
        )
        results.append(r2.stdout)

        # 3. Find all theory-local image patterns (llm-litellm, replicate-generic, etc.)
        # Get unique images from actual containers (not from docker images which has duplicates)
        images_result = subprocess.run(["docker", "ps", "-a", "--format", "{{.Image}}"], capture_output=True, text=True)
        all_images = images_result.stdout.strip().split("\n")
        unique_images = {img for img in all_images if img.startswith("theory-local/")}

        for image in unique_images:
            if image:
                r = subprocess.run(
                    [
                        "docker",
                        "ps",
                        "-a",
                        "--filter",
                        f"ancestor={image}",
                        "--format",
                        '{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}|{{.Label "com.theory.ref"}}',
                    ],
                    capture_output=True,
                    text=True,
                )
                results.append(r.stdout)

        # Combine and dedupe by container ID
        seen = set()
        containers = []
        for output in results:
            for line in output.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|")
                if len(parts) >= 4:
                    cid = parts[0]
                    if cid not in seen:
                        seen.add(cid)
                        ports_str = parts[3] if len(parts) > 3 else ""
                        containers.append(
                            {
                                "container_id": parts[0],
                                "name": parts[1],
                                "status": parts[2],
                                "port": _extract_host_port(ports_str),
                                "ref": parts[4] if len(parts) > 4 else "",
                            }
                        )
        return containers
    else:
        cmd = [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=com.theory.ref",
            "--format",
            '{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}|{{.Label "com.theory.ref"}}',
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            ports_str = parts[3] if len(parts) > 3 else ""
            containers.append(
                {
                    "container_id": parts[0],
                    "name": parts[1],
                    "status": parts[2],
                    "port": _extract_host_port(ports_str),
                    "ref": parts[4] if len(parts) > 4 else "",
                }
            )

    return containers


@capture_stdout
def cmd_start(args: argparse.Namespace) -> dict:
    """Start reusable container for tool ref."""
    ref = args.ref
    platform = args.platform
    if not ref:
        raise CommandError("--ref is required")
    if not platform:
        raise CommandError("--platform is required")

    # Get image tag for platform
    try:
        from apps.core.management.commands.imagectl import _read_build_manifest, _normalize_platform

        platform = _normalize_platform(platform)
        manifest = _read_build_manifest(ref)
        image_ref = manifest.get("tags", {}).get(platform)
        if not image_ref:
            raise RuntimeError(f"No build found for platform {platform}")
    except Exception as e:
        raise CommandError(f"Could not find built image for {ref} platform {platform}: {e}")

    # Generate container name and allocate port
    container_name = _container_name(ref, image_ref)
    port = _allocate_port(ref, override=getattr(args, "port", None))

    # Check if already running
    existing = _find_containers(ref=ref)
    if existing:
        container = existing[0]
        if "Up" in container["status"]:
            return {
                "status": "success",
                "note": "already_running",
                "container": container["name"],
                "port": port,
                "ref": ref,
            }
        else:
            # Remove stopped container
            subprocess.run(["docker", "rm", "-f", container["container_id"]], capture_output=True)

    # Start container
    import os

    uid = os.getuid() if hasattr(os, "getuid") else 1000
    gid = os.getgid() if hasattr(os, "getgid") else 1000
    mount_dir = os.getcwd()

    # Get image digest from docker inspect
    try:
        inspect_result = subprocess.run(
            ["docker", "image", "inspect", "--format={{.Id}}", image_ref],
            capture_output=True,
            text=True,
            check=True,
        )
        image_digest = inspect_result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise CommandError(f"Failed to inspect image {image_ref}: {e.stderr}")

    # Resolve required secrets from registry
    from apps.core.registry.loader import load_processor_spec
    from apps.core.utils.secret_resolver import resolve_secret

    try:
        spec = load_processor_spec(ref)
        required_secrets = (spec.get("secrets") or {}).get("required", [])
    except Exception:
        required_secrets = []

    docker_cmd = [
        "docker",
        "run",
        "--detach",
        "--name",
        container_name,
        "--label",
        f"com.theory.ref={ref}",
        "--user",
        f"{uid}:{gid}",
        "--network",
        "theory_api_app_network",
        "--add-host",
        "minio.local:host-gateway",
        "-e",
        f"IMAGE_DIGEST={image_digest}",
        "-e",
        "HOME=/home/app",
        "-e",
        "TZ=UTC",
        "-e",
        "LC_ALL=C.UTF-8",
    ]

    # Inject required secrets from environment (fail fast if missing)
    for secret_name in required_secrets:
        secret_value = resolve_secret(secret_name)
        if not secret_value:
            raise CommandError(
                f"Missing required secret: {secret_name}. "
                f"Set {secret_name} in your environment before starting the container."
            )
        docker_cmd.extend(["-e", f"{secret_name}={secret_value}"])

    docker_cmd.extend(
        [
            "-p",
            f"{port}:8000",
            "-v",
            f"{mount_dir}:/world",
            image_ref,
        ]
    )

    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CommandError(f"Failed to start container: {result.stderr}")

    return {
        "status": "success",
        "container": container_name,
        "container_id": result.stdout.strip(),
        "port": port,
        "ref": ref,
        "image": image_ref,
    }


@capture_stdout
def cmd_stop(args: argparse.Namespace) -> dict:
    """Stop containers by ref or all theory containers."""
    if args.all:
        containers = _find_containers(all_theory=True)
    elif args.ref:
        containers = _find_containers(ref=args.ref)
    else:
        raise CommandError("Either --ref or --all is required")

    if not containers:
        return {"status": "success", "note": "no_containers_found", "stopped": []}

    stopped = []
    stopped_refs = []
    for c in containers:
        result = subprocess.run(["docker", "rm", "-f", c["container_id"]], capture_output=True, text=True)
        if result.returncode == 0:
            stopped.append(c["name"])
            if c.get("ref"):
                stopped_refs.append(c["ref"])

    # Remove port allocations for stopped containers
    if stopped_refs:
        state = _load_port_state()
        for ref in stopped_refs:
            state.pop(ref, None)
        _save_port_state(state)

    return {
        "status": "success",
        "stopped": stopped,
        "count": len(stopped),
    }


@capture_stdout
def cmd_status(args: argparse.Namespace) -> dict:
    """Show running containers."""
    if args.ref:
        containers = _find_containers(ref=args.ref)
    else:
        containers = _find_containers(all_theory=True)

    return {
        "status": "success",
        "containers": containers,
        "count": len(containers),
    }


@capture_stdout
def cmd_url(args: argparse.Namespace) -> dict:
    """Get URL for tool ref."""
    ref = args.ref
    if not ref:
        raise CommandError("--ref is required")

    state = _load_port_state()
    port = state.get(ref)

    if not port:
        raise CommandError(f"No port allocated for {ref}")

    url = f"http://127.0.0.1:{port}"
    return {"ref": ref, "port": port, "url": url}


def cmd_logs(args: argparse.Namespace, stdout=None) -> None:
    """Show container logs."""
    ref = args.ref
    if not ref:
        raise CommandError("--ref is required")

    containers = _find_containers(ref=ref)
    if not containers:
        raise CommandError(f"No running container found for {ref}")

    container_name = containers[0]["name"]

    cmd = ["docker", "logs", container_name]
    if args.follow:
        cmd.append("--follow")
    if args.tail:
        cmd.extend(["--tail", str(args.tail)])

    proc = subprocess.Popen(cmd)
    proc.wait()
    if proc.returncode != 0:
        raise CommandError(f"docker logs failed with rc={proc.returncode}")


def cmd_run(args: argparse.Namespace, stdout=None) -> None:
    """Run tool with local adapter."""
    # Support both run_id and execution_id during transition
    run_id = str(uuid.uuid4())

    if args.json:
        os.environ["LOG_STREAM"] = "stderr"

    # Bind logging context
    core_logging.bind(
        trace_id=run_id,
        tool_ref=args.ref,
        adapter="local",
        mode=args.mode or "mock",
    )

    try:
        # Require {run_id} in write prefix (support both forms during transition)
        write_prefix = args.write_prefix
        if write_prefix and "{run_id}" not in write_prefix and "{execution_id}" not in write_prefix:
            raise CommandError("--write-prefix must include '{run_id}' to prevent output collisions")

        # Parse inputs
        inputs_json = run_utils.parse_inputs(vars(args))

        # Inject mode
        if args.mode:
            inputs_json["mode"] = args.mode
        elif os.environ.get("CI") == "true" and "mode" not in inputs_json:
            inputs_json["mode"] = "mock"

        # Validate mode
        try:
            resolve_mode(args.mode)
        except ModeSafetyError as e:
            core_logging.error(
                "execution.fail",
                error={"code": "ERR_CI_SAFETY", "message": e.message},
                reason="ci_guardrail_block",
                ci=True,
                mode="real",
            )
            sys.stderr.write(f"Error: {e.message}\n")
            sys.exit(1)
        except Exception as e:
            core_logging.error("execution.fail", error={"code": "ERR_MODE_INVALID", "message": str(e)})
            sys.stderr.write(f"Error: {e}\n")
            sys.exit(1)

        # Materialize attachments
        attachment_map = {}
        if args.attach:
            try:
                attachment_map = run_utils.materialize_attachments(args.attach)
                if not args.json:
                    for name, info in attachment_map.items():
                        sys.stdout.write(f"Materialized {name} -> {info.get('$artifact')} ({info.get('cid')})\n")
            except (ValueError, FileNotFoundError) as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.exit(1)

        # Rewrite $attach references
        if attachment_map:
            try:
                inputs_json = run_utils.rewrite_attach_references(inputs_json, attachment_map)
            except ValueError as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.exit(1)

        # Invoke processor with local adapter
        from apps.core.tool_runner import ToolRunner

        runner = ToolRunner()
        result = runner.invoke(
            ref=args.ref,
            mode=args.mode,
            inputs=inputs_json,
            stream=False,
            timeout_s=args.timeout or 600,
            run_id=run_id,
            write_prefix=write_prefix,
            adapter="local",
            artifact_scope="local",
        )

        # Download outputs if requested
        if result.get("status") == "success" and result.get("outputs"):
            try:
                if args.save_dir:
                    run_utils.download_all_outputs(result["outputs"], args.save_dir)
                    if not args.json:
                        sys.stdout.write(f"Downloaded outputs to {args.save_dir}\n")
                elif args.save_first:
                    run_utils.download_first_output(result["outputs"], args.save_first)
                    if not args.json:
                        sys.stdout.write(f"Downloaded first output to {args.save_first}\n")
            except Exception as e:
                sys.stderr.write(f"Error downloading outputs: {e}\n")

        # Output JSON
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")

    finally:
        core_logging.clear()


class Command(BaseCommand):
    help = "Local container control: start, stop, status, logs, run."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="subcmd", required=True)

        # start
        p_start = sub.add_parser("start", help="Start reusable container for tool")
        p_start.add_argument("--ref", required=True, help="Tool ref: ns/name@ver")
        p_start.add_argument("--platform", required=True, help="Platform (amd64 or arm64)")
        p_start.add_argument("--port", type=int, help="Override host port (default: auto-assign from 40000+)")
        p_start.set_defaults(func=cmd_start)

        # stop
        p_stop = sub.add_parser("stop", help="Stop containers")
        p_stop.add_argument("--ref", help="Stop container for specific ref")
        p_stop.add_argument("--all", action="store_true", help="Stop all theory containers")
        p_stop.set_defaults(func=cmd_stop)

        # status
        p_status = sub.add_parser("status", help="Show running containers")
        p_status.add_argument("--ref", help="Filter by specific ref")
        p_status.set_defaults(func=cmd_status)

        # url
        p_url = sub.add_parser("url", help="Get URL for tool ref")
        p_url.add_argument("--ref", required=True, help="Tool ref")
        p_url.set_defaults(func=cmd_url)

        # logs
        p_logs = sub.add_parser("logs", help="Show container logs")
        p_logs.add_argument("--ref", required=True, help="Tool ref")
        p_logs.add_argument("--follow", "-f", action="store_true", help="Follow log output")
        p_logs.add_argument("--tail", type=int, help="Number of lines to show from end")
        p_logs.set_defaults(func=cmd_logs)

        # run
        p_run = sub.add_parser("run", help="Run tool with local adapter")
        p_run.add_argument("--ref", required=True, help="Tool ref (e.g., llm/litellm@1)")
        p_run.add_argument("--mode", choices=["real", "mock"], help="Tool mode")
        p_run.add_argument("--write-prefix", help="Write prefix for outputs (must include {run_id})")
        p_run.add_argument("--timeout", type=int, help="Timeout in seconds (default: 600)")
        p_run.add_argument("--json", action="store_true", help="Output JSON response")

        # Input options (mutually exclusive)
        inputs_group = p_run.add_mutually_exclusive_group()
        inputs_group.add_argument("--inputs-json", help="JSON input (no escaping required)")
        inputs_group.add_argument("--inputs-file", help="Read JSON input from file")
        inputs_group.add_argument("--inputs", help="Read JSON from stdin (use '-')")
        inputs_group.add_argument("--inputs-jsonstr", default="{}", help="JSON input as string (legacy)")

        # Attachment and output options
        p_run.add_argument("--attach", action="append", help="Attach file as name=path (can be used multiple times)")
        p_run.add_argument("--save-dir", help="Download all outputs into this directory")
        p_run.add_argument("--save-first", help="Download only the first output into this file")
        p_run.set_defaults(func=cmd_run)

    def handle(self, *args, **options):
        func = options.get("func")
        if not func:
            raise CommandError("No subcommand specified")
        func(argparse.Namespace(**options), stdout=self.stdout)
