#!/usr/bin/env python3
"""
データベース初期化スクリプト
試験問題管理システム用

使用方法:
python init_database.py
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime

def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return salt + hash_obj.hexdigest()

def init_database(db_path: str = 'database.db'):
    """データベースを初期化"""
    
    # 既存のデータベースファイルがあれば削除
    if os.path.exists(db_path):
        print(f"既存のデータベースファイル {db_path} を削除します...")
        os.remove(db_path)
    
    print(f"新しいデータベース {db_path} を作成します...")
    
    # データベース接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 外部キー制約を有効化
        cursor.execute('PRAGMA foreign_keys = ON')
        
        print("テーブルを作成中...")
        
        # スキーマファイルを読み込んで実行
        with open('database_schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
            cursor.executescript(schema_sql)
        
        print("初期データを投入中...")
        
        # 初期データファイルを読み込んで実行
        with open('init_data.sql', 'r', encoding='utf-8') as f:
            init_sql = f.read()
            cursor.executescript(init_sql)
        
        # 管理者ユーザーのパスワードハッシュを更新
        print("管理者ユーザーのパスワードを設定中...")
        admin_password_hash = hash_password('admin123')
        staff_password_hash = hash_password('staff123')
        
        cursor.execute('''
            UPDATE Users SET password_hash = ? WHERE email = 'admin@keio.jp'
        ''', (admin_password_hash,))
        
        cursor.execute('''
            UPDATE Users SET password_hash = ? WHERE email = 'staff@keio.jp'
        ''', (staff_password_hash,))
        
        # サンプル学生ユーザーを追加
        student_users = [
            ('student1@keio.jp', 'student123', 'student', '慶應 太郎'),
            ('student2@keio.jp', 'student123', 'student', '三田 花子'),
        ]
        
        for email, password, user_type, full_name in student_users:
            password_hash = hash_password(password)
            cursor.execute('''
                INSERT OR IGNORE INTO Users (email, password_hash, user_type, full_name, is_active, email_verified)
                VALUES (?, ?, ?, ?, 1, 1)
            ''', (email, password_hash, user_type, full_name))
        
        # 教員ユーザーを追加
        faculty_users = [
            ('tanaka@keio.jp', 'faculty123', 'faculty', '田中 太郎'),
            ('sato@keio.jp', 'faculty123', 'faculty', '佐藤 花子'),
        ]
        
        for email, password, user_type, full_name in faculty_users:
            password_hash = hash_password(password)
            cursor.execute('''
                INSERT OR IGNORE INTO Users (email, password_hash, user_type, full_name, is_active, email_verified)
                VALUES (?, ?, ?, ?, 1, 1)
            ''', (email, password_hash, user_type, full_name))
        
        # 教員テーブルとユーザーテーブルを関連付け
        cursor.execute('''
            UPDATE Professors SET user_id = (
                SELECT user_id FROM Users WHERE email = 'tanaka@keio.jp'
            ) WHERE professor_name = '田中 太郎'
        ''')
        
        cursor.execute('''
            UPDATE Professors SET user_id = (
                SELECT user_id FROM Users WHERE email = 'sato@keio.jp'
            ) WHERE professor_name = '佐藤 花子'
        ''')
        
        conn.commit()
        
        print("✅ データベースの初期化が完了しました！")
        print()
        print("🔑 デフォルトユーザー:")
        print("   管理者: admin@keio.jp / admin123")
        print("   事務員: staff@keio.jp / staff123")
        print("   学生1: student1@keio.jp / student123")
        print("   学生2: student2@keio.jp / student123")
        print("   教員1: tanaka@keio.jp / faculty123")
        print("   教員2: sato@keio.jp / faculty123")
        print()
        
        # 統計情報を表示
        tables = ['Users', 'Faculties', 'Departments', 'Professors', 'Subjects', 'ExamTypes', 'Exams']
        print("📊 データベース統計:")
        for table in tables:
            count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
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
    
    # データベースファイルのパスを環境変数から取得
    db_path = os.environ.get('DATABASE_URL', 'database.db').replace('sqlite:///', '')
    
    try:
        init_database(db_path)
        print("=" * 50)
        print("🎉 初期化が正常に完了しました！")
        
    except FileNotFoundError as e:
        print(f"❌ SQLファイルが見つかりません: {e}")
        print("database_schema.sql と init_data.sql が同じディレクトリにあることを確認してください。")
        
    except Exception as e:
        print(f"❌ 予期しないエラーが発生しました: {e}")
        exit(1)