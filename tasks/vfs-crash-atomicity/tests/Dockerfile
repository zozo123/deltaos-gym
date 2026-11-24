FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev binutils python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY . /tests/
RUN mkdir -p /workspace /logs/verifier && chmod +x /tests/test.sh && chmod -R go-rwx /tests /logs
WORKDIR /workspace
