DROP TABLE IF EXISTS password_reset;
DROP TABLE IF EXISTS notification;
DROP TABLE IF EXISTS grade;
DROP TABLE IF EXISTS assignment;
DROP TABLE IF EXISTS student;
DROP TABLE IF EXISTS course;
DROP TABLE IF EXISTS user;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  email TEXT UNIQUE,
  phone TEXT UNIQUE,
  is_admin INTEGER NOT NULL DEFAULT 0,
  last_login_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A class/course. Final grades weight the three assignment categories; the
-- weights are whole percentages that must add up to 100 (enforced in models.py).
CREATE TABLE course (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  term TEXT NOT NULL DEFAULT '',
  homework_weight INTEGER NOT NULL DEFAULT 40,
  quiz_weight INTEGER NOT NULL DEFAULT 20,
  exam_weight INTEGER NOT NULL DEFAULT 40,
  -- Letter-grade scale ('standard' or 'plus_minus') and the number of lowest-
  -- scoring assignments to drop from each category before averaging.
  grading_scale TEXT NOT NULL DEFAULT 'standard',
  drop_lowest_homework INTEGER NOT NULL DEFAULT 0,
  drop_lowest_quiz INTEGER NOT NULL DEFAULT 0,
  drop_lowest_exam INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (created_by) REFERENCES user (id)
);

-- A student is a person, independent of any course. student_id is the visible,
-- school-assigned identifier shown throughout the UI (distinct from the surrogate
-- primary key) and is globally unique, so one person has one identity even when
-- enrolled in several courses.
CREATE TABLE student (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A student's membership in a course. The same student can be enrolled in any
-- number of courses; each (course, student) pair is unique.
CREATE TABLE enrollment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (course_id, student_id),
  FOREIGN KEY (course_id) REFERENCES course (id) ON DELETE CASCADE,
  FOREIGN KEY (student_id) REFERENCES student (id) ON DELETE CASCADE
);

-- A graded item in a course. category is one of: homework | quiz | exam.
-- extra_credit assignments file under a category but are bonus: a student's earned
-- points add to that category's numerator without increasing its possible total.
CREATE TABLE assignment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id INTEGER NOT NULL,
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  max_points REAL NOT NULL,
  extra_credit INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (course_id) REFERENCES course (id) ON DELETE CASCADE
);

-- One student's score on one assignment. At most one row per (assignment, student).
CREATE TABLE grade (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  points REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (assignment_id, student_id),
  FOREIGN KEY (assignment_id) REFERENCES assignment (id) ON DELETE CASCADE,
  FOREIGN KEY (student_id) REFERENCES student (id) ON DELETE CASCADE
);

-- Audit log of notification attempts. grade_id/student_id are kept as plain
-- references (no FK) on purpose: a row is recorded even for a 'deleted' event,
-- after the grade has already been removed.
CREATE TABLE notification (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  grade_id INTEGER,
  student_id INTEGER,
  event TEXT NOT NULL,
  channel TEXT NOT NULL,
  recipient TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Single-use, time-limited password reset tokens. Only the SHA-256 hash of the
-- token is stored, so a database leak cannot produce a working reset link.
CREATE TABLE password_reset (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_enrollment_course ON enrollment (course_id);
CREATE INDEX idx_enrollment_student ON enrollment (student_id);
CREATE INDEX idx_assignment_course ON assignment (course_id, category);
CREATE INDEX idx_grade_assignment ON grade (assignment_id);
CREATE INDEX idx_grade_student ON grade (student_id);
CREATE INDEX idx_notification_created ON notification (id DESC);
CREATE INDEX idx_password_reset_token ON password_reset (token_hash);
