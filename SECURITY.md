# Security Policy

## Supported versions

Only the latest tagged release receives fixes. If you're running an older version, please update before reporting.

| Version    | Supported |
|------------|-----------|
| 1.x        | ✅ yes    |
| < 1.0      | ❌ no     |

## Reporting a vulnerability

**Please do not file public issues for security problems.**

Report privately via GitHub's [Private Vulnerability Reporting](https://github.com/jaypetez/glean/security/advisories/new) (preferred), or email **jayson@shoe4africa.org** with `[glean security]` in the subject.

Include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept if you have one.
- The version / commit you tested against.
- Any suggested remediation.

## What to expect

- Acknowledgement within **3 business days**.
- A first assessment (confirmed / needs-info / out-of-scope) within **7 days**.
- For confirmed issues, a fix or mitigation plan within **30 days** when reasonably possible. Complex issues may take longer; we'll keep you posted.
- Credit in the release notes when the fix ships, unless you prefer to stay anonymous.

## Scope

In scope:

- The `glean` daemon and its bundled source / LLM provider / sink plugins.
- The published container image at `ghcr.io/jaypetez/glean`.
- Documented configuration surfaces (`feeds.yaml`, `.env`, CLI flags).

Out of scope:

- Vulnerabilities in third-party services (Telegram, Ollama, Anthropic, OpenAI, etc.) — please report those upstream.
- Issues that require the attacker to already control the operator's machine, `.env`, or `feeds.yaml`.
- DoS via obviously-malformed config you wrote yourself.

## Secrets hygiene reminder

`glean` reads bot tokens and API keys from `.env`. Never commit `.env`, never paste it into an issue, and rotate any secret you suspect has leaked.
