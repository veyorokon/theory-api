import json
import os
import pathlib
from typing import Dict, List, Tuple


def _ensure_dir(p: str):
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)


def write_outputs_and_receipts(
    execution_id: str,
    write_prefix: str,
    meta: Dict,
    outputs: List[Tuple[str, str]],  # [(relpath, text_content)]
) -> Dict:
    # Normalize write_prefix
    if "{execution_id}" in write_prefix:
        write_prefix = write_prefix.replace("{execution_id}", execution_id)
    if not write_prefix.endswith("/"):
        write_prefix += "/"

    out_dir = os.path.join(write_prefix, "outputs")
    _ensure_dir(out_dir)

    # Write payload outputs
    rel_paths = []
    for rel, content in outputs:
        abs_path = os.path.join(out_dir, rel)
        pathlib.Path(os.path.dirname(abs_path)).mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        rel_paths.append(os.path.join(write_prefix, "outputs", rel))

    # Write outputs index
    index_path = os.path.join(write_prefix, "outputs.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"outputs": [{"path": p} for p in rel_paths]}, f, indent=2)

    # Dual receipts (identical)
    receipt = {
        "execution_id": execution_id,
        "index_path": index_path,
        "meta": meta,
    }
    # Local receipt
    with open(os.path.join(write_prefix, "receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    # Global determinism receipt
    global_det = os.path.join("/artifacts/execution", execution_id, "determinism.json")
    pathlib.Path(os.path.dirname(global_det)).mkdir(parents=True, exist_ok=True)
    with open(global_det, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return {
        "status": "success",
        "execution_id": execution_id,
        "outputs": [{"path": p} for p in rel_paths],
        "index_path": index_path,
        "meta": meta,
    }
