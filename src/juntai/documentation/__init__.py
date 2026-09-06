"""Service-free Juntai Documentation Capability Bundle foundation."""

from .catalog import compile_catalog, select_capability, verify_catalog_signature
from .descriptor import validate_fuseapi_descriptor
from .feedback import (
    CapabilityFeedbackHook,
    EvidenceDereferencer,
    canonicalize_feedback,
    privacy_filter_feedback,
)
from .loader import load_capability_set, verify_derived_projection
from .packager import build_bundle, resolve_manifest, validate_lock
from .publication import publish_bundle

__all__ = [
    "CapabilityFeedbackHook",
    "EvidenceDereferencer",
    "build_bundle",
    "canonicalize_feedback",
    "compile_catalog",
    "load_capability_set",
    "privacy_filter_feedback",
    "publish_bundle",
    "resolve_manifest",
    "select_capability",
    "validate_fuseapi_descriptor",
    "validate_lock",
    "verify_catalog_signature",
    "verify_derived_projection",
]

__version__ = "2.0.1"
