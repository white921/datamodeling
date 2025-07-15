-- 試験問題管理システム データベーススキーマ
-- SQLite3用

-- 外部キー制約を有効化
PRAGMA foreign_keys = ON;

-- ユーザーテーブル
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    user_type TEXT NOT NULL CHECK (user_type IN ('admin', 'staff', 'faculty', 'student')),
    full_name TEXT,
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    email_verified INTEGER DEFAULT 0 CHECK (email_verified IN (0, 1)),
    last_login_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ログイン試行履歴テーブル
CREATE TABLE IF NOT EXISTS LoginAttempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    user_id INTEGER,
    failure_reason TEXT,
    ip_address TEXT,
    user_agent TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL
);

-- 学部テーブル
CREATE TABLE IF NOT EXISTS Faculties (
    faculty_id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_name TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 学科テーブル
CREATE TABLE IF NOT EXISTS Departments (
    department_id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL,
    department_name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (faculty_id) REFERENCES Faculties(faculty_id) ON DELETE CASCADE,
    UNIQUE(faculty_id, department_name)
);

-- 教員テーブル
CREATE TABLE IF NOT EXISTS Professors (
    professor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    professor_name TEXT NOT NULL,
    user_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL
);

-- 科目テーブル
CREATE TABLE IF NOT EXISTS Subjects (
    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER NOT NULL,
    subject_name TEXT NOT NULL,
    subject_type TEXT CHECK (subject_type IN ('必修', '選択必修', '選択', '自由選択')),
    semester TEXT CHECK (semester IN ('春学期', '秋学期', '通年', '集中')),
    grade_level INTEGER CHECK (grade_level BETWEEN 1 AND 4),
    credits INTEGER DEFAULT 2,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES Departments(department_id) ON DELETE CASCADE
);

-- 試験種別テーブル
CREATE TABLE IF NOT EXISTS ExamTypes (
    exam_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_type_name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 試験テーブル
CREATE TABLE IF NOT EXISTS Exams (
    exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    exam_type_id INTEGER NOT NULL,
    exam_year INTEGER NOT NULL,
    instructions TEXT,
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id) ON DELETE CASCADE,
    FOREIGN KEY (exam_type_id) REFERENCES ExamTypes(exam_type_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    UNIQUE(subject_id, exam_type_id, exam_year)
);

-- 試験問題画像テーブル
CREATE TABLE IF NOT EXISTS ExamQuestions (
    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    picture TEXT NOT NULL,
    question_order INTEGER DEFAULT 1,
    uploaded_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES Exams(exam_id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES Users(user_id) ON DELETE SET NULL
);

-- 科目担当教員テーブル
CREATE TABLE IF NOT EXISTS SubjectProfessors (
    subject_professor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    professor_id INTEGER NOT NULL,
    assignment_year INTEGER NOT NULL,
    assignment_semester TEXT CHECK (assignment_semester IN ('春学期', '秋学期', '通年')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id) ON DELETE CASCADE,
    FOREIGN KEY (professor_id) REFERENCES Professors(professor_id) ON DELETE CASCADE,
    UNIQUE(subject_id, professor_id, assignment_year, assignment_semester)
);

-- 試験担当教員テーブル
CREATE TABLE IF NOT EXISTS ExamProfessors (
    exam_professor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    professor_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES Exams(exam_id) ON DELETE CASCADE,
    FOREIGN KEY (professor_id) REFERENCES Professors(professor_id) ON DELETE CASCADE,
    UNIQUE(exam_id, professor_id)
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_users_email ON Users(email);
CREATE INDEX IF NOT EXISTS idx_users_user_type ON Users(user_type);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON LoginAttempts(email);
CREATE INDEX IF NOT EXISTS idx_login_attempts_timestamp ON LoginAttempts(timestamp);
CREATE INDEX IF NOT EXISTS idx_exams_year ON Exams(exam_year);
CREATE INDEX IF NOT EXISTS idx_exams_subject ON Exams(subject_id);
CREATE INDEX IF NOT EXISTS idx_subjects_department ON Subjects(department_id);

-- ビュー：試験詳細情報
CREATE VIEW IF NOT EXISTS ExamDetailView AS
SELECT 
    e.exam_id,
    f.faculty_name AS 学部名,
    d.department_name AS 学科名,
    s.subject_name AS 科目名,
    et.exam_type_name AS 試験種別,
    e.exam_year AS 年度,
    e.instructions AS 注意事項,
    GROUP_CONCAT(p.professor_name, ', ') AS 担当者,
    e.created_at,
    e.updated_at
FROM Exams e
JOIN Subjects s ON e.subject_id = s.subject_id
JOIN Departments d ON s.department_id = d.department_id
JOIN Faculties f ON d.faculty_id = f.faculty_id
JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
LEFT JOIN ExamProfessors ep ON e.exam_id = ep.exam_id
LEFT JOIN Professors p ON ep.professor_id = p.professor_id
GROUP BY e.exam_id, f.faculty_name, d.department_name, s.subject_name, 
         et.exam_type_name, e.exam_year, e.instructions, e.created_at, e.updated_at;