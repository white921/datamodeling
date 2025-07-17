#!/usr/bin/env python3
"""
簡単なデータベース初期化スクリプト
試験問題管理システム用
"""

import sqlite3

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
                user_type TEXT NOT NULL DEFAULT 'user',
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
                subject_type TEXT CHECK (subject_type IN ('必修', '選択必修', '一般教養')),
                semester TEXT CHECK (semester IN ('春学期', '春学期前半', '春学期後半', '秋学期', '秋学期前半', '秋学期後半')),
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
        
        # 試験テーブル（created_byカラムとupdated_atカラムを追加）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Exams (
                exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                exam_type_id INTEGER NOT NULL,
                exam_year INTEGER NOT NULL,
                instructions TEXT,
                created_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id),
                FOREIGN KEY (exam_type_id) REFERENCES ExamTypes(exam_type_id),
                FOREIGN KEY (created_by) REFERENCES Users(user_id) ON DELETE SET NULL,
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
        
        # 初期ユーザー（シンプルなユーザーのみ）
        users = [
            ('user1@keio.jp', 'keio123', 'user', '田中 太郎'),
            ('user2@keio.jp', 'keio123', 'user', '佐藤 花子'),
            ('user3@keio.jp', 'keio123', 'user', '山田 次郎'),
            ('user4@keio.jp', 'keio123', 'user', '鈴木 美香'),
            ('user5@keio.jp', 'keio123', 'user', '高橋 一郎')
        ]
        
        for email, password_hash, user_type, full_name in users:
            cursor.execute('''
                INSERT OR IGNORE INTO Users (email, password_hash, user_type, full_name)
                VALUES (?, ?, ?, ?)
            ''', (email, password_hash, user_type, full_name))
        
        # 慶應義塾大学の全学部データ
        faculties = [
            '文学部', '経済学部', '法学部', '商学部', '医学部', '理工学部', 
            '総合政策学部', '環境情報学部', '看護医療学部', '薬学部'
        ]
        for faculty in faculties:
            cursor.execute('INSERT OR IGNORE INTO Faculties (faculty_name) VALUES (?)', (faculty,))
        
        # 慶應義塾大学の全学科データ（faculty_idを正確に参照）
        departments_data = [
            # 文学部 (faculty_id = 1)
            (1, '人文社会学科'),
            
            # 経済学部 (faculty_id = 2)
            (2, '経済学科'),
            
            # 法学部 (faculty_id = 3)
            (3, '法律学科'),
            (3, '政治学科'),
            
            # 商学部 (faculty_id = 4)
            (4, '商学科'),
            
            # 医学部 (faculty_id = 5)
            (5, '医学科'),
            
            # 理工学部 (faculty_id = 6)
            (6, '機械工学科'),
            (6, '電気情報工学科'),
            (6, '応用化学科'),
            (6, '物理情報工学科'),
            (6, '管理工学科'),
            (6, '数理科学科'),
            (6, '物理学科'),
            (6, '化学科'),
            (6, 'システムデザイン工学科'),
            (6, '情報工学科'),
            (6, '生命情報学科'),
            
            # 総合政策学部 (faculty_id = 7)
            (7, '総合政策学科'),
            
            # 環境情報学部 (faculty_id = 8)
            (8, '環境情報学科'),
            
            # 看護医療学部 (faculty_id = 9)
            (9, '看護学科'),
            
            # 薬学部 (faculty_id = 10)
            (10, '薬学科'),
            (10, '薬科学科')
        ]
        
        for faculty_id, dept_name in departments_data:
            cursor.execute('INSERT OR IGNORE INTO Departments (faculty_id, department_name) VALUES (?, ?)', 
                         (faculty_id, dept_name))
        
        # 教員データ（最小限のサンプルのみ）
        professors = [
            'サンプル教員1', 'サンプル教員2', 'サンプル教員3'
        ]
        for professor in professors:
            cursor.execute('INSERT OR IGNORE INTO Professors (professor_name) VALUES (?)', (professor,))
        
        # 試験種別
        exam_types = ['定期試験', '中間試験', '追試験', '再試験', '小テスト', 'レポート試験']
        for exam_type in exam_types:
            cursor.execute('INSERT OR IGNORE INTO ExamTypes (exam_type_name) VALUES (?)', (exam_type,))
        
        # コミットして、実際のIDを取得
        conn.commit()
        
        # 実際のdepartment_idを取得
        dept_ids = cursor.execute('SELECT department_id, department_name FROM Departments ORDER BY department_id').fetchall()
        print(f"作成された学科: {dept_ids}")
        
        # サンプル科目（各学部の代表的な科目）
        subjects = [
            # 文学部 人文社会学科
            (1, '哲学概論', '必修', '春学期', 1),
            (1, '日本史概説', '必修', '春学期前半', 1),
            (1, '英文学概論', '選択必修', '秋学期', 2),
            (1, '基礎英語', '一般教養', '春学期前半', 1),
            
            # 経済学部 経済学科
            (2, 'ミクロ経済学', '必修', '春学期', 1),
            (2, 'マクロ経済学', '必修', '秋学期', 1),
            (2, '計量経済学', '選択必修', '春学期後半', 3),
            (2, '数学基礎', '一般教養', '春学期前半', 1),
            
            # 法学部 法律学科
            (3, '憲法', '必修', '春学期', 1),
            (3, '民法', '必修', '秋学期', 2),
            (3, '刑法', '必修', '春学期後半', 2),
            (3, '法学入門', '一般教養', '春学期前半', 1),
            
            # 法学部 政治学科
            (4, '政治学原論', '必修', '春学期', 1),
            (4, '国際政治学', '選択必修', '秋学期前半', 2),
            (4, '現代社会論', '一般教養', '秋学期前半', 1),
            
            # 商学部 商学科
            (5, '商学総論', '必修', '春学期', 1),
            (5, '会計学', '必修', '秋学期', 1),
            (5, '経営学', '必修', '春学期後半', 2),
            (5, 'ビジネス英語', '一般教養', '春学期前半', 1),
            
            # 医学部 医学科
            (6, '解剖学', '必修', '春学期', 1),
            (6, '生理学', '必修', '秋学期', 1),
            (6, '病理学', '必修', '春学期後半', 2),
            (6, '医学倫理学', '一般教養', '春学期前半', 1),
            
            # 理工学部 機械工学科
            (7, '機械力学', '必修', '春学期', 2),
            (7, '材料力学', '必修', '秋学期', 2),
            (7, '熱力学', '必修', '春学期後半', 3),
            (7, '工学基礎数学', '一般教養', '春学期前半', 1),
            
            # 理工学部 電気情報工学科
            (8, '電気回路', '必修', '春学期', 1),
            (8, '電子回路', '必修', '秋学期', 2),
            (8, '信号処理', '選択必修', '春学期後半', 3),
            (8, '情報リテラシー', '一般教養', '春学期前半', 1),
            
            # 理工学部 情報工学科
            (16, 'プログラミング第1', '必修', '春学期', 1),
            (16, 'プログラミング第2', '必修', '秋学期', 1),
            (16, 'データ構造とアルゴリズム', '必修', '春学期', 2),
            (16, 'データベースシステム', '選択必修', '秋学期後半', 3),
            (16, 'コンピュータ概論', '一般教養', '春学期前半', 1),
            
            # 総合政策学部 総合政策学科
            (18, '総合政策学', '必修', '春学期', 1),
            (18, '政策分析', '選択必修', '秋学期後半', 2),
            (18, '社会科学入門', '一般教養', '春学期前半', 1),
            
            # 環境情報学部 環境情報学科
            (19, '情報基礎', '必修', '春学期', 1),
            (19, '環境学', '必修', '秋学期', 1),
            (19, 'メディア論', '一般教養', '秋学期前半', 1),
            
            # 看護医療学部 看護学科
            (20, '看護学概論', '必修', '春学期', 1),
            (20, '基礎看護技術', '必修', '秋学期', 1),
            (20, '人体の構造と機能', '一般教養', '春学期前半', 1),
            
            # 薬学部 薬学科
            (21, '薬学概論', '必修', '春学期', 1),
            (21, '有機化学', '必修', '秋学期', 1),
            (21, '薬事法規', '一般教養', '春学期前半', 1),
            
            # 薬学部 薬科学科
            (22, '薬科学概論', '必修', '春学期', 1),
            (22, '分析化学', '必修', '秋学期', 1),
            (22, '化学基礎', '一般教養', '春学期前半', 1)
        ]
        
        for subject in subjects:
            cursor.execute('''
                INSERT OR IGNORE INTO Subjects (department_id, subject_name, subject_type, semester, grade_level)
                VALUES (?, ?, ?, ?, ?)
            ''', subject)
        
        # コミットして、実際のsubject_idを取得
        conn.commit()
        
        # 実際のsubject_idを取得
        subject_ids = cursor.execute('SELECT subject_id, subject_name FROM Subjects ORDER BY subject_id').fetchall()
        print(f"作成された科目: {subject_ids}")
        
        # サンプル試験（各学部の代表的な科目の試験）- created_byを追加
        exams = [
            # 文学部 (user1が作成)
            (1, 1, 2024, '哲学概論の定期試験です。古代から現代までの哲学史を問います。', 1),
            (2, 1, 2024, '日本史概説の定期試験です。', 1),
            (3, 1, 2024, '英文学概論の定期試験です。', 1),
            
            # 経済学部 (user2が作成)
            (5, 1, 2024, 'ミクロ経済学の定期試験です。需要・供給曲線を中心に出題。', 2),
            (6, 1, 2024, 'マクロ経済学の定期試験です。', 2),
            (7, 1, 2024, '計量経済学の定期試験です。', 2),
            
            # 法学部 (user3が作成)
            (9, 1, 2024, '憲法の定期試験です。基本的人権を中心に出題。', 3),
            (10, 1, 2024, '民法の定期試験です。', 3),
            (11, 1, 2024, '刑法の定期試験です。', 3),
            (13, 1, 2024, '政治学原論の定期試験です。', 3),
            
            # 商学部 (user4が作成)
            (17, 1, 2024, '商学総論の定期試験です。', 4),
            (18, 1, 2024, '会計学の定期試験です。', 4),
            
            # 理工学部 (user5が作成)
            (37, 1, 2024, 'プログラミング第1の定期試験です。C言語の基礎を問います。', 5),
            (38, 1, 2024, 'プログラミング第2の定期試験です。', 5),
            (39, 1, 2024, 'データ構造とアルゴリズムの定期試験です。', 5),
            
            # 総合政策学部・環境情報学部 (user1が作成)
            (42, 1, 2024, '総合政策学の定期試験です。', 1),
            (45, 1, 2024, '情報基礎の定期試験です。', 1),
            
            # 看護医療学部・薬学部 (user2が作成)
            (48, 1, 2024, '看護学概論の定期試験です。', 2),
            (51, 1, 2024, '薬学概論の定期試験です。', 2)
        ]
        
        for exam in exams:
            cursor.execute('''
                INSERT OR IGNORE INTO Exams (subject_id, exam_type_id, exam_year, instructions, created_by)
                VALUES (?, ?, ?, ?, ?)
            ''', exam)
        
        # コミットして、実際のexam_idを取得
        conn.commit()
        
        # 実際のexam_idを取得
        exam_ids = cursor.execute('SELECT exam_id FROM Exams ORDER BY exam_id').fetchall()
        valid_exam_ids = [row[0] for row in exam_ids]
        print(f"作成された試験ID: {valid_exam_ids}")
        
        # 科目担当教員の割り当て（最小限のサンプルのみ）
        subject_professors = [
            # 基本的なサンプル割り当て
            (1, 1, 2024, '春学期'),        # 哲学概論 - サンプル教員1
            (5, 2, 2024, '春学期'),        # ミクロ経済学 - サンプル教員2
            (9, 3, 2024, '春学期'),        # 憲法 - サンプル教員3
            (37, 1, 2024, '春学期'),       # プログラミング第1 - サンプル教員1
        ]
        
        for subject_id, professor_id, year, semester in subject_professors:
            cursor.execute('''
                INSERT OR IGNORE INTO SubjectProfessors (subject_id, professor_id, assignment_year, assignment_semester)
                VALUES (?, ?, ?, ?)
            ''', (subject_id, professor_id, year, semester))
        
        # 試験担当教員の割り当て（最小限のサンプルのみ）
        exam_professors = [
            # 基本的なサンプル割り当て
            (1, 1),  # 哲学概論の試験 - サンプル教員1
            (4, 2),  # ミクロ経済学の試験 - サンプル教員2
            (7, 3),  # 憲法の試験 - サンプル教員3
        ]
        
        for exam_id, professor_id in exam_professors:
            if exam_id in valid_exam_ids:
                cursor.execute('''
                    INSERT OR IGNORE INTO ExamProfessors (exam_id, professor_id)
                    VALUES (?, ?)
                ''', (exam_id, professor_id))
        
        conn.commit()
        
        print("✅ データベースの初期化が完了しました！")
        print()
        print("🔑 デフォルトユーザー (すべて同じパスワード: keio123):")
        print("   user1@keio.jp / keio123 (田中 太郎)")
        print("   user2@keio.jp / keio123 (佐藤 花子)")
        print("   user3@keio.jp / keio123 (山田 次郎)")
        print("   user4@keio.jp / keio123 (鈴木 美香)")
        print("   user5@keio.jp / keio123 (高橋 一郎)")
        print()
        
        # 統計情報
        counts = {
            'Users': cursor.execute('SELECT COUNT(*) FROM Users').fetchone()[0],
            'Faculties': cursor.execute('SELECT COUNT(*) FROM Faculties').fetchone()[0],
            'Departments': cursor.execute('SELECT COUNT(*) FROM Departments').fetchone()[0],
            'Professors': cursor.execute('SELECT COUNT(*) FROM Professors').fetchone()[0],
            'Subjects': cursor.execute('SELECT COUNT(*) FROM Subjects').fetchone()[0],
            'Exams': cursor.execute('SELECT COUNT(*) FROM Exams').fetchone()[0],
            'ExamTypes': cursor.execute('SELECT COUNT(*) FROM ExamTypes').fetchone()[0]
        }
        
        print("📊 データ統計:")
        for table, count in counts.items():
            print(f"   {table}: {count}件")
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
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