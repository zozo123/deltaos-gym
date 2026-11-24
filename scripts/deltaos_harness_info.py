"""Version and tool facts for reports, read from the canonical harness."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import deltaos_harness as H  # noqa: E402


def facts() -> dict:
    return {"version": H.VERSION, "gcc": H.tool_version("gcc"), "clang": H.tool_version("clang"),
            "cbmc": H.tool_version("cbmc")}
