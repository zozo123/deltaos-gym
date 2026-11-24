FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3 libc6-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY spawn.c spawn.h /workspace/
