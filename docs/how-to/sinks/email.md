---
title: "Email (SMTP) sink — glean"
description: Deliver rendered digests as styled HTML email via any SMTP provider.
---

# Email (SMTP) sink

The `email` sink sends each rendered digest as an HTML email via SMTP. glean acts as an SMTP **client** — it connects to your existing mail service (Gmail, Fastmail, AWS SES, Mailgun, or a self-hosted Mailpit) and delivers the message. No mail server is needed.

## Configuration

```yaml
sinks:
  - type: email
    smtp_host: smtp.gmail.com
    smtp_port: 587
    smtp_user: ${SMTP_USER}
    smtp_password: ${SMTP_PASSWORD}
    starttls: true
    from: "glean <noreply@example.com>"
    to:
      - me@example.com
      - team@example.com
    subject_template: "[glean] {feed_name} digest — {date}"
```

## Fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `smtp_host` | string | required | SMTP server hostname |
| `smtp_port` | int | `587` | `587` (STARTTLS), `465` (implicit TLS), or `1025` (Mailpit plaintext) |
| `smtp_user` | string | `""` | Username or email for SMTP AUTH. Leave empty for servers that don't need auth (for example Mailpit) |
| `smtp_password` | string | `""` | Password or app-specific password |
| `starttls` | bool | `true` | Upgrade to TLS after connect (port 587). Cannot be true if `use_ssl` is true |
| `use_ssl` | bool | `false` | Connect with implicit TLS (port 465). Cannot be true if `starttls` is true |
| `from` | string | required | Sender address. Format: `"Display Name <addr@host>"` or just `"addr@host"` |
| `to` | list[str] | required | One or more recipient email addresses |
| `subject_template` | string | `"[glean] {feed_name} digest — {date}"` | Subject line with template variables |
| `required` | bool | `true` | When `false`, SMTP failures log a warning but do not fail the feed run |

## Subject template variables

| Variable | Replaced with |
|----------|---------------|
| `{feed_name}` | Feed name from config |
| `{date}` | Current date as `YYYY-MM-DD` |
| `{item_count}` | Number of items in the digest |
| `{trace_id}` | Per-run trace ID for log correlation |

## Provider setup guides

### Gmail (app password)

1. Enable 2-factor authentication on your Google account.
2. Go to <https://myaccount.google.com/apppasswords> and generate a new app password named `glean`.
3. In `.env`:

   ```dotenv
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
   ```

4. In `feeds.yaml`:

   ```yaml
   sinks:
     - type: email
       smtp_host: ${SMTP_HOST}
       smtp_port: ${SMTP_PORT}
       smtp_user: ${SMTP_USER}
       smtp_password: ${SMTP_PASSWORD}
       starttls: true
       from: "glean <you@gmail.com>"
       to: [you@gmail.com]
   ```

### Fastmail

1. In Fastmail, go to **Settings → Privacy & Security → Integrations → App Passwords → New**.
2. In `.env`:

   ```dotenv
   SMTP_HOST=smtp.fastmail.com
   SMTP_PORT=587
   SMTP_USER=you@fastmail.com
   SMTP_PASSWORD=<generated-app-password>
   ```

### AWS SES

1. In the SES console, open **SMTP Settings** and create SMTP credentials.
2. Verify your sender address or domain in SES.
3. In `.env`:

   ```dotenv
   SMTP_HOST=email-smtp.us-east-1.amazonaws.com
   SMTP_PORT=587
   SMTP_USER=<SES-SMTP-username>
   SMTP_PASSWORD=<SES-SMTP-password>
   ```

### Mailgun

1. In Mailgun, open **Sending → Domain Settings → SMTP Credentials**.
2. In `.env`:

   ```dotenv
   SMTP_HOST=smtp.mailgun.org
   SMTP_PORT=587
   SMTP_USER=postmaster@<your-domain>.mailgun.org
   SMTP_PASSWORD=<key>
   ```

### Mailpit (local testing, zero config)

No auth is needed. Mailpit ships as a sidecar container in [example 06](https://github.com/jaypetez/glean/tree/main/examples/06-weekly-newsletter).

```yaml
sinks:
  - type: email
    smtp_host: mailpit
    smtp_port: 1025
    smtp_user: ""
    smtp_password: ""
    starttls: false
    from: "glean <glean@localhost>"
    to: [me@localhost]
```

View caught emails at `http://localhost:8025`.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Email lands in spam | Sending from a personal account without SPF/DKIM | Use a transactional provider such as SES, Mailgun, or Postmark |
| `Authentication failed` | Wrong password type | Use an app-specific password, not your account password |
| `Connection refused` on port 587 | Firewall or wrong host | Verify host:port with `openssl s_client -connect smtp.gmail.com:587 -starttls smtp` |
| `TLS handshake failed` | Using `starttls: true` on port 465 | Switch to `use_ssl: true` and `starttls: false` |
| `5.7.8 Username and Password not accepted` (Gmail) | 2FA not enabled | Enable 2FA first, then create an app password |

## See also

- [Dashboard sink](dashboard.md) — browse digests in the built-in web UI
- [File sink](file.md) — archive to JSONL or Markdown
- [Example 06: weekly newsletter](https://github.com/jaypetez/glean/tree/main/examples/06-weekly-newsletter)
