#!/usr/keio/Anaconda3-2024.10-1/bin/python
"""
試験問題管理システム Web アプリケーション

シンプルな認証システムを持つ試験問題管理システム
"""

import sqlite3
from typing import Final, Optional
import unicodedata
import os
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

from flask import Flask, g, redirect, render_template, request, url_for, flash, session, send_from_directory
from werkzeug import Response

# データベースのファイル名（絶対パス対応）
DATABASE: Final[str] = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db'))

# アップロードファイルの設定（絶対パス対応）
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

# Flask クラスのインスタンス
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'exam_management_secret_key_2024')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# アップロードフォルダが存在しない場合は作成
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception as e:
    # 権限がない場合は一時的なフォルダを使用
    import tempfile
    UPLOAD_FOLDER = tempfile.mkdtemp()
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
    'email-exists': 'このメールアドレスは既に登録されています',
    'file-upload-error': 'ファイルのアップロードに失敗しました',
    'file-too-large': 'ファイルサイズが大きすぎます（最大16MB）',
    'invalid-file-type': '許可されていないファイル形式です'
}

def allowed_file(filename):
    """アップロードが許可されているファイルかチェック"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db() -> sqlite3.Connection:
    """データベース接続を得る"""
    db = getattr(g, '_database', None)
    if db is None:
        try:
            db = g._database = sqlite3.connect(DATABASE)
            db.execute('PRAGMA foreign_keys = ON')
            db.row_factory = sqlite3.Row
        except Exception as e:
            # データベース接続エラーの場合、詳細をログに出力
            import sys
            print(f"Database connection error: {e}", file=sys.stderr)
            raise
    return db

@app.teardown_appcontext
def close_connection(exception: Optional[BaseException]) -> None:
    """データベース接続を閉じる"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def hash_password(password: str) -> str:
    """パスワードをそのまま返す（平文版）"""
    return password

def verify_password(password: str, password_hash: str) -> bool:
    """パスワードを検証（平文版）"""
    return password == password_hash

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
    try:
        if 'user_id' in session:
            return redirect(url_for('home'))
        return redirect(url_for('login'))
    except Exception as e:
        import sys
        print(f"Index route error: {e}", file=sys.stderr)
        return render_template('error/500.html'), 500

@app.route('/login')
def login() -> str:
    """ログインページ"""
    try:
        if 'user_id' in session:
            return redirect(url_for('home'))
        return render_template('auth/login.html')
    except Exception as e:
        import sys
        print(f"Login route error: {e}", file=sys.stderr)
        return render_template('error/500.html'), 500

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
    
    # 明示的なJOINを使用してデータを取得（作成者情報も含める）
    exam_list = cur.execute('''
        SELECT 
            e.exam_id,
            f.faculty_name,
            d.department_name,
            s.subject_name,
            et.exam_type_name,
            e.exam_year,
            GROUP_CONCAT(p.professor_name, ', ') AS professors,
            e.created_by
        FROM Exams e
        JOIN Subjects s ON e.subject_id = s.subject_id
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
        LEFT JOIN ExamProfessors ep ON e.exam_id = ep.exam_id
        LEFT JOIN Professors p ON ep.professor_id = p.professor_id
        GROUP BY e.exam_id, f.faculty_name, d.department_name, s.subject_name, et.exam_type_name, e.exam_year, e.created_by
        ORDER BY e.exam_year DESC, f.faculty_name, d.department_name, s.subject_name
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
    
    # 明示的なJOINを使用してデータを取得（作成者情報も含める）
    query = '''
        SELECT 
            e.exam_id,
            f.faculty_name,
            d.department_name,
            s.subject_name,
            et.exam_type_name,
            e.exam_year,
            GROUP_CONCAT(p.professor_name, ', ') AS professors,
            e.created_by
        FROM Exams e
        JOIN Subjects s ON e.subject_id = s.subject_id
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
        LEFT JOIN ExamProfessors ep ON e.exam_id = ep.exam_id
        LEFT JOIN Professors p ON ep.professor_id = p.professor_id
        WHERE 1=1
    '''
    params = []
    
    if faculty_filter:
        query += ' AND f.faculty_name LIKE ?'
        params.append(f'%{faculty_filter}%')
    
    if department_filter:
        query += ' AND d.department_name LIKE ?'
        params.append(f'%{department_filter}%')
    
    if subject_filter:
        query += ' AND s.subject_name LIKE ?'
        params.append(f'%{subject_filter}%')
    
    if year_filter:
        try:
            year = int(year_filter)
            query += ' AND e.exam_year = ?'
            params.append(year)
        except ValueError:
            flash('年度は数値で入力してください', 'error')
    
    query += '''
        GROUP BY e.exam_id, f.faculty_name, d.department_name, s.subject_name, et.exam_type_name, e.exam_year, e.created_by
        ORDER BY e.exam_year DESC, f.faculty_name, d.department_name, s.subject_name
    '''
    
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
    
    # 試験詳細情報を取得
    exam = cur.execute('''
        SELECT 
            e.exam_id,
            f.faculty_name,
            d.department_name,
            s.subject_name,
            et.exam_type_name,
            e.exam_year,
            e.instructions,
            GROUP_CONCAT(p.professor_name, ', ') AS professors,
            e.created_by
        FROM Exams e
        JOIN Subjects s ON e.subject_id = s.subject_id
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
        LEFT JOIN ExamProfessors ep ON e.exam_id = ep.exam_id
        LEFT JOIN Professors p ON ep.professor_id = p.professor_id
        WHERE e.exam_id = ?
        GROUP BY e.exam_id, f.faculty_name, d.department_name, s.subject_name, et.exam_type_name, e.exam_year, e.instructions, e.created_by
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
    return render_template('exams/add.html')

@app.route('/exam-add', methods=['POST'])
@login_required
def exam_add_execute() -> Response:
    """試験追加実行"""
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
            return redirect(url_for('exam_add'))
        
        try:
            faculty_id = int(faculty_id)
            department_id = int(department_id)
            grade_level = int(grade_level)
            exam_type_id = int(exam_type_id)
            exam_year = int(exam_year)
        except ValueError:
            flash('入力値に不正な値が含まれています', 'error')
            return redirect(url_for('exam_add'))
        
        # 年度の妥当性チェック
        if exam_year < 2000 or exam_year > 2030:
            flash('年度は2000年から2030年の間で入力してください', 'error')
            return redirect(url_for('exam_add'))
        
        # 制御文字チェック
        if any(has_control_character(s) for s in [subject_name, professor_name, instructions]):
            flash('入力値に制御文字が含まれています', 'error')
            return redirect(url_for('exam_add'))
        
        # 科目種別と学期の妥当性チェック
        valid_subject_types = ['必修', '選択必修', '一般教養']
        valid_semesters = ['春学期', '春学期前半', '春学期後半', '秋学期', '秋学期前半', '秋学期後半']
        
        if subject_type not in valid_subject_types:
            flash('不正な科目種別です', 'error')
            return redirect(url_for('exam_add'))
        
        if semester not in valid_semesters:
            flash('不正な学期です', 'error')
            return redirect(url_for('exam_add'))
        
        # 学科の存在確認
        dept_check = cur.execute('''
            SELECT department_id FROM Departments 
            WHERE department_id = ? AND faculty_id = ?
        ''', (department_id, faculty_id)).fetchone()
        
        if not dept_check:
            flash('選択された学部・学科の組み合わせが正しくありません', 'error')
            return redirect(url_for('exam_add'))
        
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
            return redirect(url_for('exam_add'))
        
        # 試験を作成（created_byを設定）
        cur.execute('''
            INSERT INTO Exams (subject_id, exam_type_id, exam_year, instructions, created_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (subject_id, exam_type_id, exam_year, instructions, session['user_id']))
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
        
        # ファイルアップロード処理
        uploaded_files = request.files.getlist('exam_files')
        file_upload_errors = []
        
        for file in uploaded_files:
            if file and file.filename:
                if allowed_file(file.filename):
                    try:
                        filename = secure_filename(file.filename)
                        # ファイル名の重複を避けるためタイムスタンプを付加
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        name, ext = os.path.splitext(filename)
                        filename = f"{name}_{timestamp}{ext}"
                        
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        
                        # データベースに問題画像を登録
                        cur.execute('''
                            INSERT INTO ExamQuestions (exam_id, picture)
                            VALUES (?, ?)
                        ''', (exam_id, filename))
                        
                    except Exception as e:
                        file_upload_errors.append(f"ファイル '{file.filename}' のアップロードに失敗しました: {str(e)}")
                else:
                    file_upload_errors.append(f"ファイル '{file.filename}' は許可されていない形式です")
        
        con.commit()
        
        # アップロードエラーがあれば警告として表示
        if file_upload_errors:
            flash('試験は正常に作成されましたが、一部のファイルでエラーが発生しました: ' + 
                  ', '.join(file_upload_errors), 'warning')
        else:
            flash('試験を正常に作成しました', 'success')
        
        return redirect(url_for('exams'))
        
    except sqlite3.Error as e:
        con.rollback()
        flash(f'データベースエラーが発生しました: {e}', 'error')
        return redirect(url_for('exam_add'))
    except Exception as e:
        con.rollback()
        flash(f'予期しないエラーが発生しました: {e}', 'error')
        return redirect(url_for('exam_add'))

# ファイル提供用のルート
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """アップロードされたファイルを提供"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/exam-edit/<int:exam_id>')
@login_required
def exam_edit(exam_id: int) -> str:
    """試験編集ページ"""
    cur = get_db().cursor()
    
    # 試験情報を取得
    exam = cur.execute('''
        SELECT 
            e.exam_id,
            e.subject_id,
            e.exam_type_id,
            e.exam_year,
            e.instructions,
            e.created_by,
            s.subject_name,
            s.subject_type,
            s.semester,
            s.grade_level,
            s.department_id,
            d.faculty_id,
            f.faculty_name,
            d.department_name,
            et.exam_type_name
        FROM Exams e
        JOIN Subjects s ON e.subject_id = s.subject_id
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
        WHERE e.exam_id = ?
    ''', (exam_id,)).fetchone()
    
    if exam is None:
        flash('指定された試験が見つかりません', 'error')
        return redirect(url_for('exams'))
    
    # 作成者チェック
    if exam['created_by'] != session['user_id']:
        flash('この試験を編集する権限がありません', 'error')
        return redirect(url_for('exam_detail', exam_id=exam_id))
    
    # 担当教員を取得
    professors = cur.execute('''
        SELECT p.professor_name
        FROM ExamProfessors ep
        JOIN Professors p ON ep.professor_id = p.professor_id
        WHERE ep.exam_id = ?
    ''', (exam_id,)).fetchall()
    
    professor_names = [p['professor_name'] for p in professors]
    
    # 試験問題ファイルを取得
    questions = cur.execute('''
        SELECT question_id, picture FROM ExamQuestions WHERE exam_id = ?
    ''', (exam_id,)).fetchall()
    
    return render_template('exams/edit.html', 
                         exam=exam, 
                         professor_names=professor_names,
                         questions=questions)

# app.pyに追加する試験編集更新処理

@app.route('/exam-edit/<int:exam_id>', methods=['POST'])
@login_required
def exam_edit_update(exam_id: int) -> Response:
    """試験編集更新実行"""
    con = get_db()
    cur = con.cursor()
    
    try:
        # 試験の存在と権限チェック
        exam = cur.execute('''
            SELECT created_by FROM Exams WHERE exam_id = ?
        ''', (exam_id,)).fetchone()
        
        if exam is None:
            flash('指定された試験が見つかりません', 'error')
            return redirect(url_for('exams'))
        
        # 作成者チェック
        if exam['created_by'] != session['user_id']:
            flash('この試験を編集する権限がありません', 'error')
            return redirect(url_for('exam_detail', exam_id=exam_id))
        
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
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        try:
            faculty_id = int(faculty_id)
            department_id = int(department_id)
            grade_level = int(grade_level)
            exam_type_id = int(exam_type_id)
            exam_year = int(exam_year)
        except ValueError:
            flash('入力値に不正な値が含まれています', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        # 年度の妥当性チェック
        if exam_year < 2000 or exam_year > 2030:
            flash('年度は2000年から2030年の間で入力してください', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        # 制御文字チェック
        if any(has_control_character(s) for s in [subject_name, professor_name, instructions]):
            flash('入力値に制御文字が含まれています', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        # 科目種別と学期の妥当性チェック
        valid_subject_types = ['必修', '選択必修', '一般教養']
        valid_semesters = ['春学期', '春学期前半', '春学期後半', '秋学期', '秋学期前半', '秋学期後半']
        
        if subject_type not in valid_subject_types:
            flash('不正な科目種別です', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        if semester not in valid_semesters:
            flash('不正な学期です', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        # 学科の存在確認
        dept_check = cur.execute('''
            SELECT department_id FROM Departments 
            WHERE department_id = ? AND faculty_id = ?
        ''', (department_id, faculty_id)).fetchone()
        
        if not dept_check:
            flash('選択された学部・学科の組み合わせが正しくありません', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        # 現在の試験に関連する科目IDを取得
        current_exam = cur.execute('''
            SELECT subject_id FROM Exams WHERE exam_id = ?
        ''', (exam_id,)).fetchone()
        
        current_subject_id = current_exam['subject_id']
        
        # 科目を検索または新規作成（現在の科目と異なる場合のみ）
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
        
        # 同じ科目・試験種別・年度の組み合わせが他に存在するかチェック（自分以外）
        existing_exam = cur.execute('''
            SELECT exam_id FROM Exams 
            WHERE subject_id = ? AND exam_type_id = ? AND exam_year = ? AND exam_id != ?
        ''', (subject_id, exam_type_id, exam_year, exam_id)).fetchone()
        
        if existing_exam:
            flash('同じ科目・試験種別・年度の試験が既に存在します', 'error')
            return redirect(url_for('exam_edit', exam_id=exam_id))
        
        # 試験情報を更新
        cur.execute('''
            UPDATE Exams 
            SET subject_id = ?, exam_type_id = ?, exam_year = ?, instructions = ?, updated_at = CURRENT_TIMESTAMP
            WHERE exam_id = ?
        ''', (subject_id, exam_type_id, exam_year, instructions, exam_id))
        
        # 既存の試験担当教員を削除して新しく設定
        cur.execute('DELETE FROM ExamProfessors WHERE exam_id = ?', (exam_id,))
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
        
        # 新しいファイルのアップロード処理
        uploaded_files = request.files.getlist('exam_files')
        file_upload_errors = []
        
        for file in uploaded_files:
            if file and file.filename:
                if allowed_file(file.filename):
                    try:
                        filename = secure_filename(file.filename)
                        # ファイル名の重複を避けるためタイムスタンプを付加
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        name, ext = os.path.splitext(filename)
                        filename = f"{name}_{timestamp}{ext}"
                        
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        
                        # データベースに問題画像を登録
                        cur.execute('''
                            INSERT INTO ExamQuestions (exam_id, picture)
                            VALUES (?, ?)
                        ''', (exam_id, filename))
                        
                    except Exception as e:
                        file_upload_errors.append(f"ファイル '{file.filename}' のアップロードに失敗しました: {str(e)}")
                else:
                    file_upload_errors.append(f"ファイル '{file.filename}' は許可されていない形式です")
        
        con.commit()
        
        # アップロードエラーがあれば警告として表示
        if file_upload_errors:
            flash('試験は正常に更新されましたが、一部のファイルでエラーが発生しました: ' + 
                  ', '.join(file_upload_errors), 'warning')
        else:
            flash('試験を正常に更新しました', 'success')
        
        # 試験一覧画面にリダイレクト
        return redirect(url_for('exams'))
        
    except sqlite3.Error as e:
        con.rollback()
        flash(f'データベースエラーが発生しました: {e}', 'error')
        return redirect(url_for('exam_edit', exam_id=exam_id))
    except Exception as e:
        con.rollback()
        flash(f'予期しないエラーが発生しました: {e}', 'error')
        return redirect(url_for('exam_edit', exam_id=exam_id))

@app.route('/exam-file-delete/<int:question_id>', methods=['DELETE'])
@login_required
def exam_file_delete(question_id: int):
    """試験問題ファイル削除API"""
    try:
        con = get_db()
        cur = con.cursor()
        
        # 問題ファイル情報と試験の作成者を取得
        question_info = cur.execute('''
            SELECT eq.picture, e.created_by, eq.exam_id
            FROM ExamQuestions eq
            JOIN Exams e ON eq.exam_id = e.exam_id
            WHERE eq.question_id = ?
        ''', (question_id,)).fetchone()
        
        if question_info is None:
            return {'success': False, 'message': 'ファイルが見つかりません'}, 404
        
        # 権限チェック
        if question_info['created_by'] != session['user_id']:
            return {'success': False, 'message': 'このファイルを削除する権限がありません'}, 403
        
        # データベースから削除
        cur.execute('DELETE FROM ExamQuestions WHERE question_id = ?', (question_id,))
        
        # 物理ファイルを削除
        if question_info['picture']:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], question_info['picture'])
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    # ファイル削除に失敗してもデータベースからは削除済みなので続行
                    pass
        
        con.commit()
        return {'success': True, 'message': 'ファイルを削除しました'}
        
    except Exception as e:
        con.rollback()
        return {'success': False, 'message': f'削除中にエラーが発生しました: {str(e)}'}, 500
    
@app.route('/exam-delete/<int:exam_id>')
@login_required
def exam_delete(exam_id: int) -> str:
    """試験削除確認ページ"""
    cur = get_db().cursor()
    
    # 試験情報を取得
    exam = cur.execute('''
        SELECT 
            e.exam_id,
            f.faculty_name,
            d.department_name,
            s.subject_name,
            et.exam_type_name,
            e.exam_year,
            e.instructions,
            e.created_by,
            GROUP_CONCAT(DISTINCT p.professor_name, ', ') AS professors
        FROM Exams e
        JOIN Subjects s ON e.subject_id = s.subject_id
        JOIN Departments d ON s.department_id = d.department_id
        JOIN Faculties f ON d.faculty_id = f.faculty_id
        JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
        LEFT JOIN ExamProfessors ep ON e.exam_id = ep.exam_id
        LEFT JOIN Professors p ON ep.professor_id = p.professor_id
        WHERE e.exam_id = ?
        GROUP BY e.exam_id, f.faculty_name, d.department_name, s.subject_name, et.exam_type_name, e.exam_year, e.instructions, e.created_by
    ''', (exam_id,)).fetchone()
    
    if exam is None:
        flash('指定された試験が見つかりません', 'error')
        return redirect(url_for('exams'))
    
    # 作成者チェック
    if exam['created_by'] != session['user_id']:
        flash('この試験を削除する権限がありません', 'error')
        return redirect(url_for('exam_detail', exam_id=exam_id))
    
    # 試験問題ファイルを取得
    questions = cur.execute('''
        SELECT question_id, picture FROM ExamQuestions WHERE exam_id = ?
    ''', (exam_id,)).fetchall()
    
    return render_template('exams/delete.html', exam=exam, questions=questions)

@app.route('/exam-delete/<int:exam_id>', methods=['POST'])
@login_required
def exam_delete_execute(exam_id: int) -> Response:
    """試験削除実行"""
    con = get_db()
    cur = con.cursor()
    
    try:
        # 試験の存在と権限チェック
        exam = cur.execute('''
            SELECT e.created_by, s.subject_name, et.exam_type_name, e.exam_year
            FROM Exams e
            JOIN Subjects s ON e.subject_id = s.subject_id
            JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
            WHERE e.exam_id = ?
        ''', (exam_id,)).fetchone()
        
        if exam is None:
            flash('指定された試験が見つかりません', 'error')
            return redirect(url_for('exams'))
        
        # 作成者チェック
        if exam['created_by'] != session['user_id']:
            flash('この試験を削除する権限がありません', 'error')
            return redirect(url_for('exam_detail', exam_id=exam_id))
        
        # 削除対象の試験情報を保存（メッセージ用）
        exam_info = f"{exam['subject_name']}（{exam['exam_type_name']}、{exam['exam_year']}年度）"
        
        # 関連するファイルを取得
        questions = cur.execute('''
            SELECT picture FROM ExamQuestions WHERE exam_id = ?
        ''', (exam_id,)).fetchall()
        
        # 関連ファイルの物理削除
        deleted_files = []
        failed_files = []
        
        for question in questions:
            if question['picture']:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], question['picture'])
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        deleted_files.append(question['picture'])
                    except OSError as e:
                        failed_files.append(question['picture'])
                        # ファイル削除に失敗してもデータベースからは削除続行
                        print(f"ファイル削除失敗: {question['picture']}, エラー: {e}")
        
        # 関連データを正しい順序で削除（外部キー制約を考慮）
        # 1. 試験問題ファイルを削除
        cur.execute('DELETE FROM ExamQuestions WHERE exam_id = ?', (exam_id,))
        
        # 2. 試験担当教員を削除
        cur.execute('DELETE FROM ExamProfessors WHERE exam_id = ?', (exam_id,))
        
        # 3. 最後に試験を削除
        cur.execute('DELETE FROM Exams WHERE exam_id = ?', (exam_id,))
        
        con.commit()
        
        # 削除結果のメッセージ作成
        success_message = f'試験「{exam_info}」を削除しました'
        if deleted_files:
            success_message += f'（{len(deleted_files)}個のファイルも削除）'
        if failed_files:
            success_message += f'（注意: {len(failed_files)}個のファイルの削除に失敗）'
        
        flash(success_message, 'success')
        return redirect(url_for('exams'))
        
    except sqlite3.Error as e:
        con.rollback()
        flash(f'データベースエラーが発生しました: {e}', 'error')
        return redirect(url_for('exam_detail', exam_id=exam_id))
    except Exception as e:
        con.rollback()
        flash(f'予期しないエラーが発生しました: {e}', 'error')
        return redirect(url_for('exam_detail', exam_id=exam_id))

@app.route('/exam-delete-ajax/<int:exam_id>', methods=['DELETE'])
@login_required
def exam_delete_ajax(exam_id: int):
    """Ajax による試験削除（一覧画面から）"""
    con = get_db()
    cur = con.cursor()
    
    try:
        # 試験の存在と権限チェック
        exam = cur.execute('''
            SELECT e.created_by, s.subject_name, et.exam_type_name, e.exam_year
            FROM Exams e
            JOIN Subjects s ON e.subject_id = s.subject_id
            JOIN ExamTypes et ON e.exam_type_id = et.exam_type_id
            WHERE e.exam_id = ?
        ''', (exam_id,)).fetchone()
        
        if exam is None:
            return {'success': False, 'message': '指定された試験が見つかりません'}, 404
        
        # 作成者チェック
        if exam['created_by'] != session['user_id']:
            return {'success': False, 'message': 'この試験を削除する権限がありません'}, 403
        
        # 削除対象の試験情報を保存
        exam_info = f"{exam['subject_name']}（{exam['exam_type_name']}、{exam['exam_year']}年度）"
        
        # 関連するファイルを取得
        questions = cur.execute('''
            SELECT picture FROM ExamQuestions WHERE exam_id = ?
        ''', (exam_id,)).fetchall()
        
        # 関連ファイルの物理削除
        deleted_files = []
        failed_files = []
        
        for question in questions:
            if question['picture']:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], question['picture'])
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        deleted_files.append(question['picture'])
                    except OSError:
                        failed_files.append(question['picture'])
                        # ファイル削除に失敗してもデータベースからは削除続行
        
        # 関連データを正しい順序で削除（外部キー制約を考慮）
        # 1. 試験問題ファイルを削除
        cur.execute('DELETE FROM ExamQuestions WHERE exam_id = ?', (exam_id,))
        
        # 2. 試験担当教員を削除
        cur.execute('DELETE FROM ExamProfessors WHERE exam_id = ?', (exam_id,))
        
        # 3. 最後に試験を削除
        cur.execute('DELETE FROM Exams WHERE exam_id = ?', (exam_id,))
        
        con.commit()
        
        # 削除結果のメッセージ作成
        success_message = f'試験「{exam_info}」を削除しました'
        if deleted_files:
            success_message += f'（{len(deleted_files)}個のファイルも削除）'
        if failed_files:
            success_message += f'（注意: {len(failed_files)}個のファイルの削除に失敗）'
        
        return {
            'success': True, 
            'message': success_message,
            'deleted_files': len(deleted_files),
            'failed_files': len(failed_files)
        }
        
    except sqlite3.Error as e:
        con.rollback()
        return {'success': False, 'message': f'データベースエラーが発生しました: {str(e)}'}, 500
    except Exception as e:
        con.rollback()
        return {'success': False, 'message': f'予期しないエラーが発生しました: {str(e)}'}, 500

if __name__ == '__main__':
    app.run(debug=True)