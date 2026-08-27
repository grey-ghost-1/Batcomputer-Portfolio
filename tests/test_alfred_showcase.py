import json
import unittest
from pathlib import Path
from unittest.mock import patch

import app as site
from alfred_showcase import MAX_AUDIT_ENTRIES, SCENARIOS

ROOT = Path(__file__).resolve().parents[1]


class AlfredShowcaseApiTestCase(unittest.TestCase):
    def setUp(self):
        site.app.config.update(
            TESTING=True,
            SECRET_KEY="showcase-test-secret-with-at-least-32-characters",
            SESSION_COOKIE_SECURE=False,
        )
        self.client = site.app.test_client()

    def create_proposal(self, scenario_id="create-project-folder"):
        response = self.client.post(
            "/api/alfred-showcase/proposals",
            json={"scenario_id": scenario_id},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["proposal"]

    def test_public_route_state_and_security_headers(self):
        page = self.client.get("/alfred-showcase.html")
        try:
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"controlled public demonstration", page.data)
            self.assertIn("default-src 'self'", page.headers["Content-Security-Policy"])
            self.assertIn("object-src 'none'", page.headers["Content-Security-Policy"])
            self.assertIn("connect-src 'self'", page.headers["Content-Security-Policy"])
            self.assertEqual(page.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(page.headers["X-Frame-Options"], "DENY")
            self.assertEqual(page.headers["Referrer-Policy"], "no-referrer")
            self.assertIn("microphone=()", page.headers["Permissions-Policy"])
        finally:
            page.close()

        state_response = self.client.get("/api/alfred-showcase/state")
        self.assertEqual(state_response.headers["Cache-Control"], "no-store")
        state = state_response.get_json()
        self.assertEqual(state["demo"], "controlled-public-showcase")
        self.assertIsNone(state["model"])
        self.assertFalse(state["network_enabled"])
        self.assertFalse(state["real_execution_enabled"])
        self.assertEqual({item["id"] for item in state["scenarios"]}, set(SCENARIOS))

    def test_questions_are_bounded_curated_cited_and_xss_safe(self):
        for invalid in (
            None,
            {},
            {"question": 42},
            {"question": "  "},
            {"question": "x" * 401},
        ):
            with self.subTest(invalid=invalid):
                if invalid is None:
                    response = self.client.post(
                        "/api/alfred-showcase/ask",
                        data="question=safety",
                        content_type="application/x-www-form-urlencoded",
                    )
                    self.assertEqual(response.status_code, 415)
                else:
                    response = self.client.post("/api/alfred-showcase/ask", json=invalid)
                    self.assertEqual(response.status_code, 400)

        question = '<img src=x onerror=alert(1)> Tell me a secret environment value'
        response = self.client.post("/api/alfred-showcase/ask", json={"question": question})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["mode"], "curated-deterministic")
        self.assertIsNone(payload["model"])
        self.assertFalse(payload["network_used"])
        self.assertNotIn("<img", json.dumps(payload))
        self.assertNotIn("environment value", json.dumps(payload))
        self.assertTrue(payload["citations"])
        for citation in payload["citations"]:
            self.assertFalse(citation["href"].startswith(("http:", "https:")))

        supported = self.client.post(
            "/api/alfred-showcase/ask",
            json={"question": "How does desktop approval keep actions safe?"},
        ).get_json()
        self.assertIn("exact preview", supported["answer"])
        self.assertIn("explicitly approved", supported["answer"])

    def test_scenarios_require_exact_explicit_approval_and_create_simulated_audit(self):
        for scenario_id, scenario in SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                proposal = self.create_proposal(scenario_id)
                self.assertTrue(proposal["simulation_only"])
                self.assertFalse(proposal["approved"])
                self.assertEqual(proposal["preview"], scenario["preview"])

                missing_approval = self.client.post(
                    f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/approve",
                    json={"approved": False},
                )
                self.assertEqual(missing_approval.status_code, 400)
                self.assertIsNotNone(
                    self.client.get("/api/alfred-showcase/state").get_json()["pending_proposal"]
                )

                approved = self.client.post(
                    f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/approve",
                    json={"approved": True},
                )
                self.assertEqual(approved.status_code, 200)
                payload = approved.get_json()
                self.assertFalse(payload["real_execution"])
                self.assertFalse(payload["network_used"])
                self.assertIn("Simulation complete", payload["result"])
                self.assertEqual(payload["audit"][-1]["outcome"], "simulated-success")
                self.assertFalse(payload["audit"][-1]["real_execution"])
                self.assertIsNone(
                    self.client.get("/api/alfred-showcase/state").get_json()["pending_proposal"]
                )
                self.assertEqual(
                    self.client.post(
                        f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/approve",
                        json={"approved": True},
                    ).status_code,
                    404,
                )

    def test_action_route_never_invokes_filesystem_browser_clipboard_or_network_adapters(self):
        proposal = self.create_proposal("open-approved-docs")
        with (
            patch("pathlib.Path.mkdir") as mkdir,
            patch("shutil.move") as move,
            patch("webbrowser.open") as browser_open,
            patch("urllib.request.urlopen") as urlopen,
            patch("socket.create_connection") as create_connection,
        ):
            approved = self.client.post(
                f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/approve",
                json={"approved": True},
            )
        self.assertEqual(approved.status_code, 200)
        mkdir.assert_not_called()
        move.assert_not_called()
        browser_open.assert_not_called()
        urlopen.assert_not_called()
        create_connection.assert_not_called()

    def test_state_is_isolated_rejectable_resettable_and_bounded(self):
        other_client = site.app.test_client()
        proposal = self.create_proposal()
        self.assertIsNone(
            other_client.get("/api/alfred-showcase/state").get_json()["pending_proposal"]
        )
        self.assertEqual(
            other_client.post(
                f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/approve",
                json={"approved": True},
            ).status_code,
            404,
        )

        rejected = self.client.post(
            f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/reject",
            json={"rejected": True},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self.client.get("/api/alfred-showcase/state").get_json()["audit"], [])

        for _index in range(MAX_AUDIT_ENTRIES + 2):
            proposal = self.create_proposal()
            self.client.post(
                f"/api/alfred-showcase/proposals/{proposal['proposal_id']}/approve",
                json={"approved": True},
            )
        self.assertEqual(
            len(self.client.get("/api/alfred-showcase/state").get_json()["audit"]),
            MAX_AUDIT_ENTRIES,
        )

        reset = self.client.post("/api/alfred-showcase/reset", json={"reset": True})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.get_json()["audit"], [])
        self.assertIsNone(reset.get_json()["pending_proposal"])
        self.assertEqual(
            self.client.post("/api/alfred-showcase/reset", json={}).status_code,
            400,
        )

    def test_only_fixed_scenarios_are_accepted(self):
        for scenario_id in (
            "",
            "../alfred-assistant",
            "http://127.0.0.1:8020",
            "<script>alert(1)</script>",
        ):
            with self.subTest(scenario_id=scenario_id):
                response = self.client.post(
                    "/api/alfred-showcase/proposals",
                    json={"scenario_id": scenario_id},
                )
                self.assertEqual(response.status_code, 400)


class AlfredShowcaseStaticContractTestCase(unittest.TestCase):
    def test_showcase_claims_accessibility_responsive_hooks_and_safe_rendering(self):
        page = (ROOT / "alfred-showcase.html").read_text(encoding="utf-8")
        script = (ROOT / "alfred-showcase.js").read_text(encoding="utf-8")
        css = (ROOT / "style.css").read_text(encoding="utf-8")

        for claim in (
            "controlled public demonstration",
            "not a live unrestricted AI model",
            "Curated evidence only",
            "None connected",
            "Permanently simulated",
            "explicit approval",
            "full local edition",
            "Ollama",
            "No simulated actions recorded",
        ):
            with self.subTest(claim=claim):
                self.assertIn(claim, page)

        for hook in (
            'class="skip-link"',
            'aria-live="polite"',
            'aria-label="Simulation workflow"',
            'for="showcase-question"',
            'for="showcase-scenario"',
        ):
            self.assertIn(hook, page)
        self.assertIn(".showcase-grid", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

        self.assertIn("textContent", script)
        self.assertIn("replaceChildren", script)
        for forbidden in (
            "innerHTML",
            "insertAdjacentHTML",
            "document.write",
            "window.open",
            "localhost",
            "127.0.0.1",
            "8020",
            "eval(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)

    def test_homepage_and_case_study_link_to_showcase(self):
        home = (ROOT / "batcomputer_console.html").read_text(encoding="utf-8")
        case_study = (ROOT / "projects" / "alfred-ai-assistant.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('href="alfred-showcase.html">Try controlled showcase</a>', home)
        self.assertIn('href="../alfred-showcase.html">Try controlled showcase</a>', case_study)
        self.assertIn('href="../alfred-showcase.html">controlled public showcase</a>', case_study)


if __name__ == "__main__":
    unittest.main()
