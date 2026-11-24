FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3 libc6-dev && rm -rf /var/lib/apt/lists/*
COPY . /tests/
RUN mkdir -p /logs/verifier && chmod +x /tests/test.sh
WORKDIR /workspace
