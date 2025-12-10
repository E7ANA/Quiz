# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import random
import json
import os
import re
import html

# הגדרות בסיסיות
app = Flask(__name__)
DB_FILE = 'quiz_db.sqlite'
QUESTIONS_FILE = 'questions.json'

# ----------------------------------------------------------------------
# 🔧 פונקציות עזר
# ----------------------------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn
# בתוך app.py - החלף את הפונקציה הזו בלבד

def get_navigation_data():
    conn = get_db_connection()
    # שליפה מסודרת
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
            'number': topic_counters[topic],  # 💥 המספר נשלח בנפרד לריבוע
            'text': q['question_text']        # הטקסט נשמר לטולטיפ (Tooltip)
        })
    return navigation_tree
# פונקציית הניקוי (לא שונתה)
def clean_text_for_comparison(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = text.lower()
    cleaned_text = re.sub(r'[^a-z0-9א-ת]', '', text)
    return cleaned_text

# ----------------------------------------------------------------------
# 💾 טעינת נתונים (Init)
# ----------------------------------------------------------------------

def init_dynamic_data():
    if not os.path.exists(QUESTIONS_FILE):
        print(f"❌ שגיאה: הקובץ {QUESTIONS_FILE} לא נמצא.")
        return

    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            questions_list = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ שגיאה ב-JSON: {e}")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM Questions')
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='Questions'")

        sql_insert = """
            INSERT INTO Questions (
                question_text, correct_answer, distractor_1, distractor_2, distractor_3, explanation, topic, sub_topic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        count = 0
        for q in questions_list:
            try:
                cursor.execute(sql_insert, (
                    q['question_text'], q['correct_answer'], 
                    q.get('distractor_1'), q.get('distractor_2'), q.get('distractor_3'), 
                    q.get('explanation'), q.get('topic', 'כללי'), q.get('sub_topic', 'ללא פרק')
                ))
                count += 1
            except KeyError: pass
                
        conn.commit()
        conn.close()
        print(f"✅ נטענו {count} שאלות.")
    except sqlite3.Error as e:
        print(f"❌ שגיאה ב-DB: {e}")

# ----------------------------------------------------------------------
# 🧭 ניתובים
# ----------------------------------------------------------------------

@app.route('/')
def index():
    conn = get_db_connection()
    topics = conn.execute('SELECT DISTINCT topic FROM Questions').fetchall()
    count = conn.execute('SELECT COUNT(*) as cnt FROM Questions').fetchone()['cnt']
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
        # שליפת השאלה הראשונה בנושא לפי הסדר הנכון (Sub topic ואז ID)
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

    # 💥 שליפת כל השאלות של הטופיק, מסודרות בדיוק כמו בתפריט (Sub-topic ואז ID)
    topic_questions = conn.execute(
        'SELECT id FROM Questions WHERE topic = ? ORDER BY sub_topic, id',
        (current_topic,)
    ).fetchall()
    
    # המרה לרשימת IDs כדי למצוא מיקום
    topic_ids = [q['id'] for q in topic_questions]
    
    try:
        current_index = topic_ids.index(question_id)
        current_q_in_category = current_index + 1 # המספר שיוצג (למשל 11)
        total_q_in_category = len(topic_ids)
        
        # חישוב הבא/הקודם בתוך הרשימה המסודרת של הנושא
        next_q_id = topic_ids[current_index + 1] if current_index + 1 < total_q_in_category else None
        prev_q_id = topic_ids[current_index - 1] if current_index > 0 else None
        
    except ValueError:
        current_q_in_category = 1
        total_q_in_category = 1
        next_q_id = None
        prev_q_id = None

    # עבור כפתור "סיום" בסוף הכל (לא קריטי ללוגיקה הפנימית אבל קיים)
    all_q_ids = [q['id'] for q in conn.execute('SELECT id FROM Questions ORDER BY id').fetchall()]
    conn.close()

    options = [question['correct_answer'], question['distractor_1'], question['distractor_2'], question['distractor_3']]
    options = [o for o in options if o and o.strip()]
    random.shuffle(options)
    
    return render_template('question.html', 
                           question=question, 
                           options=options, 
                           next_id=next_q_id,
                           prev_id=prev_q_id,
                           all_q_ids=all_q_ids, 
                           navigation_data=get_navigation_data(),
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
    
    # ניקוי והשוואה
    user_clean = clean_text_for_comparison(user_input)
    db_clean = clean_text_for_comparison(q['correct_answer'])
    
    # דיבאג לטרמינל
    print(f"\n--- בדיקת תשובה ---")
    print(f"Original User: {user_input}")
    print(f"Cleaned User : {user_clean}")
    print(f"Original DB  : {q['correct_answer']}")
    print(f"Cleaned DB   : {db_clean}")
    print(f"MATCH?       : {user_clean == db_clean}")
    print(f"-------------------\n")

    return jsonify({
        "is_correct": (user_clean == db_clean),
        "correct_answer": q['correct_answer'],
        "explanation": q['explanation']
    })

# הפעלה
with app.app_context():
    init_dynamic_data()

if __name__ == '__main__':
    app.run(debug=True)