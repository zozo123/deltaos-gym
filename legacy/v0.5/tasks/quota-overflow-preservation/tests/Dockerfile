FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang llvm gcc make python3 libbpf-dev linux-libc-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY . /tests/
RUN mkdir -p /workspace /logs/verifier && chmod +x /tests/test.sh
WORKDIR /workspace
