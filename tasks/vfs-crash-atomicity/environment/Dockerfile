FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev binutils make python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY publisher.c vfs_api.h /workspace/
