#!/usr/bin/env python3
"""
簡単なデータベース初期化スクリプト
試験問題管理システム用
"""

import sqlite3
import hashlib
import secrets

def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return salt + hash_obj.hexdigest()

def init_database():
    """データベースを初期化"""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # 外部キー制約を有効化
        cursor.execute('PRAGMA foreign_keys = ON')
        
        print("テーブルを作成中...")
        
        # ユーザーテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                user_type TEXT NOT NULL CHECK (user_type IN ('admin', 'staff', 'faculty', 'student')),
                full_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 学部テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Faculties (
                faculty_id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_name TEXT NOT NULL UNIQUE
            )
        ''')
        
        # 学科テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Departments (
                department_id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id INTEGER NOT NULL,
                department_name TEXT NOT NULL,
                FOREIGN KEY (faculty_id) REFERENCES Faculties(faculty_id),
                UNIQUE(faculty_id, department_name)
            )
        ''')
        
        # 教員テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Professors (
                professor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                professor_name TEXT NOT NULL
            )
        ''')
        
        # 科目テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Subjects (
                subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER NOT NULL,
                subject_name TEXT NOT NULL,
                subject_type TEXT CHECK (subject_type IN ('必修', '選択必修', '選択', '自由選択')),
                semester TEXT CHECK (semester IN ('春学期', '秋学期', '通年', '集中')),
                grade_level INTEGER CHECK (grade_level BETWEEN 1 AND 4),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_id) REFERENCES Departments(department_id)
            )
        ''')
        
        # 試験種別テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ExamTypes (
                exam_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_type_name TEXT NOT NULL UNIQUE
            )
        ''')
        
        # 試験テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Exams (
                exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                exam_type_id INTEGER NOT NULL,
                exam_year INTEGER NOT NULL,
                instructions TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id),
                FOREIGN KEY (exam_type_id) REFERENCES ExamTypes(exam_type_id),
                UNIQUE(subject_id, exam_type_id, exam_year)
            )
        ''')
        
        # 試験問題テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ExamQuestions (
                question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                picture TEXT,
                FOREIGN KEY (exam_id) REFERENCES Exams(exam_id)
            )
        ''')
        
        # 科目担当教員テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS SubjectProfessors (
                subject_id INTEGER NOT NULL,
                professor_id INTEGER NOT NULL,
                assignment_year INTEGER NOT NULL,
                assignment_semester TEXT NOT NULL,
                PRIMARY KEY (subject_id, professor_id, assignment_year, assignment_semester),
                FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id),
                FOREIGN KEY (professor_id) REFERENCES Professors(professor_id)
            )
        ''')
        
        # 試験担当教員テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ExamProfessors (
                exam_id INTEGER NOT NULL,
                professor_id INTEGER NOT NULL,
                PRIMARY KEY (exam_id, professor_id),
                FOREIGN KEY (exam_id) REFERENCES Exams(exam_id),
                FOREIGN KEY (professor_id) REFERENCES Professors(professor_id)
            )
        ''')
        
        # 試験詳細ビュー
        cursor.execute('''
            CREATE VIEW IF NOT EXISTS ExamDetailView AS
            SELECT 
                e.exam_id,
                f.faculty_name AS 学部名,
                d.department_name AS 学科名,
                s.subject_name AS 科目名,
                et.exam_type_name AS 試験種別,
                e.exam_year AS 年度,
                e.instructions AS 注意事項,
                GROUP_CONCAT(p.professor_name, ', ') AS 担当者
            FROM Exams e
            JOIN Subjects s ON e.subject_id = s.subject_id
            JOIN Departments d ON s.department_id = d.department_id
            JOIN Faculties f ON d.faculty_id = f.faculty_id
            JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
            LEFT JOIN ExamProfessors ep ON e.exam_id = ep.exam_id
            LEFT JOIN Professors p ON ep.professor_id = p.professor_id
            GROUP BY e.exam_id
        ''')
        
        print("初期データを投入中...")
        
        # 初期ユーザー
        admin_hash = hash_password('admin123')
        student_hash = hash_password('student123')
        
        cursor.execute('''
            INSERT OR IGNORE INTO Users (email, password_hash, user_type, full_name)
            VALUES (?, ?, ?, ?)
        ''', ('admin@keio.jp', admin_hash, 'admin', 'システム管理者'))
        
        cursor.execute('''
            INSERT OR IGNORE INTO Users (email, password_hash, user_type, full_name)
            VALUES (?, ?, ?, ?)
        ''', ('student@keio.jp', student_hash, 'student', '慶應 太郎'))
        
        # 学部データ
        faculties = ['理工学部', '文学部', '経済学部', '法学部', '商学部']
        for faculty in faculties:
            cursor.execute('INSERT OR IGNORE INTO Faculties (faculty_name) VALUES (?)', (faculty,))
        
        # 学科データ（理工学部のみ）
        cursor.execute('INSERT OR IGNORE INTO Departments (faculty_id, department_name) VALUES (1, ?)', ('情報工学科',))
        cursor.execute('INSERT OR IGNORE INTO Departments (faculty_id, department_name) VALUES (1, ?)', ('機械工学科',))
        cursor.execute('INSERT OR IGNORE INTO Departments (faculty_id, department_name) VALUES (1, ?)', ('電気情報工学科',))
        
        # 教員データ
        professors = ['田中 太郎', '佐藤 花子', '山田 次郎']
        for professor in professors:
            cursor.execute('INSERT OR IGNORE INTO Professors (professor_name) VALUES (?)', (professor,))
        
        # 試験種別
        exam_types = ['定期試験', '中間試験', '追試験', '小テスト']
        for exam_type in exam_types:
            cursor.execute('INSERT OR IGNORE INTO ExamTypes (exam_type_name) VALUES (?)', (exam_type,))
        
        # サンプル科目
        subjects = [
            (1, 'プログラミング第1', '必修', '春学期', 1),
            (1, 'プログラミング第2', '必修', '秋学期', 1),
            (1, 'データ構造とアルゴリズム', '必修', '春学期', 2),
            (1, 'データベースシステム', '選択必修', '秋学期', 3)
        ]
        
        for subject in subjects:
            cursor.execute('''
                INSERT OR IGNORE INTO Subjects (department_id, subject_name, subject_type, semester, grade_level)
                VALUES (?, ?, ?, ?, ?)
            ''', subject)
        
        # サンプル試験
        exams = [
            (1, 1, 2024, 'プログラミング第1の定期試験です。'),
            (2, 1, 2024, 'プログラミング第2の定期試験です。'),
            (3, 1, 2024, 'データ構造とアルゴリズムの定期試験です。'),
            (4, 1, 2023, 'データベースシステムの定期試験です。')
        ]
        
        for exam in exams:
            cursor.execute('''
                INSERT OR IGNORE INTO Exams (subject_id, exam_type_id, exam_year, instructions)
                VALUES (?, ?, ?, ?)
            ''', exam)
        
        conn.commit()
        
        print("✅ データベースの初期化が完了しました！")
        print()
        print("🔑 デフォルトユーザー:")
        print("   管理者: admin@keio.jp / admin123")
        print("   学生: student@keio.jp / student123")
        print()
        
        # 統計情報
        counts = {
            'Users': cursor.execute('SELECT COUNT(*) FROM Users').fetchone()[0],
            'Faculties': cursor.execute('SELECT COUNT(*) FROM Faculties').fetchone()[0],
            'Departments': cursor.execute('SELECT COUNT(*) FROM Departments').fetchone()[0],
            'Subjects': cursor.execute('SELECT COUNT(*) FROM Subjects').fetchone()[0],
            'Exams': cursor.execute('SELECT COUNT(*) FROM Exams').fetchone()[0]
        }
        
        print("📊 データ統計:")
        for table, count in counts.items():
            print(f"   {table}: {count}件")
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.close()

if __name__ == '__main__':
    print("🚀 試験問題管理システム データベース初期化")
    print("=" * 50)
    init_database()
    print("=" * 50)
    print("🎉 初期化完了！app.pyを実行してシステムを開始してください。")