from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

PRistine = pytest.mark.pristine

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
V2_ROOT = Path(__file__).resolve().parent.parent
INTEGRITY_DIR = V2_ROOT / ".integrity"

# --- helpers ----------------------------------------------------------------


def _run_ps(
    script_name: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Shell out to a PowerShell script under scripts/."""
    script = SCRIPTS_DIR / script_name
    assert script.is_file(), f"Script not found: {script}"
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *args,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# --- fixtures ---------------------------------------------------------------


def _receipt_root(name: str) -> str:
    """Корень из расписки целостности.

    Расписки привязаны к машине владельца и не входят в репозиторий,
    поэтому без них гейт пропускается, а не падает.
    """
    receipt = INTEGRITY_DIR / name
    if not receipt.is_file():
        pytest.skip(f"{name}: расписка целостности недоступна")
    root = json.loads(receipt.read_text(encoding="utf-8"))["root"]
    assert isinstance(root, str)
    return root


@pytest.fixture
def original_path() -> str:
    return _receipt_root("receipt-original.json")


@pytest.fixture
def session_root() -> str:
    return _receipt_root("receipt-sessions.json")


# --- Assert-Pristine (happy path) -------------------------------------------


class TestAssertPristine:
    @PRistine
    def test_happy_path_returns_zero(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """Assert-Pristine should exit 0 when the original tree is pristine."""
        cp = _run_ps(
            "Assert-Pristine.ps1",
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-ReceiptDir",
            str(INTEGRITY_DIR),
            "-Verbose",
        )
        if cp.stderr:
            pass
        assert cp.returncode == 0, (
            f"Assert-Pristine failed (exit {cp.returncode}):\n"
            f"stdout: {cp.stdout}\n"
            f"stderr: {cp.stderr}"
        )

    @PRistine
    def test_fails_on_missing_receipt_dir(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """Assert-Pristine should exit 1 when receipt dir does not exist."""
        cp = _run_ps(
            "Assert-Pristine.ps1",
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-ReceiptDir",
            r"C:\does_not_exist_xyz",
            "-Verbose",
        )
        assert cp.returncode != 0, "Expected non-zero exit for missing receipt dir"


# --- Assert-EvidencePaths ---------------------------------------------------


class TestAssertEvidencePaths:
    @PRistine
    def test_safe_path_passes(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """A path completely outside both protected trees should pass."""
        cp = _run_ps(
            "Assert-EvidencePaths.ps1",
            "-Paths",
            r"C:\temp\evidence\report.pdf",
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-Detailed",
        )
        assert cp.returncode == 0, f"Safe path rejected (exit {cp.returncode}):\n{cp.stdout}"

    @PRistine
    def test_path_inside_original_fails(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """A path inside the original tree should be rejected."""
        inside = str(Path(original_path) / "src" / "lnt" / "main.py")
        cp = _run_ps(
            "Assert-EvidencePaths.ps1",
            "-Paths",
            inside,
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-Detailed",
        )
        assert cp.returncode != 0, f"Path inside original was not rejected:\n{cp.stdout}"
        assert "FAIL" in cp.stdout, "Expected FAIL message in output"

    @PRistine
    def test_path_traversal_escape_fails(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """A path with ..\\ traversal into the original tree should be rejected."""
        # Simulate an evidence path that uses ..\\ to climb back into original
        original = Path(original_path)
        escape_path = str(
            original.parent.parent
            / "other_stuff"
            / ".."
            / original.parent.name
            / original.name
            / "secrets.txt"
        )
        cp = _run_ps(
            "Assert-EvidencePaths.ps1",
            "-Paths",
            escape_path,
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-Detailed",
        )
        assert cp.returncode != 0, f"Traversal escape was not rejected:\n{cp.stdout}"

    @PRistine
    def test_path_inside_sessions_root_fails(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """A path inside the sessions root should be rejected."""
        inside = str(Path(session_root) / "some-session" / "manifest.json")
        cp = _run_ps(
            "Assert-EvidencePaths.ps1",
            "-Paths",
            inside,
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-Detailed",
        )
        assert cp.returncode != 0, f"Path inside sessions root was not rejected:\n{cp.stdout}"

    @PRistine
    def test_slash_mixing_escape_fails(
        self,
        original_path: str,
        session_root: str,
    ) -> None:
        """Forward/back slash mixing should not bypass the guard."""
        mixed = original_path.replace("\\", "/") + "/src/../.integrity/evil.dll"
        cp = _run_ps(
            "Assert-EvidencePaths.ps1",
            "-Paths",
            mixed,
            "-Original",
            original_path,
            "-SessionRoot",
            session_root,
            "-Detailed",
        )
        assert cp.returncode != 0, f"Slash-mixing escape was not rejected:\n{cp.stdout}"


# --- Verify-ApprovedPlan ----------------------------------------------------


class TestVerifyApprovedPlan:
    @PRistine
    def test_approved_plan_hash_matches(self) -> None:
        """Verify-ApprovedPlan should exit 0 when the committed copy is intact."""
        cp = _run_ps(
            "Verify-ApprovedPlan.ps1",
            "-IntegrityDir",
            str(INTEGRITY_DIR),
        )
        assert cp.returncode == 0, (
            f"Verify-ApprovedPlan failed (exit {cp.returncode}):\n{cp.stdout}"
        )
