# Tools image: Docker CLI + Compose plugin (from the official docker:cli image) plus Python and pytest.
# The base tag is pinned on purpose (constitution: no floating versions).
FROM docker:29.9.2-cli

# bash is needed so the dispatcher script can be unit tested inside the container.
RUN apk add --no-cache bash python3 py3-pytest

# The project is mounted at /work. Bytecode and the pytest cache are disabled because the
# project is mounted read-only for the test service.
ENV PYTHONPATH=/work/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /work

# The docker:cli entrypoint would try to interpret our commands as Docker subcommands.
ENTRYPOINT []
