FROM python:3.12-slim
COPY . /tests/
RUN mkdir -p /workspace /logs/verifier && chmod +x /tests/test.sh
WORKDIR /workspace
