# Contributing

Thanks for improving the single-gateway `gpt-image-2` skill.

- Keep URL and API keys out of code, tests, commits, issues and logs. Use offline mocks for tests.
- Preserve the single-image-model scope. Images API and Responses hosted tool are independent paths; note which path a change affects.
- Run `python3 -m unittest discover -s tests -q` before opening a pull request. Describe any real-gateway verification separately; never publish private input/output images.
- For bugs, include a sanitized command, Python version and gateway capability details, but redact hostnames, secrets, request bodies and private images as appropriate.
- Derived upstream helper changes must preserve Apache-2.0 attribution in `NOTICE` and a prominent modified-file notice.
