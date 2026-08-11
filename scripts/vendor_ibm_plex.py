"""Vendor pinned IBM Plex WOFF2 assets for the offline UI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import shutil
import socket
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, override
from urllib.parse import urlsplit

import httpx2

if TYPE_CHECKING:
    from collections.abc import Iterable

OUTPUT_DIR: Final = Path(__file__).parents[1] / "src/lnt/ui/static/fonts"
ARCHIVE_FONT_DIR: Final = "package/fonts/complete/woff2"
MAX_ARCHIVE_BYTES: Final = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Package:
    name: str
    version: str
    source: str
    integrity: str
    fonts: tuple[str, ...]


PACKAGES: Final = (
    _Package(
        name="@ibm/plex-sans",
        version="1.1.0",
        source="https://registry.npmjs.org/@ibm/plex-sans/-/plex-sans-1.1.0.tgz",
        integrity=(
            "sha512-WPgvO6Yfj2w5YbhyAr1tv95RUz4LRJlqN+"
            "CmYvBglabXteufP1D1E9BABMde+ZIKdRbFJDoKF5eQzfhpnbgZcQ=="
        ),
        fonts=(
            "IBMPlexSans-Regular.woff2",
            "IBMPlexSans-Medium.woff2",
            "IBMPlexSans-SemiBold.woff2",
        ),
    ),
    _Package(
        name="@ibm/plex-mono",
        version="2.5.0",
        source="https://registry.npmjs.org/@ibm/plex-mono/-/plex-mono-2.5.0.tgz",
        integrity=(
            "sha512-STBJIPxPomOYPmBMO7z5TKPJUotAF9u3gAUumTqVgwgrAO+"
            "K4FRNh0MlhsoJjKhJKsMbBJR10/bk4inkj/wc1w=="
        ),
        fonts=("IBMPlexMono-Regular.woff2", "IBMPlexMono-Medium.woff2"),
    ),
)

_LIMITS: Final = httpx2.Limits(
    max_connections=200, max_keepalive_connections=40, keepalive_expiry=30.0
)
_TIMEOUT: Final = httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)


@dataclass(frozen=True, slots=True)
class IntegrityError(Exception):
    """Report an archive that does not match its pinned SRI."""

    package_name: str
    expected: str
    actual: str

    @override
    def __str__(self) -> str:
        """Render the package and both SRI values."""
        return (
            f"integrity mismatch for {self.package_name}: "
            f"expected {self.expected}, got {self.actual}"
        )


@dataclass(frozen=True, slots=True)
class ArchiveMemberError(Exception):
    """Report a missing or non-regular required archive member."""

    package_name: str
    member_name: str

    @override
    def __str__(self) -> str:
        """Render the package and required archive path."""
        return f"{self.package_name} is missing regular file {self.member_name}"


@dataclass(frozen=True, slots=True)
class LicenseMismatchError(Exception):
    """Report differing license bytes across the pinned packages."""

    first_package: str
    second_package: str

    @override
    def __str__(self) -> str:
        """Render the packages whose licenses differ."""
        return f"license files differ between {self.first_package} and {self.second_package}"


@dataclass(frozen=True, slots=True)
class ArchiveTooLargeError(Exception):
    """Report a decoded archive that exceeds its byte limit."""

    package_name: str
    source: str
    limit_bytes: int

    @override
    def __str__(self) -> str:
        """Render package, source, and configured limit."""
        return f"{self.package_name} from {self.source} exceeds {self.limit_bytes} bytes"


@dataclass(frozen=True, slots=True)
class UntrustedArchiveUrlError(Exception):
    """Report an archive response outside the trusted registry origin."""

    package_name: str
    source: str
    final_url: str

    @override
    def __str__(self) -> str:
        """Render package, pinned source, and rejected final URL."""
        return f"{self.package_name} from {self.source} redirected to {self.final_url}"


class _PackageManifest(TypedDict):
    name: str
    version: str
    source: str
    integrity: str


class _FontManifest(TypedDict):
    packages: list[_PackageManifest]
    license: list[str]
    files: dict[str, str]


def collect_archive_bytes(
    package: _Package,
    chunks: Iterable[bytes],
    limit_bytes: int = MAX_ARCHIVE_BYTES,
) -> bytes:
    """Collect decoded chunks without allowing the buffer to exceed its limit."""
    archive = bytearray()
    for chunk in chunks:
        if len(archive) + len(chunk) > limit_bytes:
            raise ArchiveTooLargeError(package.name, package.source, limit_bytes)
        archive.extend(chunk)
    return bytes(archive)


def validate_archive_url(package: _Package, final_url: str) -> None:
    """Require the final response URL to use the pinned HTTPS registry origin."""
    parsed = urlsplit(final_url)
    if parsed.scheme != "https" or parsed.hostname != "registry.npmjs.org":
        raise UntrustedArchiveUrlError(package.name, package.source, final_url)


def verify_integrity(package: _Package, archive_bytes: bytes) -> None:
    """Require archive bytes to match the package's pinned SRI."""
    expected_digest = base64.b64decode(package.integrity.removeprefix("sha512-"), validate=True)
    actual_digest = hashlib.sha512(archive_bytes).digest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise IntegrityError(
            package_name=package.name,
            expected=package.integrity,
            actual=f"sha512-{base64.b64encode(actual_digest).decode('ascii')}",
        )


def _read_member(archive: tarfile.TarFile, package: _Package, member_name: str) -> bytes:
    try:
        member = archive.getmember(member_name)
    except KeyError as error:
        raise ArchiveMemberError(package_name=package.name, member_name=member_name) from error
    if not member.isfile():
        raise ArchiveMemberError(package_name=package.name, member_name=member_name)
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ArchiveMemberError(package_name=package.name, member_name=member_name)
    with extracted:
        return extracted.read()


def extract_package(package: _Package, archive_bytes: bytes) -> tuple[dict[str, bytes], bytes]:
    """Read only the requested fonts and license from a package archive."""
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        fonts = {
            name: _read_member(archive, package, f"{ARCHIVE_FONT_DIR}/{name}")
            for name in package.fonts
        }
        license_bytes = _read_member(archive, package, "package/LICENSE.txt")
    return fonts, license_bytes


def require_matching_license(first: bytes, second: bytes) -> bytes:
    """Return identical license bytes or reject mismatched packages."""
    if first != second:
        raise LicenseMismatchError(
            first_package=PACKAGES[0].name,
            second_package=PACKAGES[1].name,
        )
    return first


def write_assets(
    fonts: dict[str, bytes],
    license_bytes: bytes,
    target_dir: Path | None = None,
) -> None:
    """Replace a font directory only after its complete successor is staged."""
    target = OUTPUT_DIR if target_dir is None else target_dir
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    backup = staging.with_name(f"{staging.name}.backup")
    try:
        for name, asset_bytes in fonts.items():
            (staging / name).write_bytes(asset_bytes)
        (staging / "OFL.txt").write_bytes(license_bytes)

        packages: list[_PackageManifest] = [
            _PackageManifest(
                name=package.name,
                version=package.version,
                source=package.source,
                integrity=package.integrity,
            )
            for package in PACKAGES
        ]
        manifest = _FontManifest(
            packages=packages,
            license=["OFL-1.1"],
            files={
                name: hashlib.sha256(asset_bytes).hexdigest() for name, asset_bytes in fonts.items()
            },
        )
        (staging / "manifest.json").write_text(
            f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        # ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: хвост файла (от этой строки и ниже)
        # утрачен при сбое диска и реконструирован по уцелевшей голове модуля.
        if target.exists():
            target.rename(backup)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


def download_archive(package: _Package) -> bytes:
    """Stream the pinned archive and verify origin and integrity."""
    with (
        httpx2.Client(limits=_LIMITS, timeout=_TIMEOUT, follow_redirects=True) as client,
        client.stream("GET", package.source) as response,
    ):
        response.raise_for_status()
        validate_archive_url(package, str(response.url))
        archive_bytes = collect_archive_bytes(package, response.iter_bytes())
    verify_integrity(package, archive_bytes)
    return archive_bytes


def main() -> None:
    """Vendor the pinned IBM Plex packages into the offline static directory."""
    socket.setdefaulttimeout(60.0)
    fonts: dict[str, bytes] = {}
    licenses: list[bytes] = []
    for package in PACKAGES:
        archive_bytes = download_archive(package)
        package_fonts, license_bytes = extract_package(package, archive_bytes)
        fonts.update(package_fonts)
        licenses.append(license_bytes)
    write_assets(fonts, require_matching_license(licenses[0], licenses[1]))


if __name__ == "__main__":
    main()
