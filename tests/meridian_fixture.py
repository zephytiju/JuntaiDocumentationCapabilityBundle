# SPDX-License-Identifier: Apache-2.0
"""Deployment-owned disposable PostgreSQL/S3 fixture using released packages."""

import os
from copy import deepcopy

import boto3
from meridian_storage import Meridian, RuntimeConfig
from meridian_storage.adapters.postgresql import (
    MigrationExecutor,
    PostgreSQLSettings,
    SchemaCompiler,
)
from meridian_storage.adapters.postgresql.descriptor import manifest
from meridian_storage.adapters.s3 import S3AdapterFactory, S3Config, s3_capability_manifest
from meridian_storage.evidence import EvidenceCatalogProvider
from meridian_storage.object_common import ObjectCatalogProvider
from meridian_storage.plugins.config_artifact.schemas import ConfigArtifactSchemaProvider
from meridian_storage.runtime.config import BindingConfig
from meridian_storage.semantics import StructuredCatalogProvider
from meridian_storage.spi import AdapterCreateContext, PhysicalResource, SecretValue
from psycopg import connect


class FixtureSecrets:
    def resolve(self, reference):
        return SecretValue(reference.reference.encode())


def compose(
    *,
    duplicate_factory=False,
    additional_providers=(),
    schema_namespace="artifact_acceptance",
    config_output=None,
):
    port = int(os.environ.get("MERIDIAN_TEST_PG_PORT", "55441"))
    endpoint = os.environ.get("MERIDIAN_TEST_S3_ENDPOINT", "http://127.0.0.1:59441")
    provider = ConfigArtifactSchemaProvider()
    providers = (provider, *additional_providers)
    bundles = tuple(p.load() for p in providers)
    resources = tuple(r for b in bundles for r in b.resources)
    schemas = tuple(s for b in bundles for s in b.schemas)
    layouts = []
    for resource in resources:
        if resource.ref.catalog not in ("structured", "evidence"):
            continue
        schema = next(s for s in schemas if s.ref == resource.schema)
        fields = []
        for index, field in enumerate(schema.definition["fields"]):
            kind = field["logicalType"]
            if not isinstance(kind, str):
                kind = kind["kind"]
            fields.append(
                {
                    "name": field["name"],
                    "column": f"f_{index}",
                    "logicalType": kind,
                    "nullable": field["nullable"],
                    "mutable": field["mutable"],
                }
            )
        layouts.append(
            {
                "ref": resource.ref.canonical,
                "table": resource.ref.name.replace("-", "_"),
                "profile": resource.profile,
                "schemaFingerprint": schema.fingerprint,
                "resourceFingerprint": resource.fingerprint,
                "fields": fields,
                "identity": list(schema.definition["identity"]),
                "indexes": [],
                "relation": None,
            }
        )
    pg = {
        "id": "metadata",
        "adapterId": "postgresql",
        "adapterContract": "1.0.0",
        "engineProfile": "postgresql-postgis-local-single-primary",
        "engineVersion": "16-postgis-3.4",
        "endpoint": f"host=127.0.0.1 port={port} dbname=meridian",
        "serviceRef": None,
        "physicalNamespace": schema_namespace,
        "tls": {
            "mode": "disabled",
            "serverName": None,
            "caRef": None,
            "clientCertificateRef": None,
        },
        "identityRef": {"provider": "fixture", "reference": "meridian"},
        "secretRef": {"provider": "fixture", "reference": "meridian-fixture-only"},
        "client": {
            "minSize": 0,
            "maxSize": 8,
            "acquireTimeoutMs": 5000,
            "idleTimeoutMs": 1000,
            "operationTimeoutMs": 10000,
            "maxResultBytes": 1048576,
            "iteratorLifetimeMs": 5000,
        },
        "requiredCapabilityFingerprint": manifest(
            "postgresql-postgis-local-single-primary", "16-postgis-3.4"
        ).fingerprint,
        "requiredPhysicalFingerprint": None,
        "compatibilityPins": {},
        "settings": {
            "formatVersion": "meridian.postgresql.settings.v1",
            "applicationName": "meridian-artifact-acceptance",
            "scopeKeys": ["tenant", "application"],
            "topology": {"expectedStandbys": 0},
            "resources": layouts,
        },
        "extensions": {},
    }
    settings = PostgreSQLSettings.from_binding(BindingConfig.from_mapping(pg, "fixture"))
    plan = SchemaCompiler(settings).compile()
    with connect(
        host="127.0.0.1",
        port=port,
        dbname="meridian",
        user="meridian",
        password="meridian-fixture-only",
    ) as connection:
        MigrationExecutor(settings).apply(connection, plan)
    pg["requiredPhysicalFingerprint"] = plan.physical_fingerprint
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["NOUS_TEST_S3_IDENTITY"],
        aws_secret_access_key=os.environ["NOUS_TEST_S3_CREDENTIAL"],
        region_name="us-east-1",
    )
    bucket = "meridian-artifact-acceptance"
    try:
        if bucket not in {b["Name"] for b in client.list_buckets()["Buckets"]}:
            client.create_bucket(Bucket=bucket)
    finally:
        client.close()
    s3config = S3Config(bucket, endpoint_url=endpoint, allow_insecure_http=True)
    s3 = deepcopy(pg)
    s3.update(
        id="objects",
        adapterId="s3",
        engineProfile=s3config.engine_profile,
        engineVersion=s3config.engine_version,
        endpoint=endpoint,
        physicalNamespace=bucket,
        settings={"allowInsecureHttp": True},
        requiredCapabilityFingerprint=s3_capability_manifest(s3config).fingerprint,
        requiredPhysicalFingerprint=None,
    )
    s3["identityRef"]["reference"] = os.environ["NOUS_TEST_S3_IDENTITY"]
    s3["secretRef"]["reference"] = os.environ["NOUS_TEST_S3_CREDENTIAL"]
    binding = BindingConfig.from_mapping(s3, "fixture")
    secrets = FixtureSecrets()
    factory = S3AdapterFactory()
    probe = factory.create(
        AdapterCreateContext(
            binding=binding,
            identity=secrets.resolve(binding.identity_ref),
            credential=secrets.resolve(binding.secret_ref),
        )
    )
    probe.open()
    try:
        s3["requiredPhysicalFingerprint"] = probe.verify_physical(
            tuple(
                PhysicalResource(r.ref, r.fingerprint, None, r.profile)
                for r in resources
                if r.ref.catalog == "object"
            )
        ).fingerprint
    finally:
        probe.close()
    catalogs = [StructuredCatalogProvider(), ObjectCatalogProvider()]
    if any(r.ref.catalog == "evidence" for r in resources):
        catalogs.append(EvidenceCatalogProvider())
    config = {
        "formatVersion": "meridian-config.v1",
        "profile": "artifact-acceptance",
        "catalogs": {
            "providers": [
                {
                    "name": p.manifest().catalog_name,
                    "package": p.manifest().package_name,
                    "contract": p.manifest().catalog_contract_version,
                    "requiredFingerprint": p.manifest().fingerprint,
                }
                for p in catalogs
            ],
            "extensions": {},
        },
        "schemas": {
            "providers": [
                {
                    "id": p.provider_id,
                    "package": "meridian-plugin-config-artifact"
                    if p is provider
                    else "juntai-documentation-capability",
                    "contract": "1.x",
                    "requiredFingerprint": b.fingerprint,
                }
                for p, b in zip(providers, bundles, strict=True)
            ],
            "live": {"enabled": False, "required": False, "providerId": None},
            "extensions": {},
        },
        "resources": {
            "pins": [
                {
                    "ref": r.ref.to_dict(),
                    "providerId": p.provider_id,
                    "requiredFingerprint": r.fingerprint,
                }
                for p, b in zip(providers, bundles, strict=True)
                for r in b.resources
            ],
            "extensions": {},
        },
        "bindings": [pg, s3],
        "placements": [
            {
                "id": catalog,
                "selector": {
                    "resources": [r.ref.to_dict() for r in resources if r.ref.catalog == catalog],
                    "catalog": None,
                    "labels": {},
                },
                "bindingId": name,
                "extensions": {},
            }
            for catalog, name in (
                ("structured", "metadata"),
                ("object", "objects"),
                ("evidence", "metadata"),
            )
            if any(r.ref.catalog == catalog for r in resources)
        ],
        "validation": {
            "strict": True,
            "requirePhysicalFingerprints": True,
            "defaultOperationTimeoutMs": 10000,
            "idempotencyCacheEntries": 64,
            "retry": {"maxAttempts": 1, "baseDelayMs": 0, "maxDelayMs": 0, "jitterRatio": 0},
        },
        "telemetry": {
            "enabled": False,
            "serviceName": None,
            "suppressExporterRecursion": True,
            "attributes": {},
            "extensions": {},
        },
        "extensions": {},
    }
    runtime = Meridian(
        RuntimeConfig.from_mapping(config),
        secret_resolver=secrets,
        adapter_factories=[factory] if duplicate_factory else [],
        schema_providers=additional_providers,
    )
    if config_output is not None:
        import json

        exported = deepcopy(config)
        for binding in exported["bindings"]:
            binding["identityRef"] = {"provider": "environment", "reference": "NOUS_TEST_IDENTITY"}
            binding["secretRef"] = {"provider": "environment", "reference": "NOUS_TEST_SECRET"}
        config_output.write_text(json.dumps(exported))
    runtime.start()
    return runtime
