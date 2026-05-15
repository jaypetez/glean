---
title: "REST API — glean Reference"
description: Interactive Swagger UI for glean's REST API.
---

# REST API Reference

Glean exposes a REST API at `/api/v1/*` for managing feeds, viewing status, and triggering runs. Auth via the `X-Glean-Api-Key` header (auto-generated on first boot; see [Security](../operations/security.md#api-key-bootstrap-and-rotation)).

Below is a live, interactive exploration of the API:

<swagger-ui src="../openapi.json"/>
