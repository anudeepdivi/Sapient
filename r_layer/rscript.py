"""The one place the pipeline starts R."""
import os
import subprocess

from config import BASE_DIR, R_EXECUTABLE

SCRIPTS = BASE_DIR / "r_layer" / "scripts"


class RError(RuntimeError):
    def __init__(self, returncode: int, stderr: str):
        super().__init__(f"R exit {returncode}: {stderr.strip()[:500]}")
        self.returncode, self.stderr = returncode, stderr


def run(*args, timeout=60, env=None, input=None) -> subprocess.CompletedProcess:
    """Rscript <args>, from the repository root (generated programs use repo-relative paths)."""
    return subprocess.run([R_EXECUTABLE, *map(str, args)], capture_output=True, text=True,
                          timeout=timeout, cwd=BASE_DIR, input=input,
                          env={**os.environ, **env} if env else None)


def script(name: str, *args, **kwargs) -> subprocess.CompletedProcess:
    """One of the helper scripts in r_layer/scripts."""
    return run(SCRIPTS / name, *args, **kwargs)


def code(r_code: str, **kwargs) -> subprocess.CompletedProcess:
    return run("-e", r_code, **kwargs)


_COLUMNS_R = ('for (p in strsplit(Sys.getenv("SAPIENT_XPT_SOURCES"), "\\n", fixed=TRUE)[[1]]) '
              'for (f in (if (dir.exists(p)) list.files(p, pattern="[.]xpt$", full.names=TRUE) else p)) {'
              ' x <- haven::read_xpt(f);'
              ' cat(sub("[.]xpt$","",basename(f)), ":",'
              ' paste0(names(x), "=", sapply(x, function(v) if (is.character(v)) "C" else "N"),'
              ' collapse=","), "\\n", sep="") }')


def xpt_columns(*sources, timeout=300) -> dict[str, dict[str, str]]:
    """Real columns of each .xpt file, or of every .xpt in a folder, in the order given:
    {file stem: {column: "C" (character) | "N" (numeric)}}. Raises RError if R fails, so a
    failed listing is never mistaken for "no columns"."""
    result = code(_COLUMNS_R, timeout=timeout,
                  env={"SAPIENT_XPT_SOURCES": "\n".join(str(s) for s in sources)})
    if result.returncode != 0:
        raise RError(result.returncode, result.stderr)
    listing = {}
    for line in result.stdout.splitlines():
        name, _, columns = line.partition(":")
        if columns:
            listing[name] = dict(c.split("=") for c in columns.split(","))
    return listing
