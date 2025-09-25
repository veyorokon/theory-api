"""
Django management command to export documentation from code.
Generates Mermaid diagrams, API documentation, and schemas.
"""

import json
import yaml
import inspect
from pathlib import Path
from typing import Dict, Any

from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models


class Command(BaseCommand):
    help = "Export documentation from Django models and code"

    def add_arguments(self, parser):
        parser.add_argument("--out", type=str, required=True, help="Output directory for generated documentation")
        parser.add_argument("--erd", action="store_true", help="Generate ERD (Entity Relationship Diagram) from models")
        parser.add_argument(
            "--api", action="store_true", help="Generate API documentation from interfaces and services"
        )
        parser.add_argument("--schemas", action="store_true", help="Export JSON schemas")
        parser.add_argument("--registry", action="store_true", help="Export processor registry documentation")

    def handle(self, *args, **options):
        output_dir = Path(options["out"])
        output_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.SUCCESS(f"Output directory: {output_dir}"))

        if options["erd"]:
            self.generate_erd(output_dir)

        if options["api"]:
            self.generate_api_docs(output_dir)

        if options["schemas"]:
            self.generate_schemas(output_dir)

        if options["registry"]:
            self.generate_registry(output_dir)

        # Generate placeholder content for hybrid pages
        self.generate_placeholders(output_dir)

        self.stdout.write(self.style.SUCCESS("Documentation export completed!"))

    def generate_erd(self, output_dir: Path):
        """Generate Entity Relationship Diagram using Mermaid"""
        self.stdout.write("Generating ERD...")

        mermaid_erd = ["erDiagram"]

        # Get all models from installed apps
        for app_config in apps.get_app_configs():
            if app_config.path and "apps" in app_config.path:
                app_models = app_config.get_models()

                for model in app_models:
                    model_name = model.__name__

                    # Add model with its fields
                    mermaid_erd.append(f"    {model_name} {{")

                    for field in model._meta.fields:
                        field_type = self._get_mermaid_field_type(field)
                        field_name = field.name
                        field_constraint = "PK" if field.primary_key else ""

                        if field.null:
                            field_constraint = "NULL"
                        elif field.unique and not field.primary_key:
                            field_constraint = "UK"

                        mermaid_erd.append(f"        {field_type} {field_name} {field_constraint}".strip())

                    mermaid_erd.append("    }")

                    # Add relationships
                    for field in model._meta.fields:
                        if isinstance(field, models.ForeignKey):
                            related_model = field.related_model.__name__
                            relationship = "||--o{" if field.null else "||--|{"
                            mermaid_erd.append(f"    {model_name} {relationship} {related_model} : {field.name}")

        # Write ERD to file
        erd_file = output_dir / "erd.mmd"
        with open(erd_file, "w") as f:
            f.write("\n".join(mermaid_erd))

        self.stdout.write(self.style.SUCCESS(f"ERD generated: {erd_file}"))

    def _get_mermaid_field_type(self, field) -> str:
        """Map Django field types to Mermaid ERD types"""
        type_mapping = {
            "CharField": "string",
            "TextField": "text",
            "IntegerField": "int",
            "BigIntegerField": "bigint",
            "FloatField": "float",
            "DecimalField": "decimal",
            "BooleanField": "boolean",
            "DateTimeField": "datetime",
            "DateField": "date",
            "TimeField": "time",
            "UUIDField": "uuid",
            "EmailField": "email",
            "URLField": "url",
            "JSONField": "json",
            "ForeignKey": "fk",
            "OneToOneField": "fk",
            "ManyToManyField": "m2m",
        }

        field_class = field.__class__.__name__
        return type_mapping.get(field_class, "string")

    def generate_api_docs(self, output_dir: Path):
        """Generate API documentation from storage interfaces and services"""
        self.stdout.write("Generating API documentation...")

        # Document storage interfaces
        storage_docs = []

        try:
            from apps.storage import interfaces

            # Document StorageInterface
            storage_docs.append("# Storage API Documentation\n")
            storage_docs.append("## Architecture Diagram\n")
            storage_docs.append("```{mermaid}")
            storage_docs.append(self._generate_storage_architecture_diagram())
            storage_docs.append("```\n")

            # Document interface
            storage_docs.append("## StorageInterface\n")
            storage_docs.append("Abstract base class for storage adapters.\n")
            storage_docs.append("### Methods\n")

            for name, method in inspect.getmembers(interfaces.StorageInterface, predicate=inspect.isfunction):
                if not name.startswith("_"):
                    sig = inspect.signature(method)
                    doc = inspect.getdoc(method) or "No documentation"
                    storage_docs.append(f"#### `{name}{sig}`\n")
                    storage_docs.append(f"{doc}\n")

            # Document service
            storage_docs.append("\n## StorageService\n")
            storage_docs.append("Vendor-neutral storage service (Singleton pattern).\n")
            storage_docs.append("```python")
            storage_docs.append("from apps.storage.service import storage_service")
            storage_docs.append("# Automatically uses MinIO in dev, S3 in prod")
            storage_docs.append("url = storage_service.upload_file(file, key, bucket)")
            storage_docs.append("```\n")

            # Document adapters
            storage_docs.append("\n## Adapters\n")
            storage_docs.append("### MinIOAdapter\n")
            storage_docs.append("Local development storage using MinIO.\n")
            storage_docs.append("### S3Adapter\n")
            storage_docs.append("Production storage using AWS S3.\n")

        except ImportError as e:
            storage_docs.append(f"Error importing storage modules: {e}\n")

        # Write API documentation
        api_file = output_dir / "storage_api.md"
        with open(api_file, "w") as f:
            f.write("\n".join(storage_docs))

        self.stdout.write(self.style.SUCCESS(f"API docs generated: {api_file}"))

    def _generate_storage_architecture_diagram(self) -> str:
        """Generate Mermaid diagram for storage architecture"""
        return """graph TD
    Client[Client Code]
    Service[StorageService<br/>Singleton]
    Interface[StorageInterface<br/>ABC]
    MinIO[MinIOAdapter]
    S3[S3Adapter]
    Backend[Django Storage Backend]

    Client --> Service
    Backend --> Service
    Service --> Interface
    Interface <|-- MinIO
    Interface <|-- S3

    Service -.->|Development| MinIO
    Service -.->|Production| S3

    style Interface fill:#f9f,stroke:#333,stroke-width:2px
    style Service fill:#bbf,stroke:#333,stroke-width:2px"""

    def generate_schemas(self, output_dir: Path):
        """Generate JSON schemas for models and interfaces"""
        self.stdout.write("Generating JSON schemas...")

        schemas = {}

        # Generate schemas for each model
        for app_config in apps.get_app_configs():
            if app_config.path and "apps" in app_config.path:
                app_name = app_config.name.split(".")[-1]
                app_models = app_config.get_models()

                for model in app_models:
                    schema = self._model_to_json_schema(model)
                    schemas[f"{app_name}.{model.__name__}"] = schema

        # Write schemas
        schema_file = output_dir / "schemas.json"
        with open(schema_file, "w") as f:
            json.dump(schemas, f, indent=2, default=str)

        self.stdout.write(self.style.SUCCESS(f"Schemas generated: {schema_file}"))

    def _model_to_json_schema(self, model) -> Dict[str, Any]:
        """Convert Django model to JSON schema"""
        schema = {
            "type": "object",
            "title": model.__name__,
            "description": model.__doc__ or f"{model.__name__} model",
            "properties": {},
            "required": [],
        }

        for field in model._meta.fields:
            field_schema = self._field_to_json_schema(field)
            schema["properties"][field.name] = field_schema

            if not field.null and not field.blank:
                schema["required"].append(field.name)

        return schema

    def _field_to_json_schema(self, field) -> Dict[str, Any]:
        """Convert Django field to JSON schema property"""
        type_mapping = {
            "CharField": "string",
            "TextField": "string",
            "IntegerField": "integer",
            "BigIntegerField": "integer",
            "FloatField": "number",
            "DecimalField": "number",
            "BooleanField": "boolean",
            "DateTimeField": "string",
            "DateField": "string",
            "TimeField": "string",
            "UUIDField": "string",
            "EmailField": "string",
            "URLField": "string",
            "JSONField": "object",
        }

        field_class = field.__class__.__name__
        json_type = type_mapping.get(field_class, "string")

        schema = {"type": json_type, "description": field.help_text or f"{field.verbose_name}"}

        if hasattr(field, "max_length") and field.max_length:
            schema["maxLength"] = field.max_length

        if field_class in ["DateTimeField", "DateField", "TimeField"]:
            schema["format"] = {"DateTimeField": "date-time", "DateField": "date", "TimeField": "time"}[field_class]
        elif field_class == "EmailField":
            schema["format"] = "email"
        elif field_class == "URLField":
            schema["format"] = "uri"
        elif field_class == "UUIDField":
            schema["format"] = "uuid"

        return schema

    def generate_registry(self, output_dir: Path):
        """Generate processor registry documentation"""
        self.stdout.write("Generating processor registry...")

        registry_dir = Path("apps/core/registry/processors")
        registry_docs = []

        registry_docs.append("# Processor Registry\n")
        registry_docs.append("Auto-generated processor registry documentation.\n\n")

        if registry_dir.exists():
            for yaml_file in registry_dir.glob("*.yaml"):
                try:
                    with open(yaml_file) as f:
                        processor = yaml.safe_load(f)

                    # Document processor
                    registry_docs.append(f"## {processor.get('ref', 'Unknown')}\n")
                    registry_docs.append(f"{processor.get('description', 'No description')}\n\n")

                    # Image configuration
                    if "image" in processor:
                        registry_docs.append("### Image\n")
                        image = processor["image"]
                        if "oci" in image:
                            registry_docs.append(f"- **OCI**: `{image['oci']}`\n")
                        if "dockerfile" in image:
                            registry_docs.append(f"- **Dockerfile**: `{image['dockerfile']}`\n")
                        registry_docs.append("\n")

                    # Runtime configuration
                    if "runtime" in processor:
                        registry_docs.append("### Runtime\n")
                        runtime = processor["runtime"]
                        registry_docs.append(f"- **CPU**: {runtime.get('cpu', 'default')}\n")
                        registry_docs.append(f"- **Memory**: {runtime.get('memory', 'default')} MB\n")
                        registry_docs.append(f"- **Timeout**: {runtime.get('timeout', 300)} seconds\n")
                        if "gpu" in runtime:
                            registry_docs.append(f"- **GPU**: {runtime['gpu']}\n")
                        registry_docs.append("\n")

                    # Adapter configuration
                    if "adapter" in processor:
                        registry_docs.append("### Adapter Configuration\n")
                        if "modal" in processor["adapter"]:
                            modal = processor["adapter"]["modal"]
                            registry_docs.append("#### Modal\n")
                            registry_docs.append(f"- **Stub Name**: `{modal.get('stub_name', 'default')}`\n")
                            registry_docs.append(f"- **Function**: `{modal.get('function_name', 'process')}`\n")
                        registry_docs.append("\n")

                    # Secrets
                    if "secrets" in processor:
                        registry_docs.append("### Required Secrets\n")
                        for secret in processor["secrets"]:
                            registry_docs.append(f"- `{secret}`\n")
                        registry_docs.append("\n")

                    # Outputs
                    if "outputs" in processor:
                        registry_docs.append("### Outputs\n")
                        for output in processor["outputs"]:
                            registry_docs.append(
                                f"- **{output['path']}**: {output.get('description', 'No description')} ({output.get('mime', 'unknown')})\n"
                            )
                        registry_docs.append("\n")

                    registry_docs.append("---\n\n")

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Error processing {yaml_file}: {e}"))

        # Write registry documentation
        registry_file = output_dir / "registry" / "processors.md"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_file, "w") as f:
            f.write("".join(registry_docs))

        self.stdout.write(self.style.SUCCESS(f"Processor registry generated: {registry_file}"))

    def generate_predicate_registry(self, registry_dir: Path):
        """Generate predicate registry documentation"""
        self.stdout.write("Generating predicate registry...")

        try:
            from apps.core.predicates import PREDICATE_REGISTRY

            # Convert registry to JSON-serializable format
            registry_data = {}
            for name, entry in PREDICATE_REGISTRY.items():
                registry_data[name] = {
                    "params": entry["params"],
                    "returns": entry["returns"],
                    "description": entry["description"],
                }

            # Write predicate registry
            registry_file = registry_dir / "predicates.json"
            with open(registry_file, "w") as f:
                json.dump(registry_data, f, indent=2)

            self.stdout.write(self.style.SUCCESS(f"Predicate registry generated: {registry_file}"))

        except ImportError as e:
            self.stdout.write(self.style.WARNING(f"Could not import predicates: {e}"))

    def generate_placeholders(self, output_dir: Path):
        """Generate placeholder content for hybrid page includes"""
        self.stdout.write("Generating placeholders...")

        # Create subdirectories
        (output_dir / "registry").mkdir(exist_ok=True)
        (output_dir / "examples").mkdir(exist_ok=True)
        (output_dir / "diagrams").mkdir(exist_ok=True)

        # Generate predicate registry
        self.generate_predicate_registry(output_dir / "registry")

        # Registry placeholder
        registry_index = output_dir / "registry" / "index.md"
        with open(registry_index, "w") as f:
            f.write("# Registry Documentation\n\n")
            f.write("## Predicates\n\n")
            f.write("The predicate registry is available as `predicates.json` in this directory.\n\n")
            f.write("## Tool Specifications\n\n")
            f.write("Coming soon: Auto-generated documentation for all registered tools.\n\n")
            f.write("## Schema Definitions\n\n")
            f.write("Coming soon: JSON schemas for all data structures.\n\n")
            f.write("## Policy Documents\n\n")
            f.write("Coming soon: Budget policies and execution constraints.\n")

        # Use case examples
        examples = [
            ("media-dag.md", "Media Generation Pipeline", "Script → Shots → Frames → Video"),
            ("cicd-dag.md", "CI/CD Pipeline", "Clone → Test → Build → Deploy → Verify"),
            ("realtime-sequence.md", "Real-time Agent Sequence", "Audio/Video processing pipeline"),
        ]

        for filename, title, description in examples:
            example_file = output_dir / "examples" / filename
            with open(example_file, "w") as f:
                f.write(f"# {title}\n\n")
                f.write(f"*{description}*\n\n")
                f.write("```{mermaid}\n")
                f.write("graph LR\n")
                f.write("    A[Start] --> B[Process]\n")
                f.write("    B --> C[Complete]\n")
                f.write("    style A fill:#e1f5fe\n")
                f.write("    style C fill:#e8f5e8\n")
                f.write("```\n\n")
                f.write("*Detailed workflow diagram will be generated when the system is implemented.*\n")

        self.stdout.write(self.style.SUCCESS("Placeholders generated"))
