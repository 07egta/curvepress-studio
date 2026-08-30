# Security policy

CurvePress Studio is a local application. Bind it to `127.0.0.1` unless you have placed it behind an authenticated reverse proxy. Do not expose its development server directly to the internet.

Image uploads are limited to 30 MB; request bodies are limited to 44 MB; artifact paths reject traversal. Report security issues privately to the repository owner rather than opening a public proof-of-concept issue.


