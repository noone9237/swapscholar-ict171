import tempfile
import unittest
from pathlib import Path

from app import create_app, get_db, seed_demo_data


class SwapScholarTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "test.sqlite")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": self.database_path,
                "SESSION_COOKIE_SECURE": False,
            }
        )
        with self.app.app_context():
            seed_demo_data()
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf(self):
        with self.client.session_transaction() as session:
            session["_csrf_token"] = "test-csrf-token"
        return "test-csrf-token"

    def login(self, email, password="Demo123!"):
        return self.client.post(
            "/login",
            data={
                "_csrf_token": self.csrf(),
                "email": email,
                "password": password,
            },
            follow_redirects=True,
        )

    def logout(self):
        return self.client.post(
            "/logout",
            data={"_csrf_token": self.csrf()},
            follow_redirects=True,
        )

    def row(self, sql, params=()):
        with self.app.app_context():
            return get_db().execute(sql, params).fetchone()

    def test_public_pages_and_seed_data_render(self):
        home = self.client.get("/")
        browse = self.client.get("/browse?q=Python")
        statistics = self.client.get("/statistics")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Teach what you know", home.data)
        self.assertEqual(browse.status_code, 200)
        self.assertIn(b"Python programming", browse.data)
        self.assertEqual(statistics.status_code, 200)
        self.assertIn(b"SwapScholar by the numbers", statistics.data)

    def test_registration_hashes_password_and_starts_with_credits(self):
        response = self.client.post(
            "/register",
            data={
                "_csrf_token": self.csrf(),
                "name": "Test Student",
                "email": "student@example.com",
                "university": "Murdoch University",
                "password": "Secure123!",
                "confirm_password": "Secure123!",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Add a skill", response.data)
        user = self.row("SELECT * FROM users WHERE email = ?", ("student@example.com",))
        self.assertIsNotNone(user)
        self.assertNotEqual(user["password_hash"], "Secure123!")
        self.assertEqual(user["credits"], 2)

    def test_csrf_protects_post_routes(self):
        response = self.client.post(
            "/login",
            data={"email": "aisha@demo.swapscholar", "password": "Demo123!"},
        )
        self.assertEqual(response.status_code, 400)

    def test_add_skill_and_mutual_matches(self):
        response = self.login("aisha@demo.swapscholar")
        self.assertIn(b"Welcome back", response.data)
        response = self.client.post(
            "/skills",
            data={
                "_csrf_token": self.csrf(),
                "direction": "want",
                "name": "Public speaking",
                "category": "Communication",
                "level": "Beginner",
                "description": "Presentation confidence",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Public speaking was added", response.data)
        matches = self.client.get("/matches")
        self.assertEqual(matches.status_code, 200)
        self.assertIn(b"Omar Hassan", matches.data)

    def test_direct_swap_full_workflow_and_review(self):
        self.login("daniel@demo.swapscholar")
        excel_skill = self.row(
            """
            SELECT s.id FROM skills s JOIN users u ON u.id = s.user_id
            WHERE u.email = ? AND s.name = ? AND s.direction = 'offer'
            """,
            ("aisha@demo.swapscholar", "Excel"),
        )
        photoshop_skill = self.row(
            """
            SELECT s.id FROM skills s JOIN users u ON u.id = s.user_id
            WHERE u.email = ? AND s.name = ? AND s.direction = 'offer'
            """,
            ("daniel@demo.swapscholar", "Photoshop"),
        )
        response = self.client.post(
            f"/request/{excel_skill['id']}",
            data={
                "_csrf_token": self.csrf(),
                "mode": "swap",
                "offered_skill_id": photoshop_skill["id"],
                "preferred_schedule": "Thursday evening",
                "message": "Can we exchange these skills?",
            },
            follow_redirects=True,
        )
        self.assertIn(b"request has been sent", response.data)
        exchange = self.row(
            "SELECT * FROM exchanges ORDER BY id DESC LIMIT 1"
        )
        self.assertEqual(exchange["status"], "pending")

        self.logout()
        self.login("aisha@demo.swapscholar")
        response = self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "accept"},
            follow_redirects=True,
        )
        self.assertIn(b"Exchange accepted", response.data)
        response = self.client.post(
            f"/exchange/{exchange['id']}/messages",
            data={
                "_csrf_token": self.csrf(),
                "body": "Can we meet in the library at 2pm?",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Message sent to Daniel Kim", response.data)
        self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "complete"},
            follow_redirects=True,
        )

        self.logout()
        self.login("daniel@demo.swapscholar")
        response = self.client.get(f"/exchange/{exchange['id']}/messages")
        self.assertIn(b"Can we meet in the library at 2pm?", response.data)
        response = self.client.post(
            f"/exchange/{exchange['id']}/messages",
            data={
                "_csrf_token": self.csrf(),
                "body": "Yes, I will bring my laptop.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Message sent to Aisha Rahman", response.data)
        response = self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "complete"},
            follow_redirects=True,
        )
        self.assertIn(b"Exchange completed", response.data)
        self.assertEqual(
            self.row("SELECT status FROM exchanges WHERE id = ?", (exchange["id"],))[
                "status"
            ],
            "completed",
        )

        response = self.client.post(
            f"/exchange/{exchange['id']}/review",
            data={
                "_csrf_token": self.csrf(),
                "rating": "5",
                "comment": "Patient and very clear Python explanations.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"review for Aisha Rahman has been published", response.data)
        review = self.row(
            "SELECT * FROM reviews WHERE exchange_id = ? AND reviewer_id = ?",
            (exchange["id"], exchange["requester_id"]),
        )
        self.assertEqual(review["rating"], 5)
        self.assertEqual(
            self.row(
                "SELECT COUNT(*) AS total FROM exchange_messages WHERE exchange_id = ?",
                (exchange["id"],),
            )["total"],
            2,
        )

    def test_credit_is_reserved_then_transferred_after_both_confirm(self):
        self.login("mia@demo.swapscholar")
        requested_skill = self.row(
            """
            SELECT s.id FROM skills s JOIN users u ON u.id = s.user_id
            WHERE u.email = ? AND s.name = ? AND s.direction = 'offer'
            """,
            ("omar@demo.swapscholar", "Public speaking"),
        )
        self.client.post(
            f"/request/{requested_skill['id']}",
            data={
                "_csrf_token": self.csrf(),
                "mode": "credit",
                "message": "I would like presentation coaching.",
            },
            follow_redirects=True,
        )
        exchange = self.row("SELECT * FROM exchanges ORDER BY id DESC LIMIT 1")
        mia_before = self.row(
            "SELECT credits FROM users WHERE email = ?", ("mia@demo.swapscholar",)
        )["credits"]
        omar_before = self.row(
            "SELECT credits FROM users WHERE email = ?", ("omar@demo.swapscholar",)
        )["credits"]

        self.logout()
        self.login("omar@demo.swapscholar")
        self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "accept"},
            follow_redirects=True,
        )
        self.assertEqual(
            self.row(
                "SELECT credits FROM users WHERE email = ?", ("mia@demo.swapscholar",)
            )["credits"],
            mia_before - 1,
        )
        self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "complete"},
            follow_redirects=True,
        )
        self.assertEqual(
            self.row(
                "SELECT credits FROM users WHERE email = ?", ("omar@demo.swapscholar",)
            )["credits"],
            omar_before,
        )

        self.logout()
        self.login("mia@demo.swapscholar")
        self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "complete"},
            follow_redirects=True,
        )
        self.assertEqual(
            self.row(
                "SELECT credits FROM users WHERE email = ?", ("omar@demo.swapscholar",)
            )["credits"],
            omar_before + 1,
        )

    def test_unrelated_user_cannot_change_exchange(self):
        exchange = self.row(
            "SELECT id FROM exchanges WHERE status = 'pending' ORDER BY id LIMIT 1"
        )
        self.login("daniel@demo.swapscholar")
        response = self.client.post(
            f"/exchange/{exchange['id']}/action",
            data={"_csrf_token": self.csrf(), "action": "accept"},
        )
        self.assertEqual(response.status_code, 403)

    def test_private_chat_rejects_pending_and_unrelated_users(self):
        pending = self.row(
            "SELECT * FROM exchanges WHERE status = 'pending' ORDER BY id LIMIT 1"
        )
        requester = self.row(
            "SELECT email FROM users WHERE id = ?", (pending["requester_id"],)
        )
        self.login(requester["email"])
        response = self.client.get(f"/exchange/{pending['id']}/messages")
        self.assertEqual(response.status_code, 403)

        completed = self.row(
            "SELECT * FROM exchanges WHERE status = 'completed' ORDER BY id LIMIT 1"
        )
        outsider = self.row(
            """
            SELECT email FROM users
            WHERE id NOT IN (?, ?)
            ORDER BY id LIMIT 1
            """,
            (completed["requester_id"], completed["recipient_id"]),
        )
        self.logout()
        self.login(outsider["email"])
        response = self.client.get(f"/exchange/{completed['id']}/messages")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
