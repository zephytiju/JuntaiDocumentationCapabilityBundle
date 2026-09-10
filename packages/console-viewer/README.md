# Juntai Documentation Viewer

`@zephytiju/juntai-documentation-viewer` contributes the single
`platform.documentation` Console service. Its lazy `catalog`, `bundle`, and
`application-version` pages use the shared standard layout profile, fetch only
same-origin immutable delivery projections, and route restricted records with
stable scalar identifiers.

Runtime peers are Console SDK 2.1.0 and React 19. The generated Application
Metadata client comes only from the aggregate Juntai TypeScript SDK 3.0.0.

## Console SDK compatibility (2.0.2)

The supported Console SDK range is `>=2.1.0 <=2.2.0`. CI verifies both endpoint releases; all domain routes, generated client dependencies and behavior remain unchanged.
