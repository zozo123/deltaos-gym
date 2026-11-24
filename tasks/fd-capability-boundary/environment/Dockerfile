FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev binutils make python3 strace ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY spawn.c spawn.h /workspace/
