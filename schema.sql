PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 2 AND 80),
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    university TEXT NOT NULL,
    course TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT '',
    availability TEXT NOT NULL DEFAULT '',
    credits INTEGER NOT NULL DEFAULT 2 CHECK(credits >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    category TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('offer', 'want')),
    level TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, name, direction)
);

CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    requested_skill_id INTEGER NOT NULL,
    offered_skill_id INTEGER,
    mode TEXT NOT NULL CHECK(mode IN ('swap', 'credit')),
    message TEXT NOT NULL DEFAULT '',
    preferred_schedule TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'accepted', 'rejected', 'cancelled', 'completed')),
    requester_complete INTEGER NOT NULL DEFAULT 0 CHECK(requester_complete IN (0, 1)),
    recipient_complete INTEGER NOT NULL DEFAULT 0 CHECK(recipient_complete IN (0, 1)),
    credit_reserved INTEGER NOT NULL DEFAULT 0 CHECK(credit_reserved IN (0, 1)),
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (requested_skill_id) REFERENCES skills(id) ON DELETE RESTRICT,
    FOREIGN KEY (offered_skill_id) REFERENCES skills(id) ON DELETE RESTRICT,
    CHECK(requester_id != recipient_id),
    CHECK(
        (mode = 'swap' AND offered_skill_id IS NOT NULL)
        OR (mode = 'credit' AND offered_skill_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    reviewee_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewee_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK(reviewer_id != reviewee_id),
    UNIQUE(exchange_id, reviewer_id)
);

CREATE TABLE IF NOT EXISTS exchange_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 1000),
    created_at TEXT NOT NULL,
    FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_skills_user_direction
    ON skills(user_id, direction);
CREATE INDEX IF NOT EXISTS idx_skills_name_direction
    ON skills(name, direction);
CREATE INDEX IF NOT EXISTS idx_exchanges_recipient_status
    ON exchanges(recipient_id, status);
CREATE INDEX IF NOT EXISTS idx_exchanges_requester_status
    ON exchanges(requester_id, status);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewee
    ON reviews(reviewee_id);
CREATE INDEX IF NOT EXISTS idx_exchange_messages_exchange_created
    ON exchange_messages(exchange_id, created_at, id);
