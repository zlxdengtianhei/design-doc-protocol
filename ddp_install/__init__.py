"""Install the DDP skills from the self-contained distribution."""

PRODUCT = "design-doc-protocol"
BUSINESS_MODULE = "ddp.cli"
SKILLS = ("design-doc-protocol", "clean-context")
SOURCE_PARENT_LEVEL = 1
SOURCE_SKILL_BASE = "skills"
SOURCE_SCRIPT = ".dsh/skills/design-doc-protocol/scripts/workflow.py"
RUNTIME_SKILLS = ("design-doc-protocol",)
RUNTIME_MODULES = ("ddp",)
