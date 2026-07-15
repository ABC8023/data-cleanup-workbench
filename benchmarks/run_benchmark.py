"""Run the canonical cleanup workflow and enforce the memory budget."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from data_workbench.domain.recipe import (  # noqa: E402
    CastNumberStep,
    ExactDeduplicateStep,
    NormalizeTextStep,
    ParseDateStep,
    Recipe,
)
from data_workbench.engine.duckdb_runtime import DuckDBRuntime  # noqa: E402
from data_workbench.findings.registry import FindingRegistry  # noqa: E402
from data_workbench.ingest.base import fingerprint_source  # noqa: E402
from data_workbench.ingest.registry import AdapterRegistry  # noqa: E402
from data_workbench.profiling.profiler import Profiler  # noqa: E402
from data_workbench.recipes.executor import RecipeExecutor  # noqa: E402


class _NoCancel:
    def raise_if_cancelled(self) -> None:
        return None


@dataclass
class BenchmarkResult:
    input_path: str
    input_bytes: int
    machine: dict[str, object]
    wall_seconds: float
    peak_rss_bytes: int
    session_disk_bytes: int
    input_rows: int
    output_rows: int
    removed_rows: int
    quarantined_rows: int
    finding_count: int
    cleaned_sha256: str


def peak_rss_bytes() -> int:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        get_info = getattr(kernel32, "K32GetProcessMemoryInfo", None)
        if get_info is None:
            get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_info.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if not get_info(handle, ctypes.byref(counters), counters.cb):
            raise SystemExit("failed to read process memory counters")
        return int(counters.PeakWorkingSetSize)
    if sys.platform == "darwin":
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    status = Path("/proc/self/status").read_text(encoding="utf-8")
    for line in status.splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) * 1024
    return 0


def directory_bytes(directory: Path) -> int:
    return sum(
        item.stat().st_size for item in directory.rglob("*") if item.is_file()
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_recipe(fingerprint: str) -> Recipe:
    return Recipe(
        source_fingerprint=fingerprint,
        steps=[
            NormalizeTextStep(
                id="trim-name", columns=["name"], trim=True, on_error="preserve"
            ),
            ParseDateStep(
                id="parse-signup",
                columns=["signup_date"],
                formats=["%Y-%m-%d", "%d/%m/%Y"],
                on_error="preserve",
            ),
            CastNumberStep(
                id="cast-amount",
                columns=["amount"],
                target="decimal",
                on_error="quarantine",
            ),
            ExactDeduplicateStep(
                id="dedup", columns=[], keep="first", on_error="preserve"
            ),
        ],
    )


def run(input_path: Path, memory_limit: str, threads: int) -> BenchmarkResult:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="workbench-bench-") as scratch:
        session_dir = Path(scratch) / "session"
        session_dir.mkdir()
        handles = AdapterRegistry().inspect(input_path, session_dir)
        fingerprint = fingerprint_source(input_path)
        runtime = DuckDBRuntime(memory_limit, threads)
        with runtime.connect(session_dir) as connection:
            profile = Profiler().profile(
                connection, handles[0], fingerprint, lambda: None
            )
            findings = FindingRegistry.default().detect(
                connection, handles[0], profile
            )
            result = RecipeExecutor().execute(
                connection,
                handles[0],
                canonical_recipe(fingerprint),
                session_dir / "outputs",
                "parquet",
                _NoCancel(),
            )
        session_disk = directory_bytes(session_dir)
        cleaned_sha = sha256_file(result.cleaned_path)
    wall = time.perf_counter() - started
    return BenchmarkResult(
        input_path=str(input_path),
        input_bytes=input_path.stat().st_size,
        machine={
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        wall_seconds=round(wall, 3),
        peak_rss_bytes=peak_rss_bytes(),
        session_disk_bytes=session_disk,
        input_rows=result.input_rows,
        output_rows=result.output_rows,
        removed_rows=result.removed_rows,
        quarantined_rows=result.quarantined_rows,
        finding_count=len(findings),
        cleaned_sha256=cleaned_sha,
    )


def assert_benchmark(result: BenchmarkResult, max_rss_gb: float) -> None:
    if result.peak_rss_bytes > max_rss_gb * 1024**3:
        raise SystemExit(
            f"peak RSS {result.peak_rss_bytes} exceeded {max_rss_gb} GB"
        )
    reconciled = (
        result.output_rows + result.removed_rows + result.quarantined_rows
    )
    if result.input_rows != reconciled:
        raise SystemExit("row reconciliation failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--max-rss-gb", type=float, default=6.0)
    parser.add_argument("--memory-limit", default="4GB")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = run(args.input, args.memory_limit, args.threads)
    payload = json.dumps(asdict(result), indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    assert_benchmark(result, args.max_rss_gb)


if __name__ == "__main__":
    main()
