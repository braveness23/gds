# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

To report a vulnerability, open a [GitHub Security Advisory](https://github.com/braveness23/gds/security/advisories/new) (private disclosure).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

You can expect an acknowledgement within 72 hours and a resolution timeline within 14 days for critical issues.

## Security Design Notes

This system is intended for deployment on private networks or secured cloud infrastructure. Key security features:

- **MQTT authentication**: Username/password with HMAC-SHA256 message signing
- **TLS**: Certificate verification enforced; no insecure fallbacks
- **GPS validation**: Input validation with type/range checks
- **Fleet coordination**: Node allowlist with per-node rate limiting
- **Credentials**: Managed via environment variables; never hardcoded

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for security architecture details.
