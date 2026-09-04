import json
import os
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from lens.models import Connection, LensNode
from lens.plugin_datasource_transfer import (
    import_plugin_datasource_snapshot,
    required_plugin_keys,
)

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024


class Command(BaseCommand):
    """Import legacy sources by reusing current Plugin Connections."""

    help = "Convert a streamed legacy datasource snapshot to Plugin sources."

    def add_arguments(self, parser):
        parser.add_argument("--input", choices=["-"], default="-")
        parser.add_argument("--lensnode", default="")
        parser.add_argument(
            "--connection",
            action="append",
            default=[],
            metavar="PLUGIN=NAME_OR_UUID",
        )
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        del args
        if os.environ.get("SOURCELENS_ALLOW_DATASOURCE_IMPORT") != "true":
            raise CommandError(
                "Datasource snapshot import requires explicit "
                "local-development opt-in."
            )
        snapshot = self._read_snapshot()
        try:
            plugin_keys = required_plugin_keys(snapshot)
            overrides = self._connection_overrides(options["connection"])
            connections = {
                plugin_key: self._resolve_connection(
                    plugin_key,
                    overrides.get(plugin_key, ""),
                )
                for plugin_key in plugin_keys
            }
            lensnode = self._resolve_lensnode(options["lensnode"])
            report = import_plugin_datasource_snapshot(
                snapshot,
                target_lensnode=lensnode,
                connections=connections,
                dry_run=not options["apply"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        output = {
            "applied": bool(options["apply"]),
            "target_lensnode": lensnode.name,
            "reused_connections": {
                key: value.name
                for key, value in sorted(connections.items())
            },
            **report,
        }
        self.stdout.write(json.dumps(output, sort_keys=True))

    @staticmethod
    def _connection_overrides(values):
        overrides = {}
        for value in values:
            plugin_key, separator, identifier = value.partition("=")
            if not separator or not plugin_key or not identifier:
                raise CommandError(
                    "--connection must use PLUGIN=NAME_OR_UUID."
                )
            if plugin_key in overrides:
                raise CommandError(
                    f"Connection override for {plugin_key} is duplicated."
                )
            overrides[plugin_key] = identifier
        return overrides

    @staticmethod
    def _resolve_connection(plugin_key, identifier):
        queryset = Connection.objects.select_related(
            "secret_version__material"
        ).filter(
            plugin_key=plugin_key,
            status=Connection.Status.ACTIVE,
        )
        if identifier:
            query = Q(name=identifier)
            try:
                query |= Q(uuid=identifier)
            except (TypeError, ValueError):
                pass
            queryset = queryset.filter(query)
        matches = list(queryset.order_by("pk")[:2])
        if not matches:
            raise CommandError(
                f"No active {plugin_key} Connection was found."
            )
        if len(matches) > 1:
            raise CommandError(
                f"Multiple active {plugin_key} Connections exist; use "
                f"--connection {plugin_key}=NAME_OR_UUID."
            )
        return matches[0]

    @staticmethod
    def _resolve_lensnode(value):
        if value:
            lensnode = LensNode.objects.filter(name=value).first()
            if lensnode is None:
                try:
                    lensnode = LensNode.objects.filter(uuid=value).first()
                except (TypeError, ValueError):
                    lensnode = None
            if lensnode is None:
                raise CommandError("Target LensNode does not exist.")
            return lensnode
        lensnodes = list(LensNode.objects.order_by("pk")[:2])
        if len(lensnodes) != 1:
            raise CommandError(
                "Use --lensnode when the target does not have exactly one "
                "LensNode."
            )
        return lensnodes[0]

    @staticmethod
    def _read_snapshot():
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise CommandError("Datasource snapshot exceeds 16 MiB.")
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(
                "Datasource snapshot is not valid JSON."
            ) from exc
