"""Manage installed Plugin release state independently from package files."""

import hashlib
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from lens.models import PluginRelease

from .registry import PluginNotFoundError, discover_plugins


class PluginReleaseLifecycleError(ValueError):
    """Raised when a Plugin release lifecycle transition is invalid."""


def plugin_package_digest(plugin):
    """Return a deterministic SHA-256 digest for one installed package."""

    digest = hashlib.sha256()
    paths = []
    for path in plugin.path.rglob("*"):
        relative = path.relative_to(plugin.path)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise PluginReleaseLifecycleError(
                "PLUGIN_RELEASE_PACKAGE_INVALID"
            )
        if path.is_file():
            paths.append((relative.as_posix(), path))
    for relative, path in sorted(paths):
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


@transaction.atomic
def reconcile_plugin_releases():
    """Register installed versions without auto-promoting later additions."""

    grouped = defaultdict(list)
    for plugin in discover_plugins():
        grouped[plugin.key].append(plugin)

    reconciled = []
    for plugin_key, plugins in grouped.items():
        plugins.sort(key=lambda item: _semver(item.version))
        existing = {
            release.version: release
            for release in PluginRelease.objects.select_for_update().filter(
                plugin_key=plugin_key
            )
        }
        bootstrap_version = plugins[-1].version if not existing else None
        for plugin in plugins:
            package_digest = plugin_package_digest(plugin)
            release = existing.get(plugin.version)
            if release is None:
                is_bootstrap = plugin.version == bootstrap_version
                release = PluginRelease.objects.create(
                    plugin_key=plugin.key,
                    version=plugin.version,
                    package_digest=package_digest,
                    release_status=(
                        PluginRelease.ReleaseStatus.PUBLISHED
                        if is_bootstrap
                        else PluginRelease.ReleaseStatus.DEBUGGING
                    ),
                    deployment_role=(
                        PluginRelease.DeploymentRole.ACTIVE
                        if is_bootstrap
                        else PluginRelease.DeploymentRole.NONE
                    ),
                    published_at=timezone.now() if is_bootstrap else None,
                )
            elif (
                release.release_status
                == PluginRelease.ReleaseStatus.DEBUGGING
                and release.package_digest != package_digest
            ):
                release.package_digest = package_digest
                release.save(update_fields=["package_digest", "updated_at"])
            reconciled.append(release)
    return reconciled


@transaction.atomic
def publish_plugin_release(release, actor):
    """Freeze the current installed package digest and publish the release."""

    release = PluginRelease.objects.select_for_update().get(pk=release.pk)
    if release.release_status != PluginRelease.ReleaseStatus.DEBUGGING:
        raise PluginReleaseLifecycleError(
            "PLUGIN_RELEASE_NOT_DEBUGGING"
        )
    plugin = _installed_release(release.plugin_key, release.version)
    release.package_digest = plugin_package_digest(plugin)
    release.release_status = PluginRelease.ReleaseStatus.PUBLISHED
    release.published_at = timezone.now()
    release.published_by = actor
    release.save(
        update_fields=[
            "package_digest",
            "release_status",
            "published_at",
            "published_by",
            "updated_at",
        ]
    )
    return release


@transaction.atomic
def assign_plugin_release_role(release, deployment_role):
    """Atomically assign one active or candidate role per Plugin key."""

    valid_roles = {value for value, _label in PluginRelease.DeploymentRole.choices}
    if deployment_role not in valid_roles:
        raise PluginReleaseLifecycleError("PLUGIN_RELEASE_ROLE_INVALID")
    releases = PluginRelease.objects.select_for_update().filter(
        plugin_key=release.plugin_key
    )
    release = releases.get(pk=release.pk)
    if (
        deployment_role
        and release.release_status
        != PluginRelease.ReleaseStatus.PUBLISHED
    ):
        raise PluginReleaseLifecycleError(
            "PLUGIN_RELEASE_NOT_PUBLISHED"
        )
    if deployment_role:
        plugin = _installed_release(release.plugin_key, release.version)
        assert_plugin_release_integrity(plugin, release)
        releases.filter(deployment_role=deployment_role).exclude(
            pk=release.pk
        ).update(deployment_role=PluginRelease.DeploymentRole.NONE)
    release.deployment_role = deployment_role
    release.save(update_fields=["deployment_role", "updated_at"])
    return release


@transaction.atomic
def retire_plugin_release(release):
    """Retire one published release without removing its package files."""

    release = PluginRelease.objects.select_for_update().get(pk=release.pk)
    if release.release_status != PluginRelease.ReleaseStatus.PUBLISHED:
        raise PluginReleaseLifecycleError(
            "PLUGIN_RELEASE_NOT_PUBLISHED"
        )
    plugin = _installed_release(release.plugin_key, release.version)
    assert_plugin_release_integrity(plugin, release)
    release.release_status = PluginRelease.ReleaseStatus.RETIRED
    release.deployment_role = PluginRelease.DeploymentRole.NONE
    release.save(
        update_fields=["release_status", "deployment_role", "updated_at"]
    )
    return release


def active_plugin_release(plugin_key):
    """Return the published active release selected for new work."""

    try:
        return PluginRelease.objects.get(
            plugin_key=plugin_key,
            release_status=PluginRelease.ReleaseStatus.PUBLISHED,
            deployment_role=PluginRelease.DeploymentRole.ACTIVE,
        )
    except PluginRelease.DoesNotExist as exc:
        raise PluginNotFoundError(
            "active published plugin release is required"
        ) from exc


def active_installed_plugins():
    """Return every integrity-checked active Plugin package."""

    plugins = []
    releases = PluginRelease.objects.filter(
        release_status=PluginRelease.ReleaseStatus.PUBLISHED,
        deployment_role=PluginRelease.DeploymentRole.ACTIVE,
    ).order_by("plugin_key")
    for release in releases:
        try:
            plugin = _installed_release(release.plugin_key, release.version)
        except PluginReleaseLifecycleError as exc:
            if str(exc) == "PLUGIN_RELEASE_NOT_INSTALLED":
                continue
            raise
        plugins.append(assert_plugin_release_integrity(plugin, release))
    return plugins


def assert_plugin_release_integrity(plugin, release=None):
    """Reject changes to the bytes frozen for a published release."""

    if release is None:
        release = PluginRelease.objects.filter(
            plugin_key=plugin.key,
            version=plugin.version,
        ).first()
    if release is None or release.release_status == "debugging":
        return plugin
    if plugin_package_digest(plugin) != release.package_digest:
        raise PluginReleaseLifecycleError(
            "PLUGIN_RELEASE_DIGEST_MISMATCH"
        )
    return plugin


def plugin_release_payload(release, installed_plugins=None):
    """Return safe lifecycle metadata for one administrative response."""

    if installed_plugins is None:
        installed_plugins = {
            (plugin.key, plugin.version): plugin
            for plugin in discover_plugins()
        }
    plugin = installed_plugins.get((release.plugin_key, release.version))
    integrity_ok = None
    if plugin is not None and release.release_status != "debugging":
        integrity_ok = (
            plugin_package_digest(plugin) == release.package_digest
        )
    return {
        "uuid": str(release.uuid),
        "plugin_key": release.plugin_key,
        "version": release.version,
        "package_digest": release.package_digest,
        "release_status": release.release_status,
        "deployment_role": release.deployment_role,
        "published_at": release.published_at,
        "published_by": (
            release.published_by.get_username()
            if release.published_by_id
            else None
        ),
        "installed": plugin is not None,
        "integrity_ok": integrity_ok,
        "display_name": plugin.display_name if plugin else release.plugin_key,
        "description": plugin.description if plugin else "",
    }


def _installed_release(plugin_key, version):
    """Return one exact installed package without applying active selection."""

    for plugin in discover_plugins():
        if plugin.key == plugin_key and plugin.version == version:
            return plugin
    raise PluginReleaseLifecycleError("PLUGIN_RELEASE_NOT_INSTALLED")


def _semver(value):
    """Return the numeric ordering key for a validated three-part SemVer."""

    return tuple(int(part) for part in value.split("."))
