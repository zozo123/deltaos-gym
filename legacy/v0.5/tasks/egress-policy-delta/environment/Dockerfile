FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang llvm gcc make python3 libbpf-dev linux-libc-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace

COPY policy.c /workspace/policy.c
