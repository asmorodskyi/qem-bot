# Copyright SUSE LLC
# SPDX-License-Identifier: MIT
"""Repository diff computation."""

from __future__ import annotations

import gzip
import tempfile
from logging import getLogger
from typing import TYPE_CHECKING, NamedTuple

import librepo  # ty: ignore[unresolved-import]
import pyzstd
from lxml import etree  # ty: ignore[unresolved-import]

from .config import settings

if TYPE_CHECKING:
    from argparse import Namespace

log = getLogger("bot.repo_diff")


class Package(NamedTuple):
    """Information about a package."""

    name: str
    version: str
    release: str
    arch: str

    @property
    def evr(self) -> str:
        """Version-Release string."""
        return f"{self.version}-{self.release}"


class RepoDiff:
    """Repository diff computation."""

    # XML namespace handling
    ns: dict[str, str] = {"common": "http://linux.duke.edu/metadata/common"}

    def __init__(self, repo_a: str, repo_b: str) -> None:
        """Initialize the RepoDiff class."""
        self.repo_a = self.make_repodata_url(repo_a)
        self.repo_b = self.make_repodata_url(repo_b)
        self.package_diff: set[Package] = set()
        log.info("Init repo comparison class for %s and %s", self.repo_a, self.repo_b)

    def make_repodata_url(self, project: str) -> str:  # noqa: PLR6301
        """Construct the URL for repository metadata."""
        path = project.replace(":", ":/")
        return f"{settings.obs_download_url}/{path}"

    def load_repo_packages(self, repo_url: str) -> set[Package]:
        """Load package metadata from a repository using librepo.

        Args:
            repo_url: URL or path to the repository

        Returns:
            Set of Package objects from the repository

        """
        packages = set()

        with tempfile.TemporaryDirectory() as tmpdir:
            log.debug("Load packages from %s", repo_url)
            h = librepo.Handle()
            h.repotype = librepo.LR_YUMREPO
            h.urls = [repo_url]
            h.destdir = tmpdir
            h.yumdlist = ["primary"]

            try:
                result = h.perform()
            except librepo.LibrepoException:
                log.exception("Failed to fetch repodata from %s", repo_url)
                raise

            primary_local_path = result.yum_repo["primary"]

            if primary_local_path.endswith(".gz"):
                opener = gzip.open
            elif primary_local_path.endswith(".zst"):
                opener = pyzstd.open
            else:
                opener = open

            log.debug("Build xml tree for primary.xml from %s", repo_url)

            with opener(primary_local_path, "rb") as f:
                tree = etree.parse(f)
                root = tree.getroot()

                for package in root.findall("common:package", RepoDiff.ns):
                    name_elem = package.find("common:name", RepoDiff.ns)
                    version_elem = package.find("common:version", RepoDiff.ns)
                    arch_elem = package.find("common:arch", RepoDiff.ns)

                    if name_elem is not None and version_elem is not None and arch_elem is not None:
                        pkg_info = Package(
                            name=name_elem.text,
                            version=version_elem.get("ver", ""),
                            release=version_elem.get("rel", ""),
                            arch=arch_elem.text,
                        )
                        packages.add(pkg_info)
            log.debug("%d packages found", len(packages))

            return packages

    def compare_repos(self) -> set[Package]:
        """Compare two repositories and return differences."""
        packages_a = self.load_repo_packages(self.repo_a)
        packages_b = self.load_repo_packages(self.repo_b)

        log.debug("Performing comparison")

        old_by_name_arch = {(pkg.name, pkg.arch): pkg for pkg in packages_a}
        new_by_name_arch = {(pkg.name, pkg.arch): pkg for pkg in packages_b}

        modified = set()

        # Find added and updated packages
        for key, new_pkg in new_by_name_arch.items():
            if key not in old_by_name_arch:
                # New package (didn't exist before)
                modified.add(new_pkg)
            else:
                old_pkg = old_by_name_arch[key]
                if old_pkg.evr != new_pkg.evr:
                    # Package version changed
                    modified.add(new_pkg)
        self.package_diff.update(modified)

        return modified

    def filter_package_diff(self, arch_filter: str, name_filter: str) -> set[Package]:
        """Filter package diff by arch"""
        return {
            package
            for package in self.package_diff
            if package.arch in {arch_filter, "noarch"} and name_filter in package.name
        }

    def __call__(self) -> int:
        """Run the repository diff computation."""
        try:
            self.compare_repos()
        except Exception:
            log.exception("Repo diff computation failed for projects %s and %s", self.repo_a, self.repo_b)
            return 1
        log.info(
            "Repository %s has %d new packages compared to %s",
            self.repo_b,
            len(self.package_diff),
            self.repo_a,
        )
        return 0
