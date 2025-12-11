# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
import random
import os
import re
import html
import data_manager  # ייבוא המודול שמנהל את הנתונים

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_quiz_app_123' 

DB_FILE = 'quiz_db.sqlite'
QUESTIONS_FILE = 'questions.json'

# ----------------------------------------------------------------------
# 🔧 פונקציות עזר
# ----------------------------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_navigation_data():
    """בונה את עץ הניווט לסרגל הצד"""
    conn = get_db_connection()
    questions = conn.execute(
        'SELECT id, question_text, topic, sub_topic FROM Questions ORDER BY topic, sub_topic, id'
    ).fetchall()
    conn.close()
    
    navigation_tree = {}
    topic_counters = {} 
    
    for q in questions:
        topic = q['topic']
        sub_topic = q['sub_topic']
        
        if topic not in navigation_tree:
            navigation_tree[topic] = {'sub_topics': {}}
            topic_counters[topic] = 0 
        
        topic_counters[topic] += 1
        
        if sub_topic not in navigation_tree[topic]['sub_topics']:
            navigation_tree[topic]['sub_topics'][sub_topic] = []
            
        navigation_tree[topic]['sub_topics'][sub_topic].append({
            'id': q['id'],
            'number': topic_counters[topic],
            'text': q['question_text']
        })
    return navigation_tree

def clean_text_for_comparison(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = text.lower()
    cleaned_text = re.sub(r'[^a-z0-9א-ת]', '', text)
    return cleaned_text

# ----------------------------------------------------------------------
# 🔄 אתחול נתונים (מצב פיתוח - טעינה מחדש בכל ריצה)
# ----------------------------------------------------------------------

def setup_database():
    """
    מצב פיתוח:
    מוחק את ה-DB הקיים וטוען מחדש את ה-JSON בכל הפעלה.
    זה מבטיח שכל שינוי ב-JSON יופיע מיד באתר.
    """
    print("🔄 מצב עדכון: מרענן את הנתונים מקובץ ה-JSON...")
    
    # 1. מחיקת הקובץ הישן אם הוא קיים
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print("🗑️ מסד הנתונים הישן נמחק.")
        except OSError:
            print("⚠️ לא ניתן למחוק את הקובץ (אולי הוא פתוח?). מנסה להמשיך...")

    # 2. יצירת טבלאות מחדש
    data_manager.create_tables()
    
    # 3. טעינת הנתונים מהקובץ
    data_manager.load_questions_from_file(QUESTIONS_FILE)
    print("✅ הנתונים נטענו מחדש בהצלחה!")

# ----------------------------------------------------------------------
# 🧭 מצב תרגול (Practice Mode)
# ----------------------------------------------------------------------

@app.route('/')
def index():
    conn = get_db_connection()
    try:
        topics = conn.execute('SELECT DISTINCT topic FROM Questions').fetchall()
        count_query = conn.execute('SELECT COUNT(*) as cnt FROM Questions').fetchone()
        count = count_query['cnt'] if count_query else 0
    except sqlite3.OperationalError:
        topics = []
        count = 0
    conn.close()
    return render_template('index.html', topics=topics, total_questions=count)

@app.route('/quiz')
def start_quiz():
    topic = request.args.get('topic')
    start_id = request.args.get('start_id')
    conn = get_db_connection()
    
    if start_id and start_id.isdigit():
        q = conn.execute('SELECT id FROM Questions WHERE id = ?', (start_id,)).fetchone()
        conn.close()
        return redirect(url_for('get_question', question_id=q['id'])) if q else ("שגיאה", 404)

    if topic:
        q = conn.execute('SELECT id FROM Questions WHERE topic = ? ORDER BY sub_topic, id LIMIT 1', (topic,)).fetchone()
        conn.close()
        return redirect(url_for('get_question', question_id=q['id'])) if q else ("לא נמצא", 404)
            
    q = conn.execute('SELECT id FROM Questions ORDER BY id LIMIT 1').fetchone()
    conn.close()
    return redirect(url_for('get_question', question_id=q['id'])) if q else redirect(url_for('index'))

@app.route('/question/<int:question_id>')
def get_question(question_id):
    conn = get_db_connection()
    question = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    
    if question is None:
        conn.close()
        return "השאלה לא נמצאה.", 404
    
    current_topic = question['topic']
    topic_questions = conn.execute(
        'SELECT id FROM Questions WHERE topic = ? ORDER BY sub_topic, id',
        (current_topic,)
    ).fetchall()
    
    topic_ids = [q['id'] for q in topic_questions]
    
    try:
        current_index = topic_ids.index(question_id)
        current_q_in_category = current_index + 1
        total_q_in_category = len(topic_ids)
        next_q_id = topic_ids[current_index + 1] if current_index + 1 < total_q_in_category else None
        prev_q_id = topic_ids[current_index - 1] if current_index > 0 else None
    except ValueError:
        current_q_in_category = 1
        total_q_in_category = 1
        next_q_id = None
        prev_q_id = None

    all_q_ids = [q['id'] for q in conn.execute('SELECT id FROM Questions ORDER BY id').fetchall()]
    conn.close()

    options = [question['correct_answer'], question['distractor_1'], question['distractor_2'], question['distractor_3']]
    options = [o for o in options if o and o.strip()]
    random.shuffle(options)
    
    return render_template('question.html', 
                           question=question, options=options, 
                           next_id=next_q_id, prev_id=prev_q_id,
                           all_q_ids=all_q_ids, navigation_data=get_navigation_data(),
                           current_q_in_category=current_q_in_category,
                           total_q_in_category=total_q_in_category)

@app.route('/check_answer', methods=['POST'])
def check_answer():
    user_input = request.form.get('selected_answer')
    q_id = request.form.get('question_id')
    
    conn = get_db_connection()
    q = conn.execute('SELECT correct_answer, explanation FROM Questions WHERE id = ?', (q_id,)).fetchone()
    conn.close()

    if q is None: return jsonify({"error": "לא נמצא"}), 404
    
    user_clean = clean_text_for_comparison(user_input)
    db_clean = clean_text_for_comparison(q['correct_answer'])
    
    return jsonify({
        "is_correct": (user_clean == db_clean),
        "correct_answer": q['correct_answer'],
        "explanation": q['explanation']
    })

# ----------------------------------------------------------------------
# 🎓 מצב בחינה (Exam Mode)
# ----------------------------------------------------------------------

@app.route('/exam_setup')
def exam_setup():
    conn = get_db_connection()
    try:
        data = conn.execute('SELECT DISTINCT topic, sub_topic FROM Questions').fetchall()
    except sqlite3.OperationalError:
        data = []
    conn.close()
    
    topics = {}
    for row in data:
        if row['topic'] not in topics:
            topics[row['topic']] = []
        topics[row['topic']].append(row['sub_topic'])
        
    return render_template('exam_setup.html', topics=topics)

@app.route('/start_exam', methods=['POST'])
def start_exam():
    sub_topic = request.form.get('sub_topic')
    conn = get_db_connection()
    
    questions = conn.execute(
        'SELECT id FROM Questions WHERE sub_topic = ? ORDER BY id', 
        (sub_topic,)
    ).fetchall()
    conn.close()
    
    if not questions: return "לא נמצאו שאלות בנושא זה", 404
        
    question_ids = [q['id'] for q in questions]
    
    session['exam_ids'] = question_ids
    session['exam_answers'] = {}
    session['exam_sub_topic'] = sub_topic
    
    return redirect(url_for('exam_question', index=0))

@app.route('/exam/<int:index>', methods=['GET', 'POST'])
def exam_question(index):
    exam_ids = session.get('exam_ids', [])
    if not exam_ids or index >= len(exam_ids):
        return redirect(url_for('exam_setup'))
    
    # POST
    if request.method == 'POST':
        selected = request.form.get('selected_answer')
        if selected:
            current_answers = session.get('exam_answers', {})
            question_id = str(exam_ids[index])
            current_answers[question_id] = selected
            session['exam_answers'] = current_answers
            session.modified = True 
            
        action = request.form.get('action')
        
        if action == 'next': 
            return redirect(url_for('exam_question', index=index + 1))
        elif action == 'prev': 
            return redirect(url_for('exam_question', index=index - 1))
        elif action == 'finish': 
            return redirect(url_for('submit_exam'))
        elif action and action.startswith('jump_'):
            new_index = int(action.split('_')[1])
            return redirect(url_for('exam_question', index=new_index))

    # GET
    question_id = exam_ids[index]
    conn = get_db_connection()
    question = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    conn.close()
    
    options = [question['correct_answer'], question['distractor_1'], question['distractor_2'], question['distractor_3']]
    options = [o for o in options if o and o.strip()]
    random.shuffle(options)
    
    user_selection = session.get('exam_answers', {}).get(str(question_id))

    # בניית הנתונים לסרגל
    user_answers = session.get('exam_answers', {})
    exam_nav = []
    for i, q_id in enumerate(exam_ids):
        status = 'default'
        if str(q_id) in user_answers:
            status = 'answered'
        if i == index:
            status = 'active'
            
        exam_nav.append({
            'index': i,
            'number': i + 1,
            'status': status
        })

    return render_template('exam_question.html', 
                           question=question, 
                           options=options, 
                           index=index, 
                           total=len(exam_ids),
                           user_selection=user_selection,
                           exam_nav=exam_nav, 
                           sub_topic=session.get('exam_sub_topic'))

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
        
        user_ans = user_answers.get(str(q_id), "")
        original_correct = q['correct_answer']
        
        user_clean = clean_text_for_comparison(user_ans)
        db_clean = clean_text_for_comparison(original_correct)
        
        is_correct = (user_clean == db_clean) and (user_clean != "")
        
        if is_correct: score += 1
            
        results.append({
            'question': q,
            'user_answer': user_ans,
            'correct_answer': original_correct,
            'is_correct': is_correct,
            'explanation': q['explanation']
        })
    conn.close()
    
    final_score = int((score / len(exam_ids)) * 100)
    
    return render_template('exam_result.html', score=final_score, results=results, total=len(exam_ids), correct_count=score)

# =======================================================
# 🚀 הפעלה אוטומטית של טעינת הנתונים (גם ב-Flask Run)
# =======================================================

# השורה הזו מבטיחה שהפונקציה תרוץ מיד כש-app.py נטען
with app.app_context():
    setup_database()

if __name__ == '__main__':
    app.run(debug=True)