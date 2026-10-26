# Public issue fixture: Requests #6071

Source: https://github.com/psf/requests/issues/6071

The issue reports that an empty `CURL_CA_BUNDLE` environment value disabled TLS certificate verification. The closed issue links to the fix recorded in Requests 2.28.0 (#6074).

This is a small, dependency-free behavioral fixture derived from that issue, not a checkout of Requests and not a claim to reproduce its complete implementation. The verifier models only environment-variable selection and never makes a network request.

Run the fixture with `python -m unittest`.
