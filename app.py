#!/usr/keio/Anaconda3-2024.10-1/bin/python
"""
試験問題管理システム Web アプリケーション

シンプルな認証システムを持つ試験問題管理システム
"""

import sqlite3
from typing import Final, Optional
import unicodedata
import hashlib
import secrets
from datetime import datetime
from functools import wraps

from flask import Flask, g, redirect, render_template, request, url_for, flash, session
from werkzeug import Response

# データベースのファイル名
DATABASE: Final[str] = 'database.db'

# Flask クラスのインスタンス
app = Flask(__name__)
app.secret_key = 'exam_management_secret_key_2024'

# 処理結果コードとメッセージ
RESULT_MESSAGES: Final[dict[str, str]] = {
    'exam-added': '試験を追加しました',
    'exam-updated': '試験を更新しました',
    'exam-deleted': '試験を削除しました',
    'subject-added': '科目を追加しました',
    'database-error': 'データベースエラーが発生しました',
    'login-success': 'ログインしました',
    'logout-success': 'ログアウトしました',
    'register-success': 'ユーザー登録が完了しました',
    'invalid-credentials': 'メールアドレスまたはパスワードが正しくありません',
    'email-exists': 'このメールアドレスは既に登録されています'
}

def get_db() -> sqlite3.Connection:
    """データベース接続を得る"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.execute('PRAGMA foreign_keys = ON')
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception: Optional[BaseException]) -> None:
    """データベース接続を閉じる"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

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

def login_required(f):
    """ログイン必須デコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def has_control_character(s: str) -> bool:
    """文字列に制御文字が含まれているか判定"""
    return any(map(lambda c: unicodedata.category(c) == 'Cc', s))

# ===== 認証関連のルート =====

@app.route('/')
def index() -> Response:
    """トップページ - ログインページにリダイレクト"""
    if 'user_id' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/login')
def login() -> str:
    """ログインページ"""
    if 'user_id' in session:
        return redirect(url_for('home'))
    return render_template('auth/login.html')

@app.route('/login', methods=['POST'])
def login_execute() -> Response:
    """ログイン実行"""
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    if not email or not password:
        flash('メールアドレスとパスワードを入力してください', 'error')
        return redirect(url_for('login'))
    
    # keio.jpドメインチェック
    if not email.endswith('@keio.jp'):
        flash('keio.jpドメインのメールアドレスを使用してください', 'error')
        return redirect(url_for('login'))
    
    try:
        con = get_db()
        cur = con.cursor()
        
        user = cur.execute('''
            SELECT user_id, email, password_hash, user_type, full_name
            FROM Users WHERE email = ?
        ''', (email,)).fetchone()
        
        if user is None or not verify_password(password, user['password_hash']):
            flash('メールアドレスまたはパスワードが正しくありません', 'error')
            return redirect(url_for('login'))
        
        # ログイン成功
        session['user_id'] = user['user_id']
        session['email'] = user['email']
        session['user_type'] = user['user_type']
        session['full_name'] = user['full_name']
        session['login_time'] = datetime.now().isoformat()
        
        flash(f'ようこそ、{user["full_name"]}さん', 'success')
        return redirect(url_for('home'))
        
    except sqlite3.Error:
        flash('データベースエラーが発生しました', 'error')
        return redirect(url_for('login'))

@app.route('/register')
def register() -> str:
    """ユーザー登録ページ"""
    if 'user_id' in session:
        return redirect(url_for('home'))
    return render_template('auth/register.html')

@app.route('/register', methods=['POST'])
def register_execute() -> Response:
    """ユーザー登録実行"""
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    full_name = request.form.get('full_name', '').strip()
    user_type = request.form.get('user_type', 'student')
    
    # バリデーション
    if not all([email, password, confirm_password, full_name]):
        flash('すべての項目を入力してください', 'error')
        return redirect(url_for('register'))
    
    if not email.endswith('@keio.jp'):
        flash('keio.jpドメインのメールアドレスを使用してください', 'error')
        return redirect(url_for('register'))
    
    if password != confirm_password:
        flash('パスワードが一致しません', 'error')
        return redirect(url_for('register'))
    
    if len(password) < 6:
        flash('パスワードは6文字以上で入力してください', 'error')
        return redirect(url_for('register'))
    
    if has_control_character(full_name):
        flash('名前に制御文字は使用できません', 'error')
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
        
        # ユーザー登録
        password_hash = hash_password(password)
        cur.execute('''
            INSERT INTO Users (email, password_hash, user_type, full_name)
            VALUES (?, ?, ?, ?)
        ''', (email, password_hash, user_type, full_name))
        con.commit()
        
        flash('ユーザー登録が完了しました。ログインしてください', 'success')
        return redirect(url_for('login'))
        
    except sqlite3.Error:
        flash('データベースエラーが発生しました', 'error')
        return redirect(url_for('register'))

@app.route('/logout')
def logout() -> Response:
    """ログアウト"""
    session.clear()
    flash('ログアウトしました', 'info')
    return redirect(url_for('login'))

# ===== メイン機能のルート =====

@app.route('/home')
@login_required
def home() -> str:
    """ホームページ"""
    try:
        cur = get_db().cursor()
        
        # 統計情報を取得
        total_exams = cur.execute('SELECT COUNT(*) FROM Exams').fetchone()[0]
        total_subjects = cur.execute('SELECT COUNT(*) FROM Subjects').fetchone()[0]
        total_professors = cur.execute('SELECT COUNT(*) FROM Professors').fetchone()[0]
        total_faculties = cur.execute('SELECT COUNT(*) FROM Faculties').fetchone()[0]
        
        stats = {
            'exams': total_exams,
            'subjects': total_subjects,
            'professors': total_professors,
            'faculties': total_faculties
        }
    except:
        stats = None
    
    return render_template('home.html', stats=stats)

@app.route('/exams')
@login_required
def exams() -> str:
    """試験一覧のページ"""
    cur = get_db().cursor()
    
    exam_list = cur.execute('''
        SELECT exam_id, 学部名, 学科名, 科目名, 試験種別, 年度, 担当者
        FROM ExamDetailView 
        ORDER BY 年度 DESC, 学部名, 学科名, 科目名
    ''').fetchall()
    
    return render_template('exams/list.html', exam_list=exam_list)

@app.route('/exams', methods=['POST'])
@login_required
def exams_filtered() -> str:
    """試験一覧のページ（絞り込み）"""
    con = get_db()
    cur = con.cursor()
    
    faculty_filter = request.form.get('faculty_filter', '').strip()
    department_filter = request.form.get('department_filter', '').strip()
    year_filter = request.form.get('year_filter', '').strip()
    subject_filter = request.form.get('subject_filter', '').strip()
    
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
    """試験詳細ページ"""
    cur = get_db().cursor()
    
    exam = cur.execute('''
        SELECT * FROM ExamDetailView WHERE exam_id = ?
    ''', (exam_id,)).fetchone()
    
    if exam is None:
        flash('指定された試験が見つかりません', 'error')
        return redirect(url_for('exams'))
    
    questions = cur.execute('''
        SELECT question_id, picture FROM ExamQuestions WHERE exam_id = ?
    ''', (exam_id,)).fetchall()
    
    return render_template('exams/detail.html', exam=exam, questions=questions)

@app.route('/exam-add')
@login_required
def exam_add() -> str:
    """試験追加ページ"""
    cur = get_db().cursor()
    
    # 科目一覧を取得
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
@login_required
def exam_add_execute() -> Response:
    """試験追加実行"""
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
        professor_ids = [int(pid) for pid in professor_ids if pid]
    except (ValueError, TypeError):
        flash('入力値に不正な値が含まれています', 'error')
        return redirect(url_for('exam_add'))
    
    if not professor_ids:
        flash('担当教員を少なくとも1人選択してください', 'error')
        return redirect(url_for('exam_add'))
    
    # 年度の妥当性チェック
    if exam_year < 2000 or exam_year > 2025:
        flash('年度は2000年から2025年の間で入力してください', 'error')
        return redirect(url_for('exam_add'))
    
    # 制御文字チェック
    if has_control_character(instructions):
        flash('注意事項に制御文字が含まれています', 'error')
        return redirect(url_for('exam_add'))
    
    try:
        # 同じ科目・試験種別・年度の組み合わせが既に存在するかチェック
        existing_exam = cur.execute('''
            SELECT exam_id FROM Exams 
            WHERE subject_id = ? AND exam_type_id = ? AND exam_year = ?
        ''', (subject_id, exam_type_id, exam_year)).fetchone()
        
        if existing_exam:
            flash('同じ科目・試験種別・年度の試験が既に存在します', 'error')
            return redirect(url_for('exam_add'))
        
        # 試験を追加
        cur.execute('''
            INSERT INTO Exams (subject_id, exam_type_id, exam_year, instructions)
            VALUES (?, ?, ?, ?)
        ''', (subject_id, exam_type_id, exam_year, instructions))
        
        # 追加された試験のIDを取得
        exam_id = cur.lastrowid
        
        # 担当教員を追加
        for professor_id in professor_ids:
            cur.execute('''
                INSERT INTO ExamProfessors (exam_id, professor_id)
                VALUES (?, ?)
            ''', (exam_id, professor_id))
        
        con.commit()
        flash('試験を正常に追加しました', 'success')
        return redirect(url_for('exam_detail', exam_id=exam_id))
        
    except sqlite3.Error as e:
        con.rollback()
        flash('データベースエラーが発生しました', 'error')
        return redirect(url_for('exam_add'))

@app.route('/subjects')
@login_required
def subjects() -> str:
    """科目一覧のページ"""
    cur = get_db().cursor()
    
    subject_list = cur.execute('''
        SELECT s.subject_id, f.faculty_name, d.department_name, s.subject_name,
               s.subject_type, s.semester, s.grade_level
        FROM Subjects s
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        ORDER BY f.faculty_name, d.department_name, s.grade_level, s.subject_name
    ''').fetchall()
    
    return render_template('subjects/list.html', subject_list=subject_list)

@app.route('/exam-create')
@login_required
def exam_create() -> str:
    """新しい試験作成ページ（学部・学科選択式、科目・教員自由入力）"""
    cur = get_db().cursor()
    
    # 学部一覧を取得
    faculties = cur.execute('''
        SELECT faculty_id, faculty_name FROM Faculties ORDER BY faculty_id
    ''').fetchall()
    
    # 学科一覧を取得（JavaScript用）
    departments = cur.execute('''
        SELECT department_id, faculty_id, department_name 
        FROM Departments ORDER BY faculty_id, department_id
    ''').fetchall()
    
    # 試験種別一覧を取得
    exam_types = cur.execute('''
        SELECT exam_type_id, exam_type_name FROM ExamTypes ORDER BY exam_type_name
    ''').fetchall()
    
    # 現在年度
    from datetime import datetime
    current_year = datetime.now().year
    
    return render_template('exams/create.html', 
                         faculties=faculties,
                         departments=departments,
                         exam_types=exam_types,
                         current_year=current_year)

@app.route('/exam-create', methods=['POST'])
@login_required
def exam_create_execute() -> Response:
    """新しい試験作成実行"""
    con = get_db()
    cur = con.cursor()
    
    try:
        # フォームデータ取得
        faculty_id = request.form.get('faculty_id')
        department_id = request.form.get('department_id')
        subject_name = request.form.get('subject_name', '').strip()
        subject_type = request.form.get('subject_type', '').strip()
        semester = request.form.get('semester', '').strip()
        grade_level = request.form.get('grade_level')
        professor_name = request.form.get('professor_name', '').strip()
        exam_type_id = request.form.get('exam_type_id')
        exam_year = request.form.get('exam_year')
        instructions = request.form.get('instructions', '').strip()
        
        # バリデーション
        if not all([faculty_id, department_id, subject_name, subject_type, 
                   semester, grade_level, professor_name, exam_type_id, exam_year]):
            flash('すべての必須項目を入力してください', 'error')
            return redirect(url_for('exam_create'))
        
        try:
            faculty_id = int(faculty_id)
            department_id = int(department_id)
            grade_level = int(grade_level)
            exam_type_id = int(exam_type_id)
            exam_year = int(exam_year)
        except ValueError:
            flash('入力値に不正な値が含まれています', 'error')
            return redirect(url_for('exam_create'))
        
        # 年度の妥当性チェック
        if exam_year < 2000 or exam_year > 2030:
            flash('年度は2000年から2030年の間で入力してください', 'error')
            return redirect(url_for('exam_create'))
        
        # 制御文字チェック
        if any(has_control_character(s) for s in [subject_name, professor_name, instructions]):
            flash('入力値に制御文字が含まれています', 'error')
            return redirect(url_for('exam_create'))
        
        # 科目種別と学期の妥当性チェック
        valid_subject_types = ['必修', '選択必修', '一般教養']
        valid_semesters = ['春学期', '春学期前半', '春学期後半', '秋学期', '秋学期前半', '秋学期後半']
        
        if subject_type not in valid_subject_types:
            flash('不正な科目種別です', 'error')
            return redirect(url_for('exam_create'))
        
        if semester not in valid_semesters:
            flash('不正な学期です', 'error')
            return redirect(url_for('exam_create'))
        
        # 学科の存在確認
        dept_check = cur.execute('''
            SELECT department_id FROM Departments 
            WHERE department_id = ? AND faculty_id = ?
        ''', (department_id, faculty_id)).fetchone()
        
        if not dept_check:
            flash('選択された学部・学科の組み合わせが正しくありません', 'error')
            return redirect(url_for('exam_create'))
        
        # 科目を検索または新規作成
        existing_subject = cur.execute('''
            SELECT subject_id FROM Subjects 
            WHERE department_id = ? AND subject_name = ? AND subject_type = ? 
            AND semester = ? AND grade_level = ?
        ''', (department_id, subject_name, subject_type, semester, grade_level)).fetchone()
        
        if existing_subject:
            subject_id = existing_subject['subject_id']
        else:
            # 新しい科目を作成
            cur.execute('''
                INSERT INTO Subjects (department_id, subject_name, subject_type, semester, grade_level)
                VALUES (?, ?, ?, ?, ?)
            ''', (department_id, subject_name, subject_type, semester, grade_level))
            subject_id = cur.lastrowid
        
        # 教員を検索または新規作成
        existing_professor = cur.execute('''
            SELECT professor_id FROM Professors WHERE professor_name = ?
        ''', (professor_name,)).fetchone()
        
        if existing_professor:
            professor_id = existing_professor['professor_id']
        else:
            # 新しい教員を作成
            cur.execute('''
                INSERT INTO Professors (professor_name) VALUES (?)
            ''', (professor_name,))
            professor_id = cur.lastrowid
        
        # 同じ科目・試験種別・年度の組み合わせが既に存在するかチェック
        existing_exam = cur.execute('''
            SELECT exam_id FROM Exams 
            WHERE subject_id = ? AND exam_type_id = ? AND exam_year = ?
        ''', (subject_id, exam_type_id, exam_year)).fetchone()
        
        if existing_exam:
            flash('同じ科目・試験種別・年度の試験が既に存在します', 'error')
            return redirect(url_for('exam_create'))
        
        # 試験を作成
        cur.execute('''
            INSERT INTO Exams (subject_id, exam_type_id, exam_year, instructions)
            VALUES (?, ?, ?, ?)
        ''', (subject_id, exam_type_id, exam_year, instructions))
        exam_id = cur.lastrowid
        
        # 試験担当教員を設定
        cur.execute('''
            INSERT INTO ExamProfessors (exam_id, professor_id)
            VALUES (?, ?)
        ''', (exam_id, professor_id))
        
        # 科目担当教員も設定（存在しない場合のみ）
        existing_assignment = cur.execute('''
            SELECT 1 FROM SubjectProfessors 
            WHERE subject_id = ? AND professor_id = ? AND assignment_year = ? AND assignment_semester = ?
        ''', (subject_id, professor_id, exam_year, semester)).fetchone()
        
        if not existing_assignment:
            cur.execute('''
                INSERT INTO SubjectProfessors (subject_id, professor_id, assignment_year, assignment_semester)
                VALUES (?, ?, ?, ?)
            ''', (subject_id, professor_id, exam_year, semester))
        
        con.commit()
        print('試験を正常に作成しました', 'success')
        return redirect(url_for('exams'))
        
    except sqlite3.Error as e:
        con.rollback()
        print('データベースエラーが発生しました', 'error')
        return redirect(url_for('exam_add'))
    except Exception as e:
        con.rollback()
        print('予期しないエラーが発生しました', 'error')
        return redirect(url_for('exam_add'))

if __name__ == '__main__':
    app.run(debug=True)