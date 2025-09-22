"""
Base class for Modal management commands.
"""

from django.core.management.base import BaseCommand, CommandError

from ._modal_common import compute_modal_context, ModalContext


class ModalCommand(BaseCommand):
    """
    Base class for Modal-related management commands.

    Automatically:
    - Adds --ref argument (required)
    - Computes Modal context with proper naming
    - Provides get_ctx() helper
    """

    requires_system_checks = []  # Disable Django system checks for speed

    def add_arguments(self, parser):
        """Add common arguments for Modal commands."""
        parser.add_argument("--ref", required=True, help="Processor reference (e.g., llm/litellm@1)")
        # Let subclasses add their own arguments
        self.add_modal_arguments(parser)

    def add_modal_arguments(self, parser):
        """Override in subclasses to add command-specific arguments."""
        pass

    def get_ctx(self, options) -> ModalContext:
        """
        Get Modal context from options.

        Args:
            options: Command options dict

        Returns:
            ModalContext with resolved app name and environment info

        Raises:
            CommandError: If --ref is missing
        """
        ref = options.get("ref")
        if not ref:
            raise CommandError("Missing required --ref argument")

        return compute_modal_context(processor_ref=ref)

    def handle(self, *args, **options):
        """Override in subclasses."""
        raise NotImplementedError("Subclasses must implement handle()")
