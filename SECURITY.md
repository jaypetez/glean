# Security Policy

## Supported versions

Only the current v1.1.x release line receives security fixes.
If you are running an older version, update before reporting unless the issue is
needed to confirm whether the latest release is affected.

| Version | Supported |
|---------|-----------|
| v1.1.x  | Yes       |
| < v1.1  | No        |

## Reporting a vulnerability

Please do not file public issues for security problems.

Report privately through GitHub's [Private Vulnerability Reporting](https://github.com/jaypetez/glean/security/advisories/new)
(preferred), or email **jayson@shoe4africa.org** with `[glean security]` in the
subject.

Include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept if you have one.
- The version or commit you tested against.
- Any suggested remediation.

## Response SLA and disclosure

- We aim to triage reports within **7 days** on a best-effort basis.
- For confirmed critical issues, we target a fix or mitigation within **90 days**.
- We coordinate disclosure with reporters and use a **90-day disclosure window**
  unless we agree otherwise.
- We credit reporters in release notes when the fix ships, unless they prefer to
  stay anonymous.

## Scope

In scope:

- The `glean` daemon and its bundled source, LLM provider, and sink plugins.
- The published container image at `ghcr.io/jaypetez/glean`.
- Documented configuration surfaces (`feeds.yaml`, `.env`, CLI flags).

Out of scope:

- Vulnerabilities in third-party services such as Telegram, Ollama, Anthropic,
  OpenAI, Brave, Tavily, Serper, Exa, Discord, Slack, and ntfy.
- Issues that require the attacker to already control the operator's machine,
  `.env`, `feeds.yaml`, or sink credentials.
- Denial of service through obviously malformed configuration written by the
  operator.

## Secrets hygiene reminder

`glean` reads bot tokens and API keys from `.env`. Never commit `.env`, never
paste it into an issue, and rotate any secret you suspect has leaked.
