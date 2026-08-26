"""Tests for the release-note build tooling."""

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.release_notes import (
    ReleaseNoteError,
    build_manifest,
    parse_fragment,
    render_release_body,
    validate_pr,
)


class ReleaseNotesTestCase(unittest.TestCase):
    """Exercise fragment validation and Git range aggregation."""

    def test_parse_fragment_requires_supported_type_and_translations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.yaml"
            valid.write_text(
                "type: feature\n"
                "audience: user\n"
                "en: Added localized release notes.\n"
                "zh-CN: "
                "\u65b0\u589e\u672c\u5730\u5316\u66f4\u65b0"
                "\u65e5\u5fd7\u3002\n",
                encoding="utf-8",
            )
            missing_translation = root / "missing.yaml"
            missing_translation.write_text(
                "type: fix\n" "audience: user\n" "en: Fixed the issue.\n",
                encoding="utf-8",
            )
            invalid_type = root / "invalid.yaml"
            invalid_type.write_text(
                "type: security\n"
                "audience: user\n"
                "en: Hardened access.\n"
                "zh-CN: \u52a0\u5f3a\u8bbf\u95ee\u63a7\u5236\u3002\n",
                encoding="utf-8",
            )
            invalid_audience = root / "invalid-audience.yaml"
            invalid_audience.write_text(
                "type: improvement\n"
                "audience: operator\n"
                "en: Improved administration.\n"
                "zh-CN: \u6539\u8fdb\u7ba1\u7406\u4f53\u9a8c\u3002\n",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_fragment(valid),
                {
                    "type": "feature",
                    "audience": "user",
                    "en": "Added localized release notes.",
                    "zh-CN": (
                        "\u65b0\u589e\u672c\u5730\u5316\u66f4\u65b0"
                        "\u65e5\u5fd7\u3002"
                    ),
                },
            )
            with self.assertRaisesRegex(
                ReleaseNoteError,
                "missing required fields: zh-CN",
            ):
                parse_fragment(missing_translation)
            with self.assertRaisesRegex(
                ReleaseNoteError,
                "unsupported type",
            ):
                parse_fragment(invalid_type)
            with self.assertRaisesRegex(
                ReleaseNoteError,
                "unsupported audience",
            ):
                parse_fragment(invalid_audience)

    def test_parse_fragment_rejects_oversized_user_facing_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fragment = Path(directory) / "oversized.yaml"
            fragment.write_text(
                "type: feature\n"
                "audience: user\n"
                f"en: {'x' * 1001}\n"
                "zh-CN: \u65b0\u529f\u80fd\u3002\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ReleaseNoteError,
                "field en exceeds 1000 characters",
            ):
                parse_fragment(fragment)

    def test_parse_fragment_accepts_optional_spanish_translation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fragment = Path(directory) / "spanish.yaml"
            fragment.write_text(
                "type: feature\n"
                "audience: user\n"
                "en: Added Spanish release notes.\n"
                "zh-CN: 新增西班牙语更新日志。\n"
                "es: Se añadieron notas de la versión en español.\n",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_fragment(fragment)["es"],
                "Se añadieron notas de la versión en español.",
            )

    def test_build_manifest_collects_only_new_fragments_since_previous_tag(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.name", "Test User")
            self._git(repo, "config", "user.email", "test@example.com")

            notes = repo / "release-notes"
            notes.mkdir()
            old_fragment = notes / "100.yaml"
            old_fragment.write_text(
                "type: fix\n"
                "audience: user\n"
                "en: Fixed the old issue.\n"
                "zh-CN: \u4fee\u590d\u65e7\u95ee\u9898\u3002\n",
                encoding="utf-8",
            )
            self._commit_all(repo, "First release")
            self._git(repo, "tag", "v1.0.0")

            old_fragment.write_text(
                "type: fix\n"
                "audience: user\n"
                "en: Edited historical text.\n"
                "zh-CN: \u7f16\u8f91\u5386\u53f2\u6587\u672c\u3002\n",
                encoding="utf-8",
            )
            (notes / "200.yaml").write_text(
                "type: improvement\n"
                "audience: admin\n"
                "en: Improved release visibility.\n"
                "zh-CN: "
                "\u6539\u8fdb\u7248\u672c\u53d8\u66f4"
                "\u53ef\u89c1\u6027\u3002\n"
                "es: Mejorada la visibilidad de las versiones.\n",
                encoding="utf-8",
            )
            self._commit_all(repo, "Second release")
            self._git(repo, "tag", "v1.1.0")

            manifest = build_manifest(
                repo=repo,
                tag="v1.1.0",
                version="1.1.0",
                release_date="2026/08/03",
            )

            self.assertEqual(manifest["version"], "1.1.0")
            self.assertEqual(manifest["releaseDate"], "2026/08/03")
            self.assertEqual(manifest["categories"]["feature"], [])
            self.assertEqual(manifest["categories"]["fix"], [])
            self.assertEqual(
                manifest["categories"]["improvement"],
                [
                    {
                        "audience": "admin",
                        "en": "Improved release visibility.",
                        "zh-CN": (
                            "\u6539\u8fdb\u7248\u672c\u53d8\u66f4"
                            "\u53ef\u89c1\u6027\u3002"
                        ),
                        "es": (
                            "Mejorada la visibilidad de las versiones."
                        ),
                    }
                ],
            )

    def test_release_body_uses_only_english_user_facing_text(
        self,
    ) -> None:
        manifest = {
            "version": "1.1.0",
            "releaseDate": "2026/08/03",
            "categories": {
                "feature": [
                    {
                        "audience": "user",
                        "en": "Added in-product release notes.",
                        "zh-CN": (
                            "\u65b0\u589e\u5e94\u7528\u5185\u66f4\u65b0"
                            "\u65e5\u5fd7\u3002"
                        ),
                    }
                ],
                "improvement": [],
                "fix": [
                    {
                        "audience": "admin",
                        "en": "Fixed an administrator workflow.",
                        "zh-CN": (
                            "\u4fee\u590d\u7ba1\u7406\u5458"
                            "\u5de5\u4f5c\u6d41\u7a0b\u3002"
                        ),
                    }
                ],
            },
        }

        body = render_release_body(manifest)

        self.assertIn("## Features", body)
        self.assertIn("Added in-product release notes.", body)
        self.assertNotIn(
            "\u65b0\u589e\u5e94\u7528\u5185\u66f4\u65b0\u65e5\u5fd7",
            body,
        )
        self.assertIn("## Fixes", body)
        self.assertIn(
            "- **Administrators:** Fixed an administrator workflow.",
            body,
        )

    def test_pr_requires_new_fragment_or_explicit_skip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.name", "Test User")
            self._git(repo, "config", "user.email", "test@example.com")
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            self._commit_all(repo, "Base")
            base = self._git(repo, "rev-parse", "HEAD").stdout.strip()

            (repo / "README.md").write_text("changed\n", encoding="utf-8")
            self._commit_all(repo, "Head")
            head = self._git(repo, "rev-parse", "HEAD").stdout.strip()

            with self.assertRaisesRegex(
                ReleaseNoteError,
                "add a release-note fragment",
            ):
                validate_pr(repo, base, head, skip=False)
            self.assertEqual(validate_pr(repo, base, head, skip=True), [])

    def test_release_workflow_gives_github_cli_repository_context(
        self,
    ) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "build_and_deploy.yml"
        )
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        publish_steps = workflow["jobs"]["publish-release"]["steps"]
        release_step = next(
            step
            for step in publish_steps
            if step.get("name") == "Create or update GitHub Release"
        )

        self.assertEqual(
            release_step["env"].get("GH_REPO"),
            "${{ github.repository }}",
        )

    def _commit_all(self, repo: Path, message: str) -> None:
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)

    def _git(
        self,
        repo: Path,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
