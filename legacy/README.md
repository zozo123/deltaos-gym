# The v0.5 graders, kept for reproduction

`v0.5/tasks/` holds the five task directories of DeltaOS Research Gym v0.5 exactly as
released on 2026-11-23 (every file matches that release's `RELEASE-MANIFEST.sha256`;
the release zip's SHA-256 was
`c63d45b059457248fd2e5833197889e85b12071e5ce8ae1ddba6a9f50770c4a6`).

They are here so anyone can rerun the result the write-up starts from: grade every
candidate in `qa/controls/` with the original graders.

```sh
docker build -t deltaos-dev -f qa/Dockerfile.dev qa
sh scripts/legacy_escape_matrix.sh > /tmp/v05.tsv          # Linux host with Docker
python3 scripts/escape_matrix_report.py /tmp/v05.tsv > qa/reports/v05-escape-matrix.json
```

Do not use these graders for anything else. They run candidate code inside their own
process and can be talked into a pass in the ways the write-up describes.
