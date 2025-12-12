# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
import sqlite3
import random
import os
import re
import html
import glob
import json
from urllib.parse import unquote
import data_manager

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_quiz_app_123' 

DB_FILE = 'quiz_db.sqlite'
QUESTIONS_PATTERN = '*.json' 

# ----------------------------------------------------------------------
# 🖼️ נתיב מיוחד להגשת תמונות (טיפול ברווחים ושמות בעייתיים)
# ----------------------------------------------------------------------
@app.route('/custom_img/<path:filename>')
def serve_image(filename):
    decoded_filename = unquote(filename)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(current_dir, 'static', 'images')
    full_path = os.path.join(images_dir, decoded_filename)
    
    if os.path.exists(full_path):
        return send_from_directory(images_dir, decoded_filename)
    return "Image not found", 404

# ----------------------------------------------------------------------
# 🔧 פונקציות עזר
# ----------------------------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def clean_text_for_comparison(text):
    if not text: return ""
    text = html.unescape(str(text)).lower()
    return re.sub(r'[^a-z0-9א-ת]', '', text)

def get_navigation_data():
    """בונה את עץ הניווט לסרגל הצד"""
    conn = get_db_connection()
    try:
        questions = conn.execute(
            'SELECT id, question_text, topic, sub_topic FROM Questions ORDER BY topic, sub_topic, id'
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    conn.close()
    
    navigation_tree = {}
    counters = {} 
    
    for q in questions:
        topic = q['topic']
        sub_topic = q['sub_topic']
        
        if topic not in navigation_tree:
            navigation_tree[topic] = {'sub_topics': {}}
        
        if sub_topic not in navigation_tree[topic]['sub_topics']:
            navigation_tree[topic]['sub_topics'][sub_topic] = []
            counters[(topic, sub_topic)] = 0
            
        counters[(topic, sub_topic)] += 1
        
        navigation_tree[topic]['sub_topics'][sub_topic].append({
            'id': q['id'],
            'number': counters[(topic, sub_topic)],
            'text': q['question_text']
        })
    return navigation_tree

# ----------------------------------------------------------------------
# ✏️ עריכת שאלה (כולל תמיכה בבחירה מרובה)
# ----------------------------------------------------------------------
@app.route('/edit_question/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    conn = get_db_connection()
    q_row = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    conn.close()
    
    if not q_row:
        return "שאלה לא נמצאה", 404

    # המרה למילון כדי שנוכל לערוך ולשלוח לטמפלייט
    q = dict(q_row)

    if request.method == 'POST':
        # איסוף הנתונים מהטופס (correct_answer יכול להגיע כ-JSON String אם יש כמה תשובות)
        new_data = {
            'question_text': request.form['question_text'],
            'correct_answer': request.form['correct_answer'],
            'distractor_1': request.form['distractor_1'],
            'distractor_2': request.form['distractor_2'],
            'distractor_3': request.form['distractor_3'],
            'explanation': request.form['explanation'],
            'topic': request.form['topic'],
            'sub_topic': request.form['sub_topic'],
            'image_path': request.form['image_path']
        }
        
        # עדכון DB
        conn = get_db_connection()
        conn.execute('''
            UPDATE Questions SET 
            question_text=?, correct_answer=?, distractor_1=?, distractor_2=?, 
            distractor_3=?, explanation=?, topic=?, sub_topic=?, image_path=?
            WHERE id=?
        ''', (
            new_data['question_text'], new_data['correct_answer'],
            new_data['distractor_1'], new_data['distractor_2'],
            new_data['distractor_3'], new_data['explanation'],
            new_data['topic'], new_data['sub_topic'],
            new_data['image_path'], question_id
        ))
        conn.commit()
        conn.close()

        # עדכון קובץ JSON הפיזי
        data_manager.update_json_file(q['source_file'], q['question_text'], new_data)
        
        return redirect(url_for('get_question', question_id=question_id, edited='true'))

    # --- הכנת נתונים לתצוגה (GET) ---
    options_for_edit = []
    correct_indices = [] # רשימת האינדקסים שמסומנים כנכונים
    
    raw_correct = q['correct_answer']
    try:
        # ניסיון לפענוח JSON (במקרה של תשובות מרובות)
        parsed = json.loads(raw_correct)
        if isinstance(parsed, list):
            for ans in parsed:
                options_for_edit.append(ans)
                correct_indices.append(len(options_for_edit) - 1)
        else:
            # מקרה נדיר של JSON שאינו רשימה
            options_for_edit.append(str(parsed))
            correct_indices.append(0)
    except:
        # מחרוזת רגילה (תשובה יחידה)
        options_for_edit.append(raw_correct)
        correct_indices.append(0)

    # הוספת המסיחים לרשימה
    if q['distractor_1']: options_for_edit.append(q['distractor_1'])
    if q['distractor_2']: options_for_edit.append(q['distractor_2'])
    if q['distractor_3']: options_for_edit.append(q['distractor_3'])

    # השלמה ל-4 שורות ריקות אם צריך
    while len(options_for_edit) < 4:
        options_for_edit.append("")

    return render_template('edit_question.html', q=q, options=options_for_edit, correct_indices=correct_indices)

# ----------------------------------------------------------------------
# 🔍 בדיקת תשובה (תומך ברשימות)
# ----------------------------------------------------------------------
@app.route('/check_answer', methods=['POST'])
def check_answer():
    # קבלת רשימה (עבור צ'קבוקסים)
    user_picks = request.form.getlist('selected_answer') 
    q_id = request.form.get('question_id')
    
    conn = get_db_connection()
    q = conn.execute('SELECT correct_answer, explanation FROM Questions WHERE id = ?', (q_id,)).fetchone()
    conn.close()

    if q is None: return jsonify({"error": "לא נמצא"}), 404
    
    # פענוח התשובה הנכונה מה-DB
    db_correct_raw = q['correct_answer']
    try:
        correct_list = json.loads(db_correct_raw)
        if not isinstance(correct_list, list):
            correct_list = [str(correct_list)]
    except:
        correct_list = [db_correct_raw]

    # השוואה באמצעות Sets (מתעלם מסדר ורווחים כפולים)
    user_clean = {clean_text_for_comparison(u) for u in user_picks}
    correct_clean = {clean_text_for_comparison(c) for c in correct_list}
    
    is_fully_correct = (user_clean == correct_clean) and (len(user_clean) > 0)
    
    # בדיקת חלקיות: יש חיתוך, אבל לא זהות מושלמת
    intersection = user_clean.intersection(correct_clean)
    is_partial = (len(intersection) > 0) and not is_fully_correct
    
    status = "wrong"
    msg = "❌ שגוי."
    
    if is_fully_correct:
        status = "correct"
        msg = "✅ תשובה מלאה ונכונה!"
    elif is_partial:
        status = "partial"
        missing = len(correct_clean) - len(intersection)
        wrong_picks = len(user_clean) - len(intersection)
        
        msg = "⚠️ תשובה חלקית."
        if missing > 0: msg += f" חסרות {missing} תשובות."
        if wrong_picks > 0: msg += " (וסימנת שגויות)."

    return jsonify({
        "status": status,
        "is_correct": is_fully_correct,
        "correct_answers": correct_list, # תמיד מחזיר רשימה ללקוח
        "message": msg,
        "explanation": q['explanation']
    })

# ----------------------------------------------------------------------
# 🧭 מצב תרגול (Practice Mode)
# ----------------------------------------------------------------------

@app.route('/')
def index():
    conn = get_db_connection()
    try:
        topics = conn.execute('SELECT DISTINCT topic FROM Questions').fetchall()
        count_res = conn.execute('SELECT COUNT(*) as cnt FROM Questions').fetchone()
        count = count_res['cnt'] if count_res else 0
    except sqlite3.OperationalError:
        topics, count = [], 0
    conn.close()
    return render_template('index.html', topics=topics, total_questions=count)

@app.route('/quiz')
def start_quiz():
    topic = request.args.get('topic')
    start_id = request.args.get('start_id')
    conn = get_db_connection()
    
    if start_id and start_id.isdigit():
        q = conn.execute('SELECT id FROM Questions WHERE id = ?', (start_id,)).fetchone()
    elif topic:
        q = conn.execute('SELECT id FROM Questions WHERE topic = ? ORDER BY sub_topic, id LIMIT 1', (topic,)).fetchone()
    else:
        q = conn.execute('SELECT id FROM Questions ORDER BY id LIMIT 1').fetchone()
        
    conn.close()
    return redirect(url_for('get_question', question_id=q['id'])) if q else redirect(url_for('index'))

@app.route('/question/<int:question_id>')
def get_question(question_id):
    conn = get_db_connection()
    question = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    
    if not question:
        conn.close()
        return "השאלה לא נמצאה.", 404
    
    # חישוב מיקומים לניווט
    sub_topic = question['sub_topic']
    topic_questions = conn.execute('SELECT id FROM Questions WHERE sub_topic = ? ORDER BY id', (sub_topic,)).fetchall()
    ids = [q['id'] for q in topic_questions]
    
    try:
        curr_idx = ids.index(question_id)
        current_q_num = curr_idx + 1
        total_q_num = len(ids)
        next_id = ids[curr_idx + 1] if curr_idx + 1 < len(ids) else None
        prev_id = ids[curr_idx - 1] if curr_idx > 0 else None
    except ValueError:
        current_q_num, total_q_num, next_id, prev_id = 1, 1, None, None

    # פענוח האופציות (כולל פירוק רשימות)
    options = []
    raw_correct = question['correct_answer']
    try:
        parsed = json.loads(raw_correct)
        if isinstance(parsed, list): options.extend(parsed)
        else: options.append(str(parsed))
    except:
        options.append(raw_correct)
        
    for d in ['distractor_1', 'distractor_2', 'distractor_3']:
        if question[d]: options.append(question[d])
    
    random.shuffle(options)
    conn.close()
    
    return render_template('question.html', 
                           question=question, options=options, 
                           next_id=next_id, prev_id=prev_id,
                           navigation_data=get_navigation_data(),
                           current_q_in_category=current_q_num,
                           total_q_in_category=total_q_num)

# ----------------------------------------------------------------------
# 🎓 מצב בחינה (Exam Mode)
# ----------------------------------------------------------------------

@app.route('/exam_setup')
def exam_setup():
    conn = get_db_connection()
    try:
        data = conn.execute('SELECT DISTINCT topic, sub_topic FROM Questions').fetchall()
    except: data = []
    conn.close()
    
    topics = {}
    for row in data:
        t, st = row['topic'], row['sub_topic']
        if t not in topics: topics[t] = []
        topics[t].append(st)
        
    return render_template('exam_setup.html', topics=topics)

@app.route('/start_exam', methods=['POST'])
def start_exam():
    sub_topic = request.form.get('sub_topic')
    conn = get_db_connection()
    questions = conn.execute('SELECT id FROM Questions WHERE sub_topic = ? ORDER BY id', (sub_topic,)).fetchall()
    conn.close()
    
    if not questions: return "לא נמצאו שאלות", 404
        
    session['exam_ids'] = [q['id'] for q in questions]
    session['exam_answers'] = {}
    session['exam_sub_topic'] = sub_topic
    
    return redirect(url_for('exam_question', index=0))

@app.route('/exam/<int:index>', methods=['GET', 'POST'])
def exam_question(index):
    exam_ids = session.get('exam_ids', [])
    if not exam_ids or index >= len(exam_ids):
        return redirect(url_for('exam_setup'))
    
    if request.method == 'POST':
        # תמיכה בבחירה מרובה (רשימה)
        selected = request.form.getlist('selected_answer') 
        if selected:
            current_answers = session.get('exam_answers', {})
            # שומרים כרשימה אם יש יותר מאחד, או מחרוזת אם אחד (לנוחות, הלוגיקה מטפלת בשניהם)
            current_answers[str(exam_ids[index])] = selected if len(selected) > 1 else selected[0]
            session['exam_answers'] = current_answers
            session.modified = True 
            
        action = request.form.get('action')
        if action == 'next': return redirect(url_for('exam_question', index=index + 1))
        elif action == 'prev': return redirect(url_for('exam_question', index=index - 1))
        elif action == 'finish': return redirect(url_for('submit_exam'))
        elif action and action.startswith('jump_'):
            return redirect(url_for('exam_question', index=int(action.split('_')[1])))

    question_id = exam_ids[index]
    conn = get_db_connection()
    question = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    conn.close()
    
    options = []
    try:
        parsed = json.loads(question['correct_answer'])
        if isinstance(parsed, list): options.extend(parsed)
        else: options.append(str(parsed))
    except: options.append(question['correct_answer'])
    
    for d in ['distractor_1', 'distractor_2', 'distractor_3']:
        if question[d]: options.append(question[d])
    random.shuffle(options)
    
    # הכנה לתצוגה בטמפלייט (המרת בחירת משתמש לרשימה תמיד)
    user_sel = session.get('exam_answers', {}).get(str(question_id))
    if user_sel and not isinstance(user_sel, list): user_sel = [user_sel]
    if not user_sel: user_sel = []

    user_answers_map = session.get('exam_answers', {})
    exam_nav = []
    for i, qid in enumerate(exam_ids):
        status = 'answered' if str(qid) in user_answers_map else 'default'
        if i == index: status = 'active'
        exam_nav.append({'index': i, 'number': i + 1, 'status': status})

    return render_template('exam_question.html', 
                           question=question, options=options, index=index, 
                           total=len(exam_ids), user_selection=user_sel, 
                           exam_nav=exam_nav, sub_topic=session.get('exam_sub_topic'))

@app.route('/submit_exam')
def submit_exam():
    exam_ids = session.get('exam_ids', [])
    user_answers = session.get('exam_answers', {})
    
    if not exam_ids: return redirect(url_for('exam_setup'))
    
    score = 0
    results = []
    conn = get_db_connection()
    
    for q_id in exam_ids:
        q = conn.execute('SELECT * FROM Questions WHERE id = ?', (q_id,)).fetchone()
        
        # נרמול תשובת המשתמש לסט
        u_raw = user_answers.get(str(q_id))
        u_list = u_raw if isinstance(u_raw, list) else ([u_raw] if u_raw else [])
        u_clean = {clean_text_for_comparison(x) for x in u_list}
        
        # נרמול תשובה נכונה לסט
        try:
            c_list = json.loads(q['correct_answer'])
            if not isinstance(c_list, list): c_list = [str(c_list)]
        except: c_list = [q['correct_answer']]
        c_clean = {clean_text_for_comparison(x) for x in c_list}
        
        # בדיקה
        is_correct = (u_clean == c_clean) and (len(u_clean) > 0)
        is_partial = (len(u_clean.intersection(c_clean)) > 0) and not is_correct
        
        if is_correct: score += 1
            
        results.append({
            'question': q,
            'user_answer': ", ".join(u_list),
            'correct_answer': ", ".join(c_list),
            'is_correct': is_correct,
            'is_partial': is_partial,
            'explanation': q['explanation']
        })
    conn.close()
    
    final_score = int((score / len(exam_ids)) * 100) if exam_ids else 0
    return render_template('exam_result.html', score=final_score, results=results, total=len(exam_ids), correct_count=score)

# ----------------------------------------------------------------------
# 🚀 אתחול
# ----------------------------------------------------------------------
def setup_database():
    data_manager.create_tables()
    files = glob.glob(QUESTIONS_PATTERN)
    for f in files:
        data_manager.load_questions_from_file(f)

if __name__ == '__main__':
    with app.app_context():
        # בכל הרצה - טעינה מחדש של הקבצים (לפיתוח)
        setup_database()
    app.run(debug=True)