FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates gcc libc6-dev binutils make clang llvm python3 cbmc \
    libbpf-dev linux-libc-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY policy.c /workspace/policy.c
