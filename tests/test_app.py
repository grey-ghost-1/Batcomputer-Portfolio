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
        site.app.config.update(
            TESTING=True,
            PROPOSALS_ENABLED=True,
            SECRET_KEY="test-session-secret-with-at-least-32-characters",
            SESSION_COOKIE_SECURE=False,
        )
        self.client = site.app.test_client()

    def get_status(self, path):
        response = self.client.get(path)
        try:
            return response.status_code
        finally:
            response.close()

    def test_health_and_site_summary(self):
        public_health = self.client.get("/healthz")
        self.assertEqual(public_health.status_code, 200)
        self.assertEqual(public_health.get_json(), {"status": "ok"})
        self.assertEqual(public_health.headers["Cache-Control"], "no-store")

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
        self.assertEqual(payload["labs_count"], 19)
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
                "SITE_PUBLIC_SOURCE_URL": "https://[",
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
                    "SITE_PUBLIC_SOURCE_URL": "https://github.com/public/example/tree/main/",
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
        self.assertEqual(
            config["public_source_urls"]["orbital-data-lab"],
            "https://github.com/public/example/tree/main/orbital-data-lab",
        )
        self.assertEqual(
            config["public_source_urls"]["alfred-assistant"],
            "https://github.com/public/example/tree/main/alfred-assistant",
        )
        self.assertEqual(
            config["public_source_urls"][""],
            "https://github.com/public/example/tree/main",
        )

    def test_public_source_requires_an_appendable_github_tree_root(self):
        invalid_urls = (
            "https://github.com/owner/repository",
            "https://github.com/owner/repository/blob/main/README.md",
            "https://github.com/owner/repository/tree/main/subdirectory",
            "https://github.com/owner/repository/tree/main?token=secret",
            "https://github.com/owner/repository/tree/%2E%2E",
            "https://github.com/owner/repository/tree%2Fmain",
            "https://github.com/owner/repository/tree\\main\\subdirectory",
            "https://gitlab.com/owner/repository/tree/main",
            "https://[",
            "http://github.com/owner/repository/tree/main",
        )
        for invalid_url in invalid_urls:
            with self.subTest(invalid_url=invalid_url):
                config = public_site_config(
                    ROOT, {"SITE_PUBLIC_SOURCE_URL": invalid_url}
                )
                self.assertNotIn("public_source_urls", config)

    def test_static_category_and_project_routes(self):
        self.assertEqual(self.get_status("/"), 200)
        self.assertEqual(self.get_status("/batcomputer_console.html"), 200)
        self.assertEqual(self.get_status("/labs.html"), 200)
        self.assertEqual(self.get_status("/project-evidence.json"), 200)
        self.assertEqual(self.get_status("/ALFRED_STATUS.md"), 200)

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
        self.assertFalse(state["reads_repository_files"])
        self.assertNotIn("workspace_root", state)

    def test_proposals_are_disabled_by_default_and_require_strong_sessions(self):
        self.assertGreaterEqual(len(site.app.secret_key), 32)
        with self.assertRaisesRegex(RuntimeError, "at least 32"):
            site._session_secret({"SITE_SESSION_SECRET": "too-short"})
        with self.assertRaisesRegex(RuntimeError, "sufficient variety"):
            site._session_secret({"SITE_SESSION_SECRET": "x" * 64})

        site.app.config["PROPOSALS_ENABLED"] = False
        try:
            for method, path in (
                ("get", "/api/coding-agent/state"),
                ("post", "/api/coding-agent/proposals"),
                ("get", "/api/hud-redesign/state"),
                ("post", "/api/hud-redesign/proposals"),
            ):
                with self.subTest(path=path):
                    response = getattr(self.client, method)(path, json={})
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(
                        response.get_json(),
                        {"error": "Review-only proposals are disabled."},
                    )
        finally:
            site.app.config["PROPOSALS_ENABLED"] = True

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
        self.assertIn("No repository file was read", created.get_json()["reply"])
        pending = created.get_json()["coding_agent"]["pending_code_change"]
        self.assertFalse(pending["executes_actions"])
        self.assertFalse(pending["writes_files"])
        self.assertFalse(pending["reads_repository_files"])
        proposal_id = pending["proposal_id"]

        self.assertEqual(self.client.post("/api/coding-agent/proposals/approve").status_code, 405)
        approved = self.client.post(f"/api/coding-agent/proposals/{proposal_id}/approve")
        self.assertEqual(approved.status_code, 200)
        self.assertIn("No file was read or written", approved.get_json()["reply"])
        self.assertEqual((ROOT / "app.py").read_bytes(), original)
        self.assertIsNone(approved.get_json()["coding_agent"]["pending_code_change"])

        created = self.client.post("/api/coding-agent/proposals", json=payload)
        proposal_id = created.get_json()["coding_agent"]["pending_code_change"]["proposal_id"]
        rejected = self.client.post(f"/api/coding-agent/proposals/{proposal_id}/reject")
        self.assertEqual(rejected.status_code, 200)
        self.assertIn("No file was read or written", rejected.get_json()["reply"])
        self.assertEqual((ROOT / "app.py").read_bytes(), original)
        self.assertEqual(
            self.client.post(f"/api/coding-agent/proposals/{proposal_id}/approve").status_code,
            404,
        )

    def test_proposal_apis_never_disclose_repository_files(self):
        cases = {
            "app.py": "from flask import Flask",
            "README.md": "# Batcomputer Portfolio",
            "render.yaml": "batcomputer-platform-db",
            "site_config.py": "REPOSITORY_URL =",
            "platform/app/config.py": "DEVELOPMENT_SECRET =",
        }
        for target_file, private_marker in cases.items():
            with self.subTest(target_file=target_file):
                response = self.client.post(
                    "/api/coding-agent/proposals",
                    json={
                        "task": "Record a local review request",
                        "target_file": target_file,
                    },
                )
                self.assertEqual(response.status_code, 200)
                serialized = json.dumps(response.get_json())
                self.assertNotIn(private_marker, serialized)
                for forbidden_key in (
                    "old_preview",
                    "new_preview",
                    "full_content",
                    "workspace_root",
                ):
                    self.assertNotIn(forbidden_key, serialized)

        for blocked_path in (
            ".env",
            ".env.example",
            "../app.py",
            "platform/../app.py",
            "C:/repo/app.py",
            "projects\\..\\app.py",
        ):
            with self.subTest(blocked_path=blocked_path):
                response = self.client.post(
                    "/api/coding-agent/proposals",
                    json={"task": "Read a file", "target_file": blocked_path},
                )
                self.assertEqual(response.status_code, 400)

        hud_response = self.client.post(
            "/api/hud-redesign/proposals",
            json={"task": "Record a homepage review request"},
        )
        self.assertEqual(hud_response.status_code, 200)
        serialized_hud = json.dumps(hud_response.get_json())
        self.assertNotIn("JUSTIN WIMMER", serialized_hud)
        for forbidden_key in ("old_preview", "new_preview", "full_content", "workspace_root"):
            self.assertNotIn(forbidden_key, serialized_hud)

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
        self.assertIn("No repository file was read", created.get_json()["reply"])
        proposal_id = created.get_json()["pending_hud_redesign"]["proposal_id"]

        self.assertEqual(self.client.post("/api/hud-redesign/proposals/approve").status_code, 405)
        approved = self.client.post(f"/api/hud-redesign/proposals/{proposal_id}/approve")
        self.assertEqual(approved.status_code, 200)
        self.assertIn("No file was read or written", approved.get_json()["reply"])
        self.assertNotIn("final_content", approved.get_json())
        self.assertEqual(home.read_bytes(), original)

        created = self.client.post(
            "/api/hud-redesign/proposals",
            json={"task": "Review the homepage heading"},
        )
        proposal_id = created.get_json()["pending_hud_redesign"]["proposal_id"]
        rejected = self.client.post(f"/api/hud-redesign/proposals/{proposal_id}/reject")
        self.assertEqual(rejected.status_code, 200)
        self.assertNotIn("final_content", rejected.get_json())
        self.assertEqual(home.read_bytes(), original)
        self.assertEqual(
            self.client.post(f"/api/hud-redesign/proposals/{proposal_id}/reject").status_code,
            404,
        )

    def test_proposals_are_isolated_between_clients(self):
        client_a = site.app.test_client()
        client_b = site.app.test_client()
        code_payload = {
            "task": "Client A code review",
            "target_file": "app.py",
            "context_files": ["README.md"],
        }
        code_a = client_a.post("/api/coding-agent/proposals", json=code_payload)
        code_a_id = code_a.get_json()["coding_agent"]["pending_code_change"]["proposal_id"]
        self.assertIsNone(
            client_b.get("/api/coding-agent/state").get_json()["pending_code_change"]
        )

        code_b = client_b.post(
            "/api/coding-agent/proposals",
            json={**code_payload, "task": "Client B code review"},
        )
        code_b_id = code_b.get_json()["coding_agent"]["pending_code_change"]["proposal_id"]
        self.assertNotEqual(code_a_id, code_b_id)
        self.assertEqual(
            client_a.get("/api/coding-agent/state")
            .get_json()["pending_code_change"]["proposal_id"],
            code_a_id,
        )
        self.assertEqual(
            client_b.post(f"/api/coding-agent/proposals/{code_a_id}/reject").status_code,
            404,
        )
        self.assertEqual(
            client_a.get("/api/coding-agent/state")
            .get_json()["pending_code_change"]["proposal_id"],
            code_a_id,
        )
        self.assertEqual(
            client_a.post(f"/api/coding-agent/proposals/{code_a_id}/approve").status_code,
            200,
        )
        self.assertEqual(
            client_b.get("/api/coding-agent/state")
            .get_json()["pending_code_change"]["proposal_id"],
            code_b_id,
        )

        hud_a = client_a.post(
            "/api/hud-redesign/proposals", json={"task": "Client A homepage review"}
        )
        hud_a_id = hud_a.get_json()["pending_hud_redesign"]["proposal_id"]
        self.assertIsNone(client_b.get("/api/hud-redesign/state").get_json()["pending_hud_redesign"])
        hud_b = client_b.post(
            "/api/hud-redesign/proposals", json={"task": "Client B homepage review"}
        )
        hud_b_id = hud_b.get_json()["pending_hud_redesign"]["proposal_id"]
        self.assertNotEqual(hud_a_id, hud_b_id)
        self.assertEqual(
            client_b.post(f"/api/hud-redesign/proposals/{hud_a_id}/approve").status_code,
            404,
        )
        self.assertEqual(
            client_a.get("/api/hud-redesign/state")
            .get_json()["pending_hud_redesign"]["proposal_id"],
            hud_a_id,
        )
        self.assertEqual(
            client_a.post(f"/api/hud-redesign/proposals/{hud_a_id}/reject").status_code,
            200,
        )
        self.assertEqual(
            client_b.get("/api/hud-redesign/state")
            .get_json()["pending_hud_redesign"]["proposal_id"],
            hud_b_id,
        )

    def test_maximum_proposal_metadata_stays_within_cookie_limit(self):
        high_entropy_unicode = "".join(chr(0x4E00 + index) for index in range(2000))
        long_target = f"targets/{high_entropy_unicode[:220]}.py"
        contexts = [
            f"context/{index}/{high_entropy_unicode[index : index + 190]}.py"
            for index in range(20)
        ]
        cookie_lengths = []
        for _index in range(6):
            code_response = self.client.post(
                "/api/coding-agent/proposals",
                json={
                    "task": high_entropy_unicode,
                    "target_file": long_target,
                    "context_files": contexts,
                },
            )
            self.assertEqual(code_response.status_code, 200)
            cookie_lengths.append(len(code_response.headers["Set-Cookie"]))
            pending = code_response.get_json()["coding_agent"]["pending_code_change"]
            self.assertTrue(pending["metadata_truncated"])
            self.assertEqual(pending["context_file_count"], 20)
            self.assertEqual(len(pending["context_files"]), site.SESSION_CONTEXT_LIMIT)

            hud_response = self.client.post(
                "/api/hud-redesign/proposals",
                json={"task": high_entropy_unicode},
            )
            self.assertEqual(hud_response.status_code, 200)
            cookie_lengths.append(len(hud_response.headers["Set-Cookie"]))

        self.assertLess(
            max(cookie_lengths),
            min(site.app.config["MAX_COOKIE_SIZE"], 3500),
        )
        code_state = self.client.get("/api/coding-agent/state").get_json()
        hud_state = self.client.get("/api/hud-redesign/state").get_json()
        self.assertIsNotNone(code_state["pending_code_change"])
        self.assertIsNotNone(hud_state["pending_hud_redesign"])


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
            "Alfred AI Assistant",
            "Zion, showcased from the Batcomputer portfolio",
            "Community Aid Hub",
            "Health Navigator",
            "Humanitarian Automation Pipeline",
            "View Zion on GitHub",
            "Labs & Prototypes",
            "19 secondary learning prototypes",
            "No AI model",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, normalized)

        primary_position = normalized.index("Four production-style engineering case studies")
        zion_position = normalized.index("Zion, showcased from the Batcomputer portfolio")
        labs_position = normalized.index("Learning archive")
        self.assertLess(primary_position, labs_position)
        self.assertLess(primary_position, zion_position)
        self.assertLess(zion_position, labs_position)

    def test_homepage_navigation_covers_six_categories_and_application(self):
        content = (ROOT / "batcomputer_console.html").read_text(encoding="utf-8")
        parser = LinkParser()
        parser.feed(content)
        expected_links = {
            "software_development.html",
            "projects/operations-platform.html",
            "projects/orbital-data-lab.html",
            "projects/algorithm-quality-lab.html",
            "projects/alfred-ai-assistant.html",
            "cybersecurity.html",
            "network_software.html",
            "labs.html",
            "project-evidence.json",
        }
        self.assertTrue(expected_links.issubset(set(parser.links)))
        self.assertIn('data-panel="contact"', content)

    def test_flagship_pages_have_complete_case_study_evidence(self):
        source_paths = {
            "operations-platform.html": "platform",
            "orbital-data-lab.html": "orbital-data-lab",
            "algorithm-quality-lab.html": "algorithms-quality",
            "alfred-ai-assistant.html": "alfred-assistant",
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
        for file_name, source_path in source_paths.items():
            with self.subTest(file_name=file_name):
                content = (ROOT / "projects" / file_name).read_text(encoding="utf-8")
                parser = TextParser()
                parser.feed(content)
                for section in required_sections:
                    self.assertIn(section, parser.text)
                self.assertIn(f'data-public-source-path="{source_path}"', content)
                self.assertIn(f'href="{REPOSITORY_URL}/tree/{SOURCE_REF}/{source_path}"', content)
                self.assertNotIn("fake screenshot", content.lower())

    def test_flagship_cards_pair_local_evidence_with_public_source(self):
        home = (ROOT / "batcomputer_console.html").read_text(encoding="utf-8")
        flagship_links = {
            "View platform evidence": (
                "projects/operations-platform.html",
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/platform",
            ),
            "View orbital evidence": (
                "projects/orbital-data-lab.html",
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/orbital-data-lab",
            ),
            "View algorithms evidence": (
                "projects/algorithm-quality-lab.html",
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/algorithms-quality",
            ),
            "View Alfred evidence": (
                "projects/alfred-ai-assistant.html",
                f"{REPOSITORY_URL}/tree/{SOURCE_REF}/alfred-assistant",
            ),
        }
        client = site.app.test_client()
        for label, (path, source_url) in flagship_links.items():
            with self.subTest(label=label):
                self.assertIn(f'href="{path}">{label}</a>', home)
                self.assertIn(f'href="{source_url}">View source on GitHub</a>', home)
                response = client.get(f"/{path}")
                try:
                    self.assertEqual(response.status_code, 200)
                finally:
                    response.close()

        self.assertNotIn("Private GitHub source", home)
        self.assertIn("config.public_source_urls", (ROOT / "app.js").read_text(encoding="utf-8"))

    def test_deployment_configuration_and_smoke_contract(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_check.py").read_text(encoding="utf-8")

        for health_path in ("/api/health", "/health/live", "/health/ready"):
            self.assertIn(health_path, smoke)
        self.assertIn("site:", compose)
        self.assertIn("platform:", compose)
        self.assertIn("orbital:", compose)
        for field in (
            "PLATFORM_DATABASE_HOST",
            "PLATFORM_DATABASE_PORT",
            "PLATFORM_DATABASE_NAME",
            "PLATFORM_DATABASE_USER",
            "PLATFORM_DATABASE_PASSWORD",
        ):
            self.assertIn(field, compose)
        self.assertNotIn(
            "PLATFORM_DATABASE_URL: postgresql+psycopg://", compose
        )
        for site_setting in (
            "SITE_ENVIRONMENT",
            "SITE_PROPOSALS_ENABLED",
            "SITE_SESSION_SECRET",
            "SITE_CONTACT_EMAIL",
            "SITE_LINKEDIN_URL",
            "SITE_RESUME_PATH",
            "SITE_PLATFORM_DEMO_URL",
            "SITE_ORBITAL_DEMO_URL",
            "SITE_PUBLIC_SOURCE_URL",
        ):
            self.assertIn(site_setting, compose)
        self.assertTrue((ROOT / "Dockerfile").is_file())
        self.assertTrue((ROOT / "platform" / "Dockerfile").is_file())
        self.assertTrue((ROOT / "orbital-data-lab" / "Dockerfile").is_file())
        self.assertIn("No service in this repository is claimed as currently deployed", deployment)
        self.assertIn("GitHub Pages", deployment)

    def test_labs_are_accurately_labeled_and_all_legacy_paths_remain(self):
        labs = (ROOT / "labs.html").read_text(encoding="utf-8")
        self.assertIn("Nineteen small, runnable exercises", labs)
        self.assertIn("four primary case studies", labs)
        legacy_sources = [
            path
            for category in ("Cybersecurity", "IT Support", "Network", "Software Automation")
            for path in (ROOT / category).glob("*/main.py")
        ]
        self.assertEqual(len(legacy_sources), 20)
        retained_legacy_pages = {
            project["page"]
            for project in self.evidence["projects"]
            if project.get("legacy_source_folder", project["source_folder"])
            in {path.parent.relative_to(ROOT).as_posix() for path in legacy_sources}
        }
        self.assertEqual(len(retained_legacy_pages), 20)
        self.assertTrue(all((ROOT / page).is_file() for page in retained_legacy_pages))
        self.assertEqual(site.app.test_client().get("/api/site/summary").get_json()["labs_count"], 19)
        self.assertTrue((ROOT / "Software Automation" / "alfred-ai-assistant" / "main.py").is_file())

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
            + [ROOT / "README.md", ROOT / "app.js", ROOT / "alfred_agent.js"]
        )
        content = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
        for unsupported in (
            "repository link placeholder",
            "Desktop\\Batcomputer",
            "Ollama is enabled on every machine",
            "Embedded AI Assistant",
            "local-demo",
            "your email",
            "your linkedin",
            "your resume",
            "Load existing file previews",
            "Proposal Review tab",
            "review-only previews",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, content)


if __name__ == "__main__":
    unittest.main()
