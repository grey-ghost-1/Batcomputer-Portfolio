import json
import os
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import yaml

import app as site

ROOT = Path(__file__).resolve().parents[1]


class PublicUrlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for name in ("action", "href", "src"):
            value = attributes.get(name)
            if value:
                self.urls.append(value)


class RenderManifestTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))

    def test_blueprint_defines_only_the_public_flask_service(self):
        self.assertEqual(set(self.manifest), {"services"})
        self.assertEqual(len(self.manifest["services"]), 1)
        service = self.manifest["services"][0]
        self.assertEqual(service["type"], "web")
        self.assertEqual(service["name"], "batcomputer-portfolio")
        self.assertEqual(service["runtime"], "python")
        self.assertEqual(service["branch"], "grey-ghost-1-render-release-config")
        self.assertEqual(service["healthCheckPath"], "/healthz")
        self.assertEqual(service["autoDeployTrigger"], "off")
        self.assertNotIn("dockerfilePath", service)
        self.assertNotIn("dockerCommand", service)

    def test_build_and_start_commands_are_explicit_and_port_aware(self):
        service = self.manifest["services"][0]
        self.assertEqual(
            service["buildCommand"],
            "python -m pip install --disable-pip-version-check --requirement requirements.txt",
        )
        self.assertEqual(
            service["startCommand"],
            (
                "gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 "
                "--access-logfile - app:app"
            ),
        )
        self.assertNotIn(":5000", service["startCommand"])

    def test_hosted_environment_is_fail_closed_and_contains_no_provider_configuration(self):
        service = self.manifest["services"][0]
        variables = {item["key"]: item for item in service["envVars"]}
        self.assertEqual(variables["SITE_ENVIRONMENT"]["value"], "production")
        self.assertEqual(variables["SITE_HOSTED_MODE"]["value"], "true")
        self.assertEqual(variables["SITE_PROPOSALS_ENABLED"]["value"], "false")
        self.assertTrue(variables["SITE_SESSION_SECRET"]["generateValue"])
        forbidden_fragments = ("ALFRED", "OLLAMA", "OPENAI", "PROVIDER", "TOKEN", "API_KEY")
        for variable in variables:
            with self.subTest(variable=variable):
                self.assertFalse(any(fragment in variable for fragment in forbidden_fragments))


class HostedRuntimeTestCase(unittest.TestCase):
    def test_hosted_runtime_requires_production_and_a_managed_session_secret(self):
        safe_environment = {
            "SITE_ENVIRONMENT": "production",
            "SITE_HOSTED_MODE": "true",
            "SITE_PROPOSALS_ENABLED": "false",
            "SITE_SESSION_SECRET": "render-generated-secret-with-enough-variety-123",
        }
        config = site._runtime_config(safe_environment)
        self.assertTrue(config["HOSTED_MODE"])
        self.assertFalse(config["PROPOSALS_ENABLED"])
        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertEqual(config["PREFERRED_URL_SCHEME"], "https")

        invalid_environments = (
            {**safe_environment, "SITE_ENVIRONMENT": "development"},
            {**safe_environment, "SITE_PROPOSALS_ENABLED": "true"},
            {key: value for key, value in safe_environment.items() if key != "SITE_SESSION_SECRET"},
        )
        for environment in invalid_environments:
            with self.subTest(environment=environment), self.assertRaises(RuntimeError):
                site._runtime_config(environment)

    def test_production_import_applies_proxy_and_https_configuration(self):
        environment = {
            **os.environ,
            "SITE_ENVIRONMENT": "production",
            "SITE_HOSTED_MODE": "true",
            "SITE_PROPOSALS_ENABLED": "false",
            "SITE_SESSION_SECRET": "render-generated-secret-with-enough-variety-123",
        }
        command = (
            "import json, app; "
            "print(json.dumps({"
            "'hosted': app.app.config['HOSTED_MODE'], "
            "'proposals': app.app.config['PROPOSALS_ENABLED'], "
            "'secure': app.app.config['SESSION_COOKIE_SECURE'], "
            "'scheme': app.app.config['PREFERRED_URL_SCHEME'], "
            "'middleware': type(app.app.wsgi_app).__name__"
            "}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "hosted": True,
                "proposals": False,
                "secure": True,
                "scheme": "https",
                "middleware": "ProxyFix",
            },
        )

    def test_hosted_health_and_showcase_do_not_expose_private_capabilities(self):
        original = {
            key: site.app.config[key]
            for key in ("HOSTED_MODE", "PROPOSALS_ENABLED", "SESSION_COOKIE_SECURE")
        }
        site.app.config.update(
            HOSTED_MODE=True,
            PROPOSALS_ENABLED=False,
            SESSION_COOKIE_SECURE=True,
            TESTING=True,
        )
        try:
            client = site.app.test_client()
            health = client.get("/healthz")
            self.assertEqual(health.get_json(), {"status": "ok"})
            self.assertNotIn("Server", health.headers)
            self.assertIn("max-age=31536000", health.headers["Strict-Transport-Security"])

            state = client.get("/api/alfred-showcase/state").get_json()
            self.assertIsNone(state["model"])
            self.assertFalse(state["network_enabled"])
            self.assertFalse(state["real_execution_enabled"])
            self.assertEqual(client.get("/api/coding-agent/state").status_code, 404)
            self.assertEqual(client.get("/api/hud-redesign/state").status_code, 404)
        finally:
            site.app.config.update(original)


class HostedLinkContractTestCase(unittest.TestCase):
    def test_public_pages_have_no_localhost_or_insecure_external_links(self):
        html_files = list(ROOT.glob("*.html")) + list((ROOT / "projects").glob("*.html"))
        violations = []
        for path in html_files:
            parser = PublicUrlParser()
            parser.feed(path.read_text(encoding="utf-8"))
            for value in parser.urls:
                parsed = urlsplit(value)
                if parsed.hostname in {"localhost", "127.0.0.1"} or parsed.port == 8020:
                    violations.append((path.name, value))
                if parsed.scheme == "http":
                    violations.append((path.name, value))
        self.assertEqual(violations, [])

    def test_public_showcase_uses_only_same_origin_api_requests(self):
        script = (ROOT / "alfred-showcase.js").read_text(encoding="utf-8")
        self.assertIn('const apiBase = "/api/alfred-showcase";', script)
        for forbidden in ("http://", "https://", "localhost", "127.0.0.1", "8020"):
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
