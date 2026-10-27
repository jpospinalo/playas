"""Salidas contenidas, JSON y medición de procesos sin servicios externos."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path


def positive(value):
    number = int(value)
    if number <= 0:
        raise ValueError("Se requiere un entero positivo")
    return number


def sizes(value):
    return sorted({positive(part.strip()) for part in value.split(",")})


def output_dir(path, inputs=()):
    """Rechaza solapamientos, rutas protegidas y enlaces en la salida."""
    raw = Path(path).absolute()
    target = raw.resolve()
    for candidate in (raw, target):
        parts = [part.casefold() for part in candidate.parts]
        if any(parts[i : i + 2] == ["data", "documents"] for i in range(len(parts) - 1)):
            raise ValueError("data/documents es de solo lectura")
    for source in inputs:
        source = Path(source).resolve()
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError("La salida y las entradas deben estar separadas")
    for parent in (raw, *raw.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("La salida no admite enlaces ni junctions")
    if target.exists():
        for directory, dirs, files in os.walk(target, followlinks=False):
            for name in dirs + files:
                entry = Path(directory) / name
                if entry.is_symlink() or entry.is_junction():
                    raise ValueError("La salida contiene enlaces o junctions")
    target.mkdir(parents=True, exist_ok=True)
    return target


def inside(out, path):
    root = Path(out).resolve()
    target = Path(path)
    target = (root / target).resolve() if not target.is_absolute() else target.resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("El destino debe estar dentro de --out")
    return target


def emit(result, out=None, name="result.json"):
    body = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out is not None:
        path = inside(out, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    print(body, end="")
    return result


def disk_bytes(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def rate(count, seconds):
    return count / seconds if seconds and seconds > 0 else None


def isolated_env(out):
    """Contiene temporales, cachés de bibliotecas y bytecode del subproceso."""
    out = Path(out).resolve()
    env = dict(os.environ)
    for key, relative in {
        "TMPDIR": "tmp",
        "TMP": "tmp",
        "TEMP": "tmp",
        "HOME": "home",
        "USERPROFILE": "home",
        "XDG_CACHE_HOME": "home/.cache",
        "XDG_CONFIG_HOME": "home/.config",
        "XDG_DATA_HOME": "home/.local/share",
        "HF_HOME": "home/.cache/huggingface",
    }.items():
        destination = inside(out, relative)
        destination.mkdir(parents=True, exist_ok=True)
        env[key] = str(destination)
    env.update(PYTHONDONTWRITEBYTECODE="1", ANONYMIZED_TELEMETRY="False")
    # La invocación cambia cwd: no depender de un PYTHONPATH relativo heredado.
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return env


def parse_time_verbose(content):
    """Lee GNU time con LC_ALL=C; RSS está en KiB y CPU en porcentaje de un núcleo."""
    result = {}
    fields = {
        "User time (seconds)": "user_seconds",
        "System time (seconds)": "sys_seconds",
        "Percent of CPU this job got": "cpu_percent",
        "Maximum resident set size (kbytes)": "max_rss_kib",
    }
    for line in content.splitlines():
        for label, key in fields.items():
            if line.strip().startswith(label + ":"):
                result[key] = float(line.split(":", 1)[1].strip().rstrip("%"))
    if "max_rss_kib" in result:
        result["max_rss_bytes"] = int(result.pop("max_rss_kib") * 1024)
    if "user_seconds" in result and "sys_seconds" in result:
        result["cpu_seconds"] = result["user_seconds"] + result["sys_seconds"]
    return result


def measured_process(command, out, label, env=None):
    """GNU time incluye hijos terminados; psutil muestrea el árbol cada 50 ms."""
    out = Path(out)
    env = {**(env or isolated_env(out)), "LC_ALL": "C"}
    time_file = inside(out, label + ".time.txt")
    use_time = Path("/usr/bin/time").is_file() and os.name == "posix"
    wrapped = ["/usr/bin/time", "-v", "-o", str(time_file), "--", *command] if use_time else command
    psutil = None
    if not use_time:
        try:
            import psutil
        except ImportError:
            raise RuntimeError("Sin /usr/bin/time se requiere psutil para medir recursos") from None
    started = time.perf_counter()
    samples = {}
    peak_rss = 0
    with (
        inside(out, label + ".stdout.log").open("w", encoding="utf-8") as stdout,
        inside(out, label + ".stderr.log").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(wrapped, cwd=out, env=env, stdout=stdout, stderr=stderr)
        if use_time:
            process.wait()
        else:
            while process.poll() is None:
                rss = 0
                try:
                    root = psutil.Process(process.pid)
                    descendants = [root, *root.children(recursive=True)]
                except psutil.Error:
                    descendants = []
                for child in descendants:
                    try:
                        cpu = child.cpu_times()
                        samples[(child.pid, child.create_time())] = (cpu.user, cpu.system)
                        rss += child.memory_info().rss
                    except psutil.Error:
                        continue
                peak_rss = max(peak_rss, rss)
                time.sleep(0.05)
        returncode = process.wait()
    elapsed = time.perf_counter() - started
    result = {"wall_seconds": elapsed, "returncode": returncode}
    if use_time:
        result.update(parse_time_verbose(time_file.read_text(encoding="utf-8")))
        result["resource_method"] = "gnu_time_v"
        result["rss_scope"] = "máximo RSS de un proceso del trabajo; no suma simultánea"
    else:
        user = sum(item[0] for item in samples.values())
        system = sum(item[1] for item in samples.values())
        result.update(
            user_seconds=user,
            sys_seconds=system,
            cpu_seconds=user + system,
            cpu_percent=100 * (user + system) / elapsed,
            max_rss_bytes=peak_rss,
            resource_method="psutil_tree_50ms",
            rss_scope="suma RSS del árbol; muestreo puede perder hijos muy breves",
        )
    return result


def finite_positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Se requiere un número finito positivo")
    return number
