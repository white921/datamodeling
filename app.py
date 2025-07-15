"""
試験問題管理システム

Flask + SQLite3を使用した試験問題管理Webアプリケーション
keio.jp限定メール認証システム
"""

import sqlite3
from typing import Final, Optional
import unicodedata
import os
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, redirect, render_template, request, url_for, flash, session
from werkzeug import Response

# 環境変数の読み込み
try:
    from dotenv import load_dotenv
    load_dotenv()  # .envファイルから環境変数を読み込み
    print("✅ .envファイルから環境変数を読み込みました")
except ImportError:
    print("ℹ️ python-dotenvがインストールされていません。環境変数は手動設定してください。")

# データベースのファイル名
DATABASE: Final[str] = os.environ.get('DATABASE_URL', 'database.db').replace('sqlite:///', '')

# Flask クラスのインスタンス
app = Flask(__name__)

# 設定
app.secret_key = os.environ.get('SECRET_KEY', 'exam_management_secret_key_2024')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_FILE_SIZE_MB', '10')) * 1024 * 1024

# ログ設定
import logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.environ.get('LOG_FILE', 'app.log')),
        logging.StreamHandler()
    ]
)

print(f"🚀 アプリケーション起動設定:")
print(f"   データベース: {DATABASE}")
print(f"   デバッグモード: {app.config['DEBUG']}")
print(f"   アップロードフォルダ: {app.config['UPLOAD_FOLDER']}")
print(f"   最大ファイルサイズ: {int(os.environ.get('MAX_FILE_SIZE_MB', '10'))}MB")
print(f"   認証方式: keio.jpメール・パスワード認証")

# 処理結果コードとメッセージ
RESULT_MESSAGES: Final[dict[str, str]] = {
    'exam-added': '試験を追加しました',
    'exam-updated': '試験情報を更新しました',
    'exam-deleted': '試験を削除しました',
    'subject-added': '科目を追加しました',
    'subject-updated': '科目情報を更新しました',
    'subject-deleted': '科目を削除しました',
    'professor-added': '教員を追加しました',
    'professor-updated': '教員情報を更新しました',
    'database-error': 'データベースエラーが発生しました',
    'invalid-input': '入力値に不正な文字が含まれています',
    'not-found': '指定されたデータが見つかりません',
    'access-denied': 'アクセスが拒否されました'
}

def validate_keio_email(email: str) -> bool:
    """keio.jpドメインのメールアドレスかチェック（厳密版）"""
    if not email:
        return False
    
    # 小文字に変換
    email = email.lower().strip()
    # 基本的なメール形式チェック
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    # keio.jpドメインのチェック
    if not re.match(email_pattern, email):
        return False
    domain = email.split('@')[1]
    return domain == 'keio.jp'

def get_db() -> sqlite3.Connection:
    """
    データベース接続を得る.

    Flask の g にデータベース接続が保存されていたらその接続を返す。
    そうでなければデータベース接続して g に保存しつつ接続を返す。
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.execute('PRAGMA foreign_keys = ON')  # 外部キー制約を有効化
        db.row_factory = sqlite3.Row  # カラム名でアクセスできるよう設定変更
    return db

@app.teardown_appcontext
def close_connection(exception: Optional[BaseException]) -> None:
    """
    データベース接続を閉じる.

    リクエスト処理の終了時に Flask が自動的に呼ぶ関数。
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def has_control_character(s: str) -> bool:
    """
    文字列に制御文字が含まれているか否か判定する.
    """
    return any(map(lambda c: unicodedata.category(c) == 'Cc', s))

def login_required(f):
    """ログイン必須デコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_session_valid():
            flash('ログインが必要です', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """管理者権限必須デコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_session_valid():
            flash('ログインが必要です', 'error')
            return redirect(url_for('index'))
        
        if session.get('user_type') != 'admin':
            flash('管理者権限が必要です', 'error')
            return redirect(url_for('home'))
        
        return f(*args, **kwargs)
    return decorated_function

def is_session_valid() -> bool:
    """セッションが有効かチェック"""
    if 'user_id' not in session:
        return False
    
    # セッション期限チェック（24時間）
    if 'login_time' in session:
        login_time = datetime.fromisoformat(session['login_time'])
        if datetime.now() - login_time > timedelta(hours=24):
            session.clear()
            return False
    
    return True

def record_login_attempt(email: str, success: bool, user_id: int = None, failure_reason: str = None):
    """ログイン試行を記録"""
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute('''
            INSERT INTO LoginAttempts (email, success, user_id, failure_reason, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, success, user_id, failure_reason, request.remote_addr, datetime.now()))
        con.commit()
    except Exception as e:
        print(f"Login attempt recording failed: {e}")

def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return salt + hash_obj.hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """パスワードを検証"""
    if len(password_hash) < 32:
        return False
    
    salt = password_hash[:32]
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return salt + hash_obj.hexdigest() == password_hash

def get_user_type_from_email(email: str) -> str:
    """メールアドレスからユーザータイプを推定"""
    if 'admin' in email.lower():
        return 'admin'
    elif 'staff' in email.lower():
        return 'staff'
    elif 'faculty' in email.lower():
        return 'faculty'
    else:
        return 'student'

# ===== 認証関連のルート =====

@app.route('/')
def index() -> str:
    """
    トップページ（ログインページ）.
    
    既にログインしている場合はホームページにリダイレクト
    未ログインの場合はログインページを表示
    """
    if is_session_valid():
        return redirect(url_for('home'))
    
    return render_template('auth/login.html')

@app.route('/login')
def login() -> str:
    """
    ログインページ（リダイレクト用）.
    
    /loginへのアクセスを/にリダイレクト
    """
    return redirect(url_for('login'))

@app.route('/login', methods=['POST'])
def login_execute() -> Response:
    """
    ログイン実行.
    
    メールアドレスとパスワードを検証してセッションを作成
    """
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    remember_me = request.form.get('remember_me') == 'on'
    
    # バリデーション
    if not email or not password:
        flash('メールアドレスとパスワードを入力してください', 'error')
        return redirect(url_for('login'))
    
    # keio.jpドメインチェック
    if not validate_keio_email(email):
        record_login_attempt(email, False, failure_reason='Invalid domain')
        flash('keio.jpドメインのメールアドレスを使用してください', 'error')
        return redirect(url_for('login'))
    
    # 制御文字チェック
    if has_control_character(email) or has_control_character(password):
        record_login_attempt(email, False, failure_reason='Control characters detected')
        flash('入力値に不正な文字が含まれています', 'error')
        return redirect(url_for('login'))
    
    try:
        con = get_db()
        cur = con.cursor()
        
        # ユーザー情報を取得
        user = cur.execute('''
            SELECT user_id, email, password_hash, user_type, full_name, is_active, email_verified
            FROM Users WHERE email = ?
        ''', (email,)).fetchone()
        
        if user is None:
            record_login_attempt(email, False, failure_reason='User not found')
            flash('メールアドレスまたはパスワードが正しくありません', 'error')
            return redirect(url_for('login'))
        
        # アカウント有効性チェック
        if not user['is_active']:
            record_login_attempt(email, False, user['user_id'], 'Account inactive')
            flash('アカウントが無効化されています。管理者にお問い合わせください', 'error')
            return redirect(url_for('login'))
        
        # メール認証チェック
        if not user['email_verified']:
            record_login_attempt(email, False, user['user_id'], 'Email not verified')
            flash('メールアドレスが未認証です。認証を完了してください', 'warning')
            return redirect(url_for('login'))
        
        # パスワード検証
        if not verify_password(password, user['password_hash']):
            record_login_attempt(email, False, user['user_id'], 'Wrong password')
            flash('メールアドレスまたはパスワードが正しくありません', 'error')
            return redirect(url_for('login'))
        
        # ログイン成功処理
        session.clear()
        session['user_id'] = user['user_id']
        session['email'] = user['email']
        session['user_type'] = user['user_type']
        session['full_name'] = user['full_name']
        session['login_time'] = datetime.now().isoformat()
        session['remember_me'] = remember_me
        
        # セッション期限設定
        if remember_me:
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=30)
        else:
            session.permanent = True
            app.permanent_session_lifetime = timedelta(hours=24)
        
        # 最終ログイン時刻を更新
        cur.execute('''
            UPDATE Users SET last_login_at = CURRENT_TIMESTAMP WHERE user_id = ?
        ''', (user['user_id'],))
        con.commit()
        
        # ログイン成功を記録
        record_login_attempt(email, True, user['user_id'])
        
        flash(f'ようこそ、{user["full_name"]}さん', 'success')
        
        # リダイレクト先を決定
        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        else:
            return redirect(url_for('home'))
            
    except sqlite3.Error as e:
        print(f"データベースエラー: {e}")
        record_login_attempt(email, False, failure_reason='Database error')
        flash('システムエラーが発生しました。しばらく後にお試しください', 'error')
        return redirect(url_for('index'))
    
    except Exception as e:
        print(f"予期しないエラー: {e}")
        record_login_attempt(email, False, failure_reason='Unexpected error')
        flash('予期しないエラーが発生しました', 'error')
        return redirect(url_for('index'))

@app.route('/register')
def register() -> str:
    """
    ユーザー登録ページ.
    
    既にログインしている場合はホームページにリダイレクト
    """
    if is_session_valid():
        return redirect(url_for('home'))
    
    return render_template('auth/register.html')

@app.route('/register', methods=['POST'])
def register_execute() -> Response:
    """
    ユーザー登録実行.
    
    新規ユーザーを登録して認証メールを送信（模擬）
    """
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    full_name = request.form.get('full_name', '').strip()
    user_type = request.form.get('user_type', '').strip()
    terms_agreed = request.form.get('terms_agreed') == 'on'
    
    # バリデーション
    if not all([email, password, confirm_password, full_name, user_type]):
        flash('すべての必須項目を入力してください', 'error')
        return redirect(url_for('register'))
    
    # 利用規約同意チェック
    if not terms_agreed:
        flash('利用規約に同意してください', 'error')
        return redirect(url_for('register'))
    
    # keio.jpドメインチェック
    if not validate_keio_email(email):
        flash('keio.jpドメインのメールアドレスを使用してください', 'error')
        return redirect(url_for('register'))
    
    # パスワード確認
    if password != confirm_password:
        flash('パスワードが一致しません', 'error')
        return redirect(url_for('register'))
    
    # パスワード強度チェック
    if len(password) < 8:
        flash('パスワードは8文字以上で入力してください', 'error')
        return redirect(url_for('register'))
    
    if not re.search(r'[A-Za-z]', password) or not re.search(r'[0-9]', password):
        flash('パスワードは英字と数字を含む必要があります', 'error')
        return redirect(url_for('register'))
    
    # 制御文字チェック
    if any(has_control_character(field) for field in [email, password, full_name]):
        flash('入力値に不正な文字が含まれています', 'error')
        return redirect(url_for('register'))
    
    # ユーザー種別チェック
    valid_user_types = ['student', 'faculty', 'staff']
    if user_type not in valid_user_types:
        flash('正しいユーザー種別を選択してください', 'error')
        return redirect(url_for('register'))
    
    # 氏名チェック
    if len(full_name) < 2 or len(full_name) > 50:
        flash('氏名は2文字以上50文字以下で入力してください', 'error')
        return redirect(url_for('register'))
    
    try:
        con = get_db()
        cur = con.cursor()
        
        # 既存ユーザーチェック
        existing_user = cur.execute('''
            SELECT user_id FROM Users WHERE email = ?
        ''', (email,)).fetchone()
        
        if existing_user:
            flash('このメールアドレスは既に登録されています', 'error')
            return redirect(url_for('register'))
        
        # パスワードハッシュ化
        password_hash = hash_password(password)
        
        # ユーザー登録
        cur.execute('''
            INSERT INTO Users (email, password_hash, user_type, full_name, is_active, email_verified)
            VALUES (?, ?, ?, ?, 1, 0)
        ''', (email, password_hash, user_type, full_name))
        
        user_id = cur.lastrowid
        
        # 教員の場合、Professorsテーブルにも追加
        if user_type == 'faculty':
            cur.execute('''
                INSERT INTO Professors (professor_name, user_id)
                VALUES (?, ?)
            ''', (full_name, user_id))
        
        con.commit()
        
        # 登録成功ログ
        print(f"新規ユーザー登録: {email} ({user_type}) - {full_name}")
        
        flash(f'ユーザー登録が完了しました。{email} に認証メールを送信しました（模擬）', 'success')
        flash('実際のシステムでは認証メールのリンクをクリックしてメール認証を完了してください', 'info')
        
        # 開発環境用: 自動的にメール認証済みにする
        if app.config['DEBUG']:
            cur.execute('''
                UPDATE Users SET email_verified = 1 WHERE user_id = ?
            ''', (user_id,))
            con.commit()
            flash('開発環境のため、メール認証を自動的に完了しました', 'info')
        
        return redirect(url_for('index'))
        
    except sqlite3.IntegrityError as e:
        con.rollback()
        print(f"データベース整合性エラー: {e}")
        flash('登録に失敗しました。メールアドレスが既に使用されている可能性があります', 'error')
        return redirect(url_for('register'))
    
    except sqlite3.Error as e:
        con.rollback()
        print(f"データベースエラー: {e}")
        flash('データベースエラーが発生しました', 'error')
        return redirect(url_for('register'))
    
    except Exception as e:
        con.rollback()
        print(f"予期しないエラー: {e}")
        flash('予期しないエラーが発生しました', 'error')
        return redirect(url_for('register'))

@app.route('/verify-email/<token>')
def verify_email(token: str) -> Response:
    """
    メール認証処理（将来実装用）.
    
    現在は模擬実装
    """
    flash('メール認証機能は今後実装予定です', 'info')
    return redirect(url_for('index'))

@app.route('/resend-verification')
@login_required
def resend_verification() -> Response:
    """
    認証メール再送信（将来実装用）.
    
    現在は模擬実装
    """
    flash('認証メール再送信機能は今後実装予定です', 'info')
    return redirect(url_for('profile'))

@app.route('/logout')
def logout() -> Response:
    """
    ログアウト.
    
    セッションをクリアしてトップページ（ログインページ）にリダイレクト
    """
    if 'user_id' in session:
        flash('ログアウトしました', 'info')
    
    session.clear()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile() -> str:
    """
    プロフィールページ.
    
    ログイン中のユーザー情報を表示
    """
    cur = get_db().cursor()
    
    # ユーザー情報を取得
    user = cur.execute('''
        SELECT user_id, email, user_type, full_name, last_login_at, created_at
        FROM Users WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # 最近のログイン履歴を取得
    login_history = cur.execute('''
        SELECT success, failure_reason, ip_address, timestamp
        FROM LoginAttempts 
        WHERE email = ? 
        ORDER BY timestamp DESC 
        LIMIT 10
    ''', (session['email'],)).fetchall()
    
    return render_template('auth/profile.html', user=user, login_history=login_history)

@app.route('/home')
@login_required
def home() -> str:
    """
    ホームページ（ログイン後のダッシュボード）.
    
    ログイン済みユーザー専用のホームページ
    """
    # 統計情報を取得
    stats = None
    try:
        cur = get_db().cursor()
        
        # 詳細な統計情報を取得
        total_exams = cur.execute('SELECT COUNT(*) FROM Exams').fetchone()[0]
        total_subjects = cur.execute('SELECT COUNT(*) FROM Subjects').fetchone()[0]
        total_professors = cur.execute('SELECT COUNT(*) FROM Professors').fetchone()[0]
        total_faculties = cur.execute('SELECT COUNT(*) FROM Faculties').fetchone()[0]
        
        # 最近の試験を取得
        recent_exams = cur.execute('''
            SELECT exam_id, 学部名, 学科名, 科目名, 試験種別, 年度
            FROM ExamDetailView 
            ORDER BY created_at DESC 
            LIMIT 5
        ''').fetchall()
        
        # ユーザー種別別の情報
        user_specific_info = None
        if session.get('user_type') == 'faculty':
            # 教員の場合：担当試験情報
            user_specific_info = cur.execute('''
                SELECT COUNT(*) as exam_count
                FROM ExamDetailView 
                WHERE 担当者 LIKE ?
            ''', (f'%{session.get("full_name")}%',)).fetchone()
        
        stats = {
            'exams': total_exams,
            'subjects': total_subjects,
            'professors': total_professors,
            'faculties': total_faculties,
            'recent_exams': recent_exams,
            'user_info': user_specific_info
        }
    except Exception as e:
        print(f"統計情報取得エラー: {e}")
        stats = None
    
    return render_template('home.html', stats=stats)

# ===== 既存のルート =====

@app.route('/exams')
@login_required
def exams() -> str:
    """
    試験一覧のページ（全件表示）.

    ExamDetailViewを使用して試験一覧を取得・表示
    """
    cur = get_db().cursor()

    # ExamDetailViewから全試験データを取得
    exam_list = cur.execute('''
        SELECT exam_id, 学部名, 学科名, 科目名, 試験種別, 年度, 担当者
        FROM ExamDetailView 
        ORDER BY 年度 DESC, 学部名, 学科名, 科目名
    ''').fetchall()

    return render_template('exams/list.html', exam_list=exam_list)

@app.route('/exams', methods=['POST'])
@login_required
def exams_filtered() -> str:
    """
    試験一覧のページ（絞り込み表示）.

    学部、学科、年度による絞り込み検索
    """
    con = get_db()
    cur = con.cursor()

    # フォームデータ取得
    faculty_filter = request.form.get('faculty_filter', '').strip()
    department_filter = request.form.get('department_filter', '').strip()
    year_filter = request.form.get('year_filter', '').strip()
    subject_filter = request.form.get('subject_filter', '').strip()

    # 動的なクエリ構築
    query = 'SELECT exam_id, 学部名, 学科名, 科目名, 試験種別, 年度, 担当者 FROM ExamDetailView WHERE 1=1'
    params = []

    if faculty_filter:
        query += ' AND 学部名 LIKE ?'
        params.append(f'%{faculty_filter}%')
    
    if department_filter:
        query += ' AND 学科名 LIKE ?'
        params.append(f'%{department_filter}%')
    
    if subject_filter:
        query += ' AND 科目名 LIKE ?'
        params.append(f'%{subject_filter}%')
    
    if year_filter:
        try:
            year = int(year_filter)
            query += ' AND 年度 = ?'
            params.append(year)
        except ValueError:
            flash('年度は数値で入力してください', 'error')
    
    query += ' ORDER BY 年度 DESC, 学部名, 学科名, 科目名'
    
    exam_list = cur.execute(query, params).fetchall()

    return render_template('exams/list.html', exam_list=exam_list, 
                         faculty_filter=faculty_filter, 
                         department_filter=department_filter,
                         year_filter=year_filter,
                         subject_filter=subject_filter)

@app.route('/exam/<int:exam_id>')
@login_required
def exam_detail(exam_id: int) -> str:
    """
    試験詳細ページ.

    指定された試験IDの詳細情報を表示
    """
    cur = get_db().cursor()

    # 試験詳細情報を取得
    exam = cur.execute('''
        SELECT * FROM ExamDetailView WHERE exam_id = ?
    ''', (exam_id,)).fetchone()

    if exam is None:
        flash('指定された試験が見つかりません', 'error')
        return redirect(url_for('exams'))

    # 試験問題画像一覧を取得
    questions = cur.execute('''
        SELECT question_id, picture FROM ExamQuestions WHERE exam_id = ?
    ''', (exam_id,)).fetchall()

    return render_template('exams/detail.html', exam=exam, questions=questions)

@app.route('/subjects')
@login_required
def subjects() -> str:
    """
    科目一覧のページ.

    学部・学科別に科目一覧を表示
    """
    cur = get_db().cursor()

    # 科目一覧を取得（学部・学科情報を含む）
    subject_list = cur.execute('''
        SELECT s.subject_id, f.faculty_name, d.department_name, s.subject_name,
               s.subject_type, s.semester, s.grade_level
        FROM Subjects s
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        ORDER BY f.faculty_name, d.department_name, s.grade_level, s.subject_name
    ''').fetchall()

    return render_template('subjects/list.html', subject_list=subject_list)

@app.route('/subject/<int:subject_id>')
@login_required
def subject_detail(subject_id: int) -> str:
    """
    科目詳細ページ.

    科目情報と関連する試験一覧を表示
    """
    cur = get_db().cursor()

    # 科目詳細情報を取得
    subject = cur.execute('''
        SELECT s.subject_id, f.faculty_name, d.department_name, s.subject_name,
               s.subject_type, s.semester, s.grade_level, s.created_at, s.updated_at
        FROM Subjects s
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        WHERE s.subject_id = ?
    ''', (subject_id,)).fetchone()

    if subject is None:
        flash('指定された科目が見つかりません', 'error')
        return redirect(url_for('subjects'))

    # この科目の試験一覧を取得
    exams = cur.execute('''
        SELECT exam_id, 試験種別, 年度, 注意事項, 担当者
        FROM ExamDetailView
        WHERE exam_id IN (SELECT exam_id FROM Exams WHERE subject_id = ?)
        ORDER BY 年度 DESC, 試験種別
    ''', (subject_id,)).fetchall()

    # この科目の担当教員一覧を取得
    professors = cur.execute('''
        SELECT p.professor_name, sp.assignment_year, sp.assignment_semester
        FROM SubjectProfessors sp
        JOIN Professors p ON sp.professor_id = p.professor_id
        WHERE sp.subject_id = ?
        ORDER BY sp.assignment_year DESC, sp.assignment_semester
    ''', (subject_id,)).fetchall()

    return render_template('subjects/detail.html', subject=subject, 
                         exams=exams, professors=professors)

@app.route('/professors')
@login_required
def professors() -> str:
    """
    教員一覧のページ.

    全教員の一覧を表示
    """
    cur = get_db().cursor()

    # 教員一覧を取得（担当科目数も含む）
    professor_list = cur.execute('''
        SELECT p.professor_id, p.professor_name,
               COUNT(DISTINCT sp.subject_id) as subject_count,
               COUNT(DISTINCT ep.exam_id) as exam_count
        FROM Professors p
        LEFT JOIN SubjectProfessors sp ON p.professor_id = sp.professor_id
        LEFT JOIN ExamProfessors ep ON p.professor_id = ep.professor_id
        GROUP BY p.professor_id, p.professor_name
        ORDER BY p.professor_name
    ''').fetchall()

    return render_template('professors/list.html', professor_list=professor_list)

@app.route('/professor/<int:professor_id>')
@login_required
def professor_detail(professor_id: int) -> str:
    """
    教員詳細ページ.

    教員情報と担当科目・試験一覧を表示
    """
    cur = get_db().cursor()

    # 教員基本情報を取得
    professor = cur.execute('''
        SELECT professor_id, professor_name FROM Professors WHERE professor_id = ?
    ''', (professor_id,)).fetchone()

    if professor is None:
        flash('指定された教員が見つかりません', 'error')
        return redirect(url_for('professors'))

    # 担当科目一覧を取得
    subjects = cur.execute('''
        SELECT s.subject_id, f.faculty_name, d.department_name, s.subject_name,
               sp.assignment_year, sp.assignment_semester
        FROM SubjectProfessors sp
        JOIN Subjects s ON sp.subject_id = s.subject_id
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        WHERE sp.professor_id = ?
        ORDER BY sp.assignment_year DESC, f.faculty_name, d.department_name, s.subject_name
    ''', (professor_id,)).fetchall()

    # 担当試験一覧を取得
    exams = cur.execute('''
        SELECT exam_id, 学部名, 学科名, 科目名, 試験種別, 年度
        FROM ExamDetailView
        WHERE exam_id IN (
            SELECT exam_id FROM ExamProfessors WHERE professor_id = ?
        )
        ORDER BY 年度 DESC, 学部名, 学科名, 科目名
    ''', (professor_id,)).fetchall()

    return render_template('professors/detail.html', professor=professor,
                         subjects=subjects, exams=exams)

@app.route('/exam-add')
@admin_required
def exam_add() -> str:
    """
    試験追加ページ.

    試験追加フォームを表示（科目・試験種別・教員の選択肢も取得）
    """
    cur = get_db().cursor()

    # 科目一覧を取得（学部・学科情報を含む）
    subjects = cur.execute('''
        SELECT s.subject_id, f.faculty_name, d.department_name, s.subject_name
        FROM Subjects s
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        ORDER BY f.faculty_name, d.department_name, s.subject_name
    ''').fetchall()

    # 試験種別一覧を取得
    exam_types = cur.execute('''
        SELECT exam_type_id, exam_type_name FROM ExamTypes ORDER BY exam_type_name
    ''').fetchall()

    # 教員一覧を取得
    professors = cur.execute('''
        SELECT professor_id, professor_name FROM Professors ORDER BY professor_name
    ''').fetchall()

    # 現在年度
    from datetime import datetime
    current_year = datetime.now().year

    return render_template('exams/add.html', 
                         subjects=subjects,
                         exam_types=exam_types, 
                         professors=professors,
                         current_year=current_year)

@app.route('/exam-add', methods=['POST'])
@admin_required
def exam_add_execute() -> Response:
    """
    試験追加実行.

    POST データを検証して新しい試験を追加
    """
    con = get_db()
    cur = con.cursor()

    # フォームデータ取得
    subject_id = request.form.get('subject_id')
    exam_type_id = request.form.get('exam_type_id')
    exam_year = request.form.get('exam_year')
    instructions = request.form.get('instructions', '').strip()
    professor_ids = request.form.getlist('professor_ids')

    # バリデーション
    try:
        subject_id = int(subject_id)
        exam_type_id = int(exam_type_id)
        exam_year = int(exam_year)
        professor_ids = [int(pid) for pid in professor_ids]
    except (ValueError, TypeError):
        flash('入力値に不正な値が含まれています', 'error')
        return redirect(url_for('exam_add'))

    if not professor_ids:
        flash('担当教員を少なくとも1人選択してください', 'error')
        return redirect(url_for('exam_add'))

    # 年度の妥当性チェック
    if exam_year < 2020 or exam_year > 2030:
        flash('年度は2020年から2030年の間で入力してください', 'error')
        return redirect(url_for('exam_add'))

    # 注意事項の制御文字チェック
    if has_control_character(instructions):
        flash('注意事項に制御文字が含まれています', 'error')
        return redirect(url_for('exam_add'))

    try:
        # トランザクション開始
        con.execute('BEGIN')

        # 同じ科目・試験種別・年度の組み合わせが既に存在するかチェック
        existing_exam = cur.execute('''
            SELECT exam_id FROM Exams 
            WHERE subject_id = ? AND exam_type_id = ? AND exam_year = ?
        ''', (subject_id, exam_type_id, exam_year)).fetchone()

        if existing_exam:
            flash('同じ科目・試験種別・年度の試験が既に存在します', 'error')
            con.rollback()
            return redirect(url_for('exam_add'))

        # 試験を追加
        cur.execute('''
            INSERT INTO Exams (subject_id, exam_type_id, exam_year, instructions, created_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (subject_id, exam_type_id, exam_year, instructions, session['user_id']))

        # 追加された試験のIDを取得
        exam_id = cur.lastrowid

        # 担当教員を追加
        for professor_id in professor_ids:
            cur.execute('''
                INSERT INTO ExamProfessors (exam_id, professor_id)
                VALUES (?, ?)
            ''', (exam_id, professor_id))

        # コミット
        con.commit()
        flash('試験を正常に追加しました', 'success')
        return redirect(url_for('exam_detail', exam_id=exam_id))

    except sqlite3.Error as e:
        con.rollback()
        print(f"データベースエラー: {e}")
        flash('データベースエラーが発生しました', 'error')
        return redirect(url_for('exam_add'))
    except Exception as e:
        con.rollback()
        print(f"予期しないエラー: {e}")
        flash('予期しないエラーが発生しました', 'error')
        return redirect(url_for('exam_add'))

@app.route('/statistics')
@login_required
def statistics() -> str:
    """
    統計情報ページ.

    集約関数を使用した各種統計情報を表示
    """
    cur = get_db().cursor()

    # 年度別試験数統計
    year_stats = cur.execute('''
        SELECT 年度, COUNT(*) as exam_count
        FROM ExamDetailView
        GROUP BY 年度
        ORDER BY 年度 DESC
    ''').fetchall()

    # 学部別試験数統計
    faculty_stats = cur.execute('''
        SELECT 学部名, COUNT(*) as exam_count
        FROM ExamDetailView
        GROUP BY 学部名
        ORDER BY exam_count DESC
    ''').fetchall()

    # 学科別試験数統計
    department_stats = cur.execute('''
        SELECT 学部名, 学科名, COUNT(*) as exam_count
        FROM ExamDetailView
        GROUP BY 学部名, 学科名
        ORDER BY 学部名, exam_count DESC
    ''').fetchall()

    # 試験種別統計
    exam_type_stats = cur.execute('''
        SELECT 試験種別, COUNT(*) as exam_count
        FROM ExamDetailView
        GROUP BY 試験種別
        ORDER BY exam_count DESC
    ''').fetchall()

    # 教員別担当試験数統計
    professor_stats = cur.execute('''
        SELECT 担当者, COUNT(*) as exam_count
        FROM ExamDetailView
        WHERE 担当者 IS NOT NULL
        GROUP BY 担当者
        ORDER BY exam_count DESC
    ''').fetchall()

    # 科目種別統計
    subject_type_stats = cur.execute('''
        SELECT subject_type, COUNT(*) as subject_count
        FROM Subjects
        WHERE subject_type IS NOT NULL
        GROUP BY subject_type
        ORDER BY subject_count DESC
    ''').fetchall()

    return render_template('statistics/dashboard.html',
                         year_stats=year_stats,
                         faculty_stats=faculty_stats,
                         department_stats=department_stats,
                         exam_type_stats=exam_type_stats,
                         professor_stats=professor_stats,
                         subject_type_stats=subject_type_stats)

@app.errorhandler(404)
def not_found_error(error):
    """404エラーハンドラ"""
    return render_template('error/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """500エラーハンドラ"""
    return render_template('error/500.html'), 500

if __name__ == '__main__':
    # このスクリプトを直接実行したらデバッグ用 Web サーバで起動する
    app.run(debug=True)