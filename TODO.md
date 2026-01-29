# TODO

## High Priority
- [ ] Add unit tests for parser and email finder modules
- [ ] Handle pagination for Gmail API when many emails exist
- [ ] Add retry logic for Grok-3 API failures

## Features
- [ ] Support multiple newsletter sources (not just Axios)
- [ ] Add LinkedIn profile lookup for founders
- [ ] Create web UI dashboard for reviewing drafts before sending
- [ ] Add email open/reply tracking integration
- [ ] Support custom email templates via config

## Improvements
- [ ] Cache MX record lookups to reduce DNS queries
- [ ] Add async SMTP verification for faster processing
- [ ] Improve catch-all detection accuracy
- [ ] Add more email permutation patterns (international names)
- [ ] Better HTML parsing for complex newsletter formats

## DevOps
- [ ] Add GitHub Actions CI pipeline
- [ ] Create Docker container for deployment
- [ ] Add pre-commit hooks for linting
- [ ] Set up logging to external service (e.g., Sentry)

## Documentation
- [ ] Add example newsletter content for testing
- [ ] Document common SMTP error codes
- [ ] Add troubleshooting guide for OAuth issues
