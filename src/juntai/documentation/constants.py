"""Versioned public constants owned by this foundation."""

PACKAGE_VERSION = "1.0.0"
SCHEMA_VERSION = "1"
MANIFEST_API_VERSION = "capability.juntai.io/v1"
MANIFEST_KIND = "AgentCapabilityBundle"
LAYOUT_PROFILE = "juntai.documentation.standard/v1"
FUSE_API_VERSION = "2.0.0"
FUSE_DESCRIPTOR_VERSION = "juntai.fuse/mcp-descriptor/v1"
FUSE_MCP_PROFILE = "juntai.fuse.profile.mcp/v1"

MEDIA_TYPES = {
    "bundle": "application/vnd.juntai.capability-bundle.v1+tar",
    "agent_bundle": "application/vnd.juntai.agent-capability-bundle.v1+tar",
    "human": "application/vnd.juntai.documentation-human.v1+tar",
    "mcp": "application/vnd.juntai.documentation-mcp.v1+json",
    "catalog": "application/vnd.juntai.documentation-catalog.v1+json",
    "provenance": "application/vnd.juntai.capability-provenance.v1+json",
}
