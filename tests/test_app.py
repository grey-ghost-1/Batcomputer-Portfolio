import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import app as site
from site_config import REPOSITORY_URL, SOURCE_REF, public_site_config

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
        self.assertEqual(payload["primary_projects"], list(site.PRIMARY_PROJECTS))
        self.assertEqual(payload["labs_count"], 20)
        self.assertEqual(payload["labs_page"], "labs.html")
        self.assertEqual(payload["evidence_inventory"], "project-evidence.json")
        self.assertEqual(payload["categories"], site.CATEGORY_PAGES)

    def test_public_site_config_omits_unknown_optional_values(self):
        with patch.dict(
            "os.environ",
            {
                "SITE_CONTACT_EMAIL": "",
                "SITE_LINKEDIN_URL": "not-a-url",
                "SITE_RESUME_PATH": "assets/missing.pdf",
                "SITE_PLATFORM_DEMO_URL": "http://insecure.example",
                "SITE_ORBITAL_DEMO_URL": "",
            },
            clear=False,
        ):
            response = self.client.get("/api/site/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "repository_url": REPOSITORY_URL,
                "source_ref": SOURCE_REF,
                "optional_links": [],
                "demos": {},
            },
        )

    def test_public_site_config_accepts_only_safe_existing_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "resume.pdf").write_bytes(b"%PDF-1.4\n")
            config = public_site_config(
                root,
                {
                    "SITE_CONTACT_EMAIL": "candidate@example.com",
                    "SITE_LINKEDIN_URL": "https://www.linkedin.com/in/candidate",
                    "SITE_RESUME_PATH": "assets/resume.pdf",
                    "SITE_PLATFORM_DEMO_URL": "https://platform.example.com",
                    "SITE_ORBITAL_DEMO_URL": "javascript:alert(1)",
                },
            )
        self.assertEqual(
            config["optional_links"],
            [
                {
                    "label": "Email",
                    "href": "mailto:candidate@example.com",
                    "kind": "email",
                },
                {
                    "label": "LinkedIn",
                    "href": "https://www.linkedin.com/in/candidate",
                    "kind": "linkedin",
                },
                {
                    "label": "Resume",
                    "href": "assets/resume.pdf",
                    "kind": "resume",
                },
            ],
        )
        self.assertEqual(config["demos"], {"platform": "https://platform.example.com"})

    def test_static_category_and_project_routes(self):
        self.assertEqual(self.get_status("/"), 200)
        self.assertEqual(self.get_status("/batcomputer_console.html"), 200)
        self.assertEqual(self.get_status("/labs.html"), 200)
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

    def test_homepage_is_recruiter_clear_and_flagship_first(self):
        parser = TextParser()
        parser.feed((ROOT / "batcomputer_console.html").read_text(encoding="utf-8"))
        normalized = " ".join(parser.text.split())
        for expected in (
            "ENTRY-LEVEL FULL-STACK / BACKEND SOFTWARE ENGINEER",
            "Python",
            "FastAPI",
            "PostgreSQL",
            "Batcomputer Operations Platform",
            "Orbital Data Lab",
            "Algorithms & Quality",
            "Labs & Prototypes",
            "20 retained learning prototypes",
            "No AI model",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, normalized)

        primary_position = normalized.index("Three production-style engineering case studies")
        labs_position = normalized.index("Learning archive")
        self.assertLess(primary_position, labs_position)

    def test_homepage_navigation_covers_six_categories_and_application(self):
        content = (ROOT / "batcomputer_console.html").read_text(encoding="utf-8")
        parser = LinkParser()
        parser.feed(content)
        expected_links = {
            "software_development.html",
            "projects/operations-platform.html",
            "projects/orbital-data-lab.html",
            "projects/algorithm-quality-lab.html",
            "cybersecurity.html",
            "network_software.html",
            "labs.html",
            "project-evidence.json",
            REPOSITORY_URL,
        }
        self.assertTrue(expected_links.issubset(set(parser.links)))
        self.assertIn('data-panel="contact"', content)

    def test_flagship_pages_have_complete_case_study_evidence(self):
        source_urls = {
            "operations-platform.html": (
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/platform"
            ),
            "orbital-data-lab.html": (
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/orbital-data-lab"
            ),
            "algorithm-quality-lab.html": (
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/algorithms-quality"
            ),
        }
        required_sections = (
            "Problem and users",
            "Implemented by me",
            "Architecture",
            "Trade-offs",
            "Run and verify",
            "Run from repository root",
            "Current Limitations",
            "Demo status",
        )
        for file_name, source_url in source_urls.items():
            with self.subTest(file_name=file_name):
                content = (ROOT / "projects" / file_name).read_text(encoding="utf-8")
                parser = TextParser()
                parser.feed(content)
                for section in required_sections:
                    self.assertIn(section, parser.text)
                self.assertIn(source_url, content)
                self.assertNotIn("fake screenshot", content.lower())

    def test_deployment_configuration_and_smoke_contract(self):
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_check.py").read_text(encoding="utf-8")

        for name in (
            "batcomputer-portfolio",
            "batcomputer-platform",
            "batcomputer-orbital",
        ):
            self.assertIn(f"name: {name}", render)
        for health_path in ("/api/health", "/health/live", "/health/ready"):
            self.assertIn(health_path, smoke)
        self.assertEqual(render.count("autoDeploy: false"), 3)
        self.assertIn("python -m alembic -c alembic.ini upgrade head", render)
        self.assertIn("ORBITAL_DATABASE_PATH", render)
        self.assertIn("site:", compose)
        self.assertIn("platform:", compose)
        self.assertIn("orbital:", compose)
        self.assertTrue((ROOT / "Dockerfile").is_file())
        self.assertTrue((ROOT / "platform" / "Dockerfile").is_file())
        self.assertTrue((ROOT / "orbital-data-lab" / "Dockerfile").is_file())
        self.assertIn("No service in this repository is claimed as currently deployed", deployment)
        self.assertIn("GitHub Pages", deployment)

    def test_labs_are_accurately_labeled_and_all_legacy_paths_remain(self):
        labs = (ROOT / "labs.html").read_text(encoding="utf-8")
        self.assertIn("Twenty small, runnable exercises", labs)
        self.assertIn("three primary case studies", labs)
        legacy_sources = [
            path
            for category in ("Cybersecurity", "IT Support", "Network", "Software Automation")
            for path in (ROOT / category).glob("*/main.py")
        ]
        self.assertEqual(len(legacy_sources), 20)
        legacy_pages = {
            project["page"]
            for project in self.evidence["projects"]
            if project["source_folder"]
            in {path.parent.relative_to(ROOT).as_posix() for path in legacy_sources}
        }
        self.assertEqual(len(legacy_pages), 20)
        self.assertTrue(all((ROOT / page).is_file() for page in legacy_pages))

    def test_accessibility_and_responsive_contracts_are_present(self):
        home = (ROOT / "batcomputer_console.html").read_text(encoding="utf-8")
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        self.assertIn('class="skip-link"', home)
        self.assertIn('aria-label="Six project categories"', home)
        self.assertIn('aria-live="polite"', home)
        self.assertIn("a:focus-visible", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("overflow-x: hidden", css)
        self.assertIn("@media (max-width: 720px)", css)

        html_files = list(ROOT.glob("*.html")) + list((ROOT / "projects").glob("*.html"))
        for path in html_files:
            content = path.read_text(encoding="utf-8")
            if "<img" in content:
                self.assertNotRegex(content, r"<img(?![^>]*\balt=)[^>]*>")

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
            "your email",
            "your linkedin",
            "your resume",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, content)


if __name__ == "__main__":
    unittest.main()
