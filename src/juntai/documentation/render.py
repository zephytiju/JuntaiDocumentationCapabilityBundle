"""Deterministic projections of the canonical content graph."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from typing import Any

from .canonical import canonical_json_bytes, deterministic_tar, digest_json
from .constants import LAYOUT_PROFILE

_INLINE_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=True)
    return _INLINE_CODE.sub(lambda match: f"<code>{match.group(1)}</code>", escaped)


def markdown_to_safe_html(markdown: str) -> str:
    """Render a deliberately small, escaped Markdown subset for offline use."""

    output: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                output.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
                code.clear()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code.append(raw_line)
            continue
        if not line:
            flush_paragraph()
            close_list()
            continue
        heading = len(line) - len(line.lstrip("#"))
        if 1 <= heading <= 6 and len(line) > heading and line[heading] == " ":
            flush_paragraph()
            close_list()
            output.append(f"<h{heading}>{_inline(line[heading + 1 :])}</h{heading}>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{_inline(line[2:])}</li>")
            continue
        paragraph.append(line.strip())
    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
    flush_paragraph()
    close_list()
    return "\n".join(output)


def render_human(graph: Mapping[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
    bundle = graph["bundle"]
    units = [unit for unit in graph["units"] if "human" in unit["audiences"]]
    units.sort(key=lambda item: (item.get("order", 0), item["unitId"]))
    nav = "".join(
        (
            f'<li><a href="pages/{html.escape(unit["unitId"])}.html">'
            f"{html.escape(unit['title'])}</a></li>"
        )
        for unit in units
    )
    pages: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    for unit in units:
        references = [
            {
                "kind": "mcp.tool",
                "toolId": ref["toolId"],
                "descriptorDigest": ref["mcpDescriptorDigest"],
                "signatureSha256": ref["signatureSha256"],
            }
            for ref in unit["toolReferences"]
        ] + [
            {"kind": "schema", "schemaId": ref["schemaId"], "digest": ref["digest"]}
            for ref in unit["schemaReferences"]
        ]
        path = f"pages/{unit['unitId']}.html"
        page = {
            "unitId": unit["unitId"],
            "kind": unit["kind"],
            "path": path,
            "title": unit["title"],
            "contentDigest": unit["contentDigest"],
            "exactReferences": references,
        }
        if "parentUnitId" in unit:
            page["parentUnitId"] = unit["parentUnitId"]
        if "order" in unit:
            page["order"] = unit["order"]
        pages.append(page)
        body = markdown_to_safe_html(unit["content"])
        ref_html = "".join(
            f"<li><code>{html.escape(item.get('toolId', item.get('schemaId', '')))}</code> "
            f"<code>{html.escape(item.get('signatureSha256', item.get('digest', '')))}</code></li>"
            for item in references
        )
        document = "".join(
            [
                "<!doctype html>\n",
                f'<html lang="{html.escape(unit["locale"])}">\n',
                '<head><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width">',
                f"<title>{html.escape(unit['title'])}</title>",
                '<link rel="stylesheet" href="../viewer.css"></head>\n',
                "<body><header>",
                f"<p>{html.escape(bundle['ownerKey'])} / ",
                f"{html.escape(bundle['bundleId'])}</p>",
                f"<h1>{html.escape(unit['title'])}</h1>",
                f"<p>Version {html.escape(bundle['version'])} · ",
                f"{html.escape(unit['lifecycle'])}</p></header>",
                '<div class="layout"><nav aria-label="Documentation"><ul>',
                nav,
                '</ul></nav><main id="content">',
                body,
                '<section aria-labelledby="exact-references">',
                '<h2 id="exact-references">Exact references</h2><ul>',
                ref_html,
                "</ul></section></main></div><footer><code>",
                html.escape(graph["contracts"]["mcpDescriptorDigest"]),
                "</code></footer></body></html>\n",
            ]
        )
        files[path] = document.encode("utf-8")
    search = [
        {"unitId": unit["unitId"], "title": unit["title"], "path": f"pages/{unit['unitId']}.html"}
        for unit in units
    ]
    core = {
        "bundleDigest": digest_json(graph),
        "layoutProfile": LAYOUT_PROFILE,
        "scope": "service",
        "locale": units[0]["locale"] if units else "en",
        "pages": pages,
        "searchIndex": {"path": "search-index.json", "digest": digest_json(search)},
        "lifecycle": graph["provenance"]["lifecycle"],
        "provenance": graph["provenance"],
    }
    projection = {**core, "projectionDigest": digest_json(core)}
    files["projection.json"] = canonical_json_bytes(projection)
    files["search-index.json"] = canonical_json_bytes(search)
    files["viewer.css"] = (
        b":root{font-family:system-ui;color:#172033;background:#fff}body{margin:0}"
        b"header,footer{padding:1rem 2rem;background:#f4f6fa}"
        b".layout{display:grid;grid-template-columns:minmax(14rem,22rem) 1fr;"
        b"gap:2rem;padding:2rem}"
        b"nav{border-right:1px solid #ccd2df;padding-right:1rem}"
        b"main{max-width:78ch}pre{overflow:auto;background:#101828;color:#fff;"
        b"padding:1rem}a{color:#175cd3}code{overflow-wrap:anywhere}"
        b"@media(max-width:700px){.layout{grid-template-columns:1fr}"
        b"nav{border-right:0}}\n"
    )
    files["index.html"] = (
        f'<!doctype html><meta charset="utf-8"><title>{html.escape(bundle["bundleId"])}</title>'
        + (
            f'<meta http-equiv="refresh" content="0;url={pages[0]["path"]}">'
            if pages
            else "<p>No human units.</p>"
        )
    ).encode("utf-8")
    return projection, deterministic_tar(files), files


def render_mcp(graph: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    resources: list[dict[str, Any]] = []
    prompts: list[dict[str, Any]] = []
    for unit in sorted(graph["units"], key=lambda item: item["unitId"]):
        if "agent" not in unit["audiences"]:
            continue
        mcp = unit.get("mcp", {})
        if "resourceId" in mcp:
            resources.append(
                {
                    "resourceId": mcp["resourceId"],
                    "unitIds": [unit["unitId"]],
                    "mimeType": mcp.get("mimeType", "text/markdown"),
                    "contentDigest": unit["contentDigest"],
                }
            )
        if "promptId" in mcp:
            prompts.append(
                {
                    "promptId": mcp["promptId"],
                    "workflowUnitId": unit["unitId"],
                    "toolRefs": unit["toolReferences"],
                    "userInvoked": True,
                }
            )
    core = {
        "schemaVersion": "1",
        "bundleDigest": digest_json(graph),
        "mcpDescriptorDigest": graph["contracts"]["mcpDescriptorDigest"],
        "resources": resources,
        "prompts": prompts,
    }
    projection = {**core, "projectionDigest": digest_json(core)}
    return projection, canonical_json_bytes(projection)
