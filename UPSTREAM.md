# Upstream baseline

`docker-compose.yaml` is a byte-for-byte copy of the official Penpot Compose file. It MUST NOT be edited;
all project changes live in `docker-compose.override.yaml`. `tests/unit/test_upstream.py` verifies the hash below.

- source: https://raw.githubusercontent.com/penpot/penpot/2.18.4/docker/images/docker-compose.yaml
- tag: 2.18.4
- retrieved: 2026-10-25
- sha256: 85e9df797d84e01cdbe774b942f2f7fa7e60d90cd284f5f1b7d200628832c93a
