import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0


def run_command(command: list[str], timeout: float = 5.0) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        return CommandResult(
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )

    except subprocess.TimeoutExpired:
        return CommandResult(
            stdout="",
            stderr=f"command timed out after {timeout} seconds",
            returncode=124,
        )
