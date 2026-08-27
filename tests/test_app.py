import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import app as site


ROOT = Path(__file__).resolve().parents[1]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"a", "link"} and attributes.get("href"):
            self.links.append(attributes["href"])
        if tag in {"img", "script"} and attributes.get("src"):
            self.links.append(attributes["src"])


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    @property
    def text(self):
        return " ".join(self.parts)


class AppTestCase(unittest.TestCase):
    def setUp(self):
        site.app.config.update(TESTING=True)
        site.CODE_PROPOSAL = None
        site.HUD_PROPOSAL = None
        site.RECENT_EVENTS.clear()
        self.client = site.app.test_client()

    def get_status(self, path):
        response = self.client.get(path)
        try:
            return response.status_code
        finally:
            response.close()

    def test_health_and_site_summary(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(
            health.get_json(),
            {"status": "ok", "service": "batcomputer-website", "projects": 23},
        )

        summary = self.client.get("/api/site/summary")
        self.assertEqual(summary.status_code, 200)
        payload = summary.get_json()
        self.assertEqual(payload["project_count"], 23)
        self.assertEqual(len(payload["projects"]), 23)
        self.assertEqual(payload["evidence_inventory"], "project-evidence.json")
        self.assertEqual(payload["categories"], site.CATEGORY_PAGES)

    def test_static_category_and_project_routes(self):
        self.assertEqual(self.get_status("/"), 200)
        self.assertEqual(self.get_status("/batcomputer_console.html"), 200)
        self.assertEqual(self.get_status("/project-evidence.json"), 200)

        for alias, file_name in site.CATEGORY_PAGES.items():
            with self.subTest(alias=alias):
                self.assertEqual(self.get_status(f"/{alias}"), 200)
                self.assertEqual(self.get_status(f"/{file_name}"), 200)

        for slug in site.project_inventory():
            with self.subTest(slug=slug):
                self.assertEqual(self.get_status(f"/projects/{slug}"), 200)
                self.assertEqual(self.get_status(f"/projects/{slug}.html"), 200)

    def test_missing_and_private_files_are_not_served(self):
        for path in (
            "/missing.html",
            "/projects/not-a-project",
            "/app.py",
            "/README.md",
            "/requirements.txt",
            "/Cybersecurity/network-scanner/main.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.get_status(path), 404)

    def test_traversal_attempts_are_rejected(self):
        for path in (
            "/../app.py",
            "/%2e%2e/app.py",
            "/projects/%2e%2e/%2e%2e/app.py",
            "/projects%5c..%5capp.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.get_status(path), 404)

    def test_alfred_requires_text_and_is_deterministic(self):
        self.assertEqual(self.client.post("/alfred", json={}).status_code, 400)
        self.assertEqual(self.client.post("/alfred", json={"message": "   "}).status_code, 400)
        self.assertEqual(self.client.post("/alfred", json={"message": []}).status_code, 400)

        first = self.client.post("/alfred", json={"message": "status"})
        second = self.client.post("/alfred", json={"message": "status"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), second.get_json())
        payload = first.get_json()
        self.assertEqual(payload["mode"], "deterministic")
        self.assertIsNone(payload["model"])
        self.assertFalse(payload["executes_actions"])
        self.assertIn("not an AI model", payload["reply"])

    def test_agent_state_is_review_only(self):
        response = self.client.get("/api/coding-agent/state")
        self.assertEqual(response.status_code, 200)
        state = response.get_json()
        self.assertFalse(state["available"])
        self.assertIsNone(state["model"])
        self.assertEqual(state["mode"], "deterministic-review-only")
        self.assertFalse(state["executes_actions"])
        self.assertFalse(state["writes_files"])

    def test_code_proposal_validation(self):
        invalid_payloads = (
            {},
            {"task": "Review", "target_file": ""},
            {"task": [], "target_file": "app.py"},
            {"task": "Review", "target_file": "../outside.py"},
            {"task": "Review", "target_file": "assets/header-skyline-transparent.png"},
            {"task": "Review", "target_file": "app.py", "context_files": "README.md"},
            {"task": "Review", "target_file": "app.py", "context_files": ["../outside.py"]},
            {"task": "x" * 2001, "target_file": "app.py"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/api/coding-agent/proposals", json=payload).status_code,
                    400,
                )

    def test_code_proposal_approval_and_rejection_do_not_write(self):
        original = (ROOT / "app.py").read_bytes()
        payload = {
            "task": "Review the route names",
            "target_file": "app.py",
            "context_files": ["README.md"],
        }
        created = self.client.post("/api/coding-agent/proposals", json=payload)
        self.assertEqual(created.status_code, 200)
        self.assertIn("No code was generated", created.get_json()["reply"])
        pending = created.get_json()["coding_agent"]["pending_code_change"]
        self.assertFalse(pending["executes_actions"])
        self.assertFalse(pending["writes_files"])

        approved = self.client.post("/api/coding-agent/proposals/approve")
        self.assertEqual(approved.status_code, 200)
        self.assertIn("No file was written", approved.get_json()["reply"])
        self.assertEqual((ROOT / "app.py").read_bytes(), original)
        self.assertIsNone(approved.get_json()["coding_agent"]["pending_code_change"])

        self.client.post("/api/coding-agent/proposals", json=payload)
        rejected = self.client.post("/api/coding-agent/proposals/reject")
        self.assertEqual(rejected.status_code, 200)
        self.assertIn("No file was written", rejected.get_json()["reply"])
        self.assertEqual((ROOT / "app.py").read_bytes(), original)
        self.assertEqual(self.client.post("/api/coding-agent/proposals/approve").status_code, 409)

    def test_hud_preview_approval_and_rejection_do_not_write(self):
        home = ROOT / "batcomputer_console.html"
        original = home.read_bytes()

        self.assertEqual(self.client.post("/api/hud-redesign/proposals", json={}).status_code, 400)
        self.assertEqual(
            self.client.post("/api/hud-redesign/proposals", json={"task": []}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/hud-redesign/proposals",
                json={"task": "x" * 2001},
            ).status_code,
            400,
        )

        created = self.client.post(
            "/api/hud-redesign/proposals",
            json={"task": "Review the homepage heading"},
        )
        self.assertEqual(created.status_code, 200)
        self.assertIn("No redesign was generated", created.get_json()["reply"])

        approved = self.client.post("/api/hud-redesign/proposals/approve")
        self.assertEqual(approved.status_code, 200)
        self.assertIn("No file was written", approved.get_json()["reply"])
        self.assertIn("final_content", approved.get_json())
        self.assertEqual(home.read_bytes(), original)

        self.client.post(
            "/api/hud-redesign/proposals",
            json={"task": "Review the homepage heading"},
        )
        rejected = self.client.post("/api/hud-redesign/proposals/reject")
        self.assertEqual(rejected.status_code, 200)
        self.assertNotIn("final_content", rejected.get_json())
        self.assertEqual(home.read_bytes(), original)
        self.assertEqual(self.client.post("/api/hud-redesign/proposals/reject").status_code, 409)


class StaticContentTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT / "project-evidence.json").read_text(encoding="utf-8"))

    def test_evidence_inventory_maps_all_pages_and_sources(self):
        projects = self.evidence["projects"]
        self.assertEqual(self.evidence["project_count"], 23)
        self.assertEqual(len(projects), 23)
        self.assertEqual(len({project["slug"] for project in projects}), 23)

        expected_pages = {path.relative_to(ROOT).as_posix() for path in (ROOT / "projects").glob("*.html")}
        inventory_pages = {project["page"] for project in projects}
        self.assertEqual(inventory_pages, expected_pages)

        for project in projects:
            with self.subTest(slug=project["slug"]):
                page = ROOT / project["page"]
                source = ROOT / project["source_folder"]
                self.assertTrue(page.is_file())
                entrypoint = ROOT / project.get("entrypoint", f"{project['source_folder']}/main.py")
                self.assertTrue(entrypoint.is_file())
                self.assertTrue((source / "README.md").is_file())
                self.assertTrue(project["run_command"])
                self.assertTrue(project["implemented_features"])
                self.assertTrue(project["limitations"])
                self.assertTrue(project["validation_status"].startswith("passed"))

                parser = TextParser()
                parser.feed(page.read_text(encoding="utf-8"))
                normalized_text = parser.text.replace("\\", "/")
                self.assertIn(project["source_folder"], normalized_text)
                self.assertIn("Implemented", parser.text)
                self.assertIn("Limitations", parser.text)
                self.assertIn("Run from repository root", parser.text)

    def test_all_local_html_links_resolve(self):
        html_files = list(ROOT.glob("*.html")) + list((ROOT / "projects").glob("*.html"))
        self.assertGreaterEqual(len(html_files), 27)

        broken = []
        for html_file in html_files:
            parser = LinkParser()
            parser.feed(html_file.read_text(encoding="utf-8"))
            for link in parser.links:
                parsed = urlsplit(link)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                decoded_path = unquote(parsed.path)
                target = (
                    ROOT / decoded_path.lstrip("/")
                    if decoded_path.startswith("/")
                    else html_file.parent / decoded_path
                ).resolve()
                try:
                    target.relative_to(ROOT)
                except ValueError:
                    broken.append((html_file.name, link, "outside repository"))
                    continue
                if not target.exists():
                    broken.append((html_file.name, link, "missing"))
        self.assertEqual(broken, [])

    def test_public_copy_has_no_known_placeholder_or_model_claims(self):
        public_files = (
            list(ROOT.glob("*.html"))
            + list((ROOT / "projects").glob("*.html"))
            + [ROOT / "README.md"]
        )
        content = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
        for unsupported in (
            "repository link placeholder",
            "Desktop\\Batcomputer",
            "Ollama-backed",
            "Embedded AI Assistant",
            "local-demo",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, content)


if __name__ == "__main__":
    unittest.main()
