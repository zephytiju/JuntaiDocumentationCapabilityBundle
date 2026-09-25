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
from .meridian import load_capability_set_meridian, publish_bundle_meridian
from .openapi import compile_openapi_tools
from .openapi_bundle import (
    build_openapi_bundle,
    inspect_openapi_bundle,
    load_openapi_bundle_meridian,
    publish_openapi_bundle_meridian,
    validate_openapi_bindings,
    validate_openapi_pin,
)
from .packager import build_bundle, resolve_manifest, validate_lock
from .publication import publish_bundle

__all__ = [
    "CapabilityFeedbackHook",
    "EvidenceDereferencer",
    "build_bundle",
    "build_openapi_bundle",
    "canonicalize_feedback",
    "compile_catalog",
    "compile_openapi_tools",
    "inspect_openapi_bundle",
    "load_capability_set",
    "load_capability_set_meridian",
    "load_openapi_bundle_meridian",
    "privacy_filter_feedback",
    "publish_bundle",
    "publish_bundle_meridian",
    "publish_openapi_bundle_meridian",
    "resolve_manifest",
    "select_capability",
    "validate_fuseapi_descriptor",
    "validate_lock",
    "validate_openapi_bindings",
    "validate_openapi_pin",
    "verify_catalog_signature",
    "verify_derived_projection",
]

__version__ = "2.2.0"
