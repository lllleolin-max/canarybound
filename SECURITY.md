# Security and responsible reporting

Use pseudonymous IDs and local de-identified logs. Aggregate reports omit IDs, but source logs can still be sensitive. No telemetry or network transport exists. Do not commit customer or personal traces. The manifest digest does not authenticate inputs. Input caps bound local parsing effort; do not expose this CLI directly as an unauthenticated public service. Files and output directories must be controlled by the invoking user; alias checks do not secure a directory against concurrent hostile replacement.

Report validation, interval-enclosure or identity defects through a repository issue with a minimal synthetic reproduction and affected version; omit secrets and private logs. Until a public repository exists, send a report to the maintainer through the channel distributing this code. Numeric/statistical claims are limited to the declared subset in docs/MATH.md.
