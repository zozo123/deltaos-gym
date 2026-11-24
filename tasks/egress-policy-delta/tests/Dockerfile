FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates gcc libc6-dev binutils clang llvm python3 cbmc \
    libbpf-dev linux-libc-dev libelf-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
COPY . /tests/
RUN mkdir -p /workspace /logs/verifier && chmod +x /tests/test.sh && chmod -R go-rwx /tests /logs
WORKDIR /workspace
