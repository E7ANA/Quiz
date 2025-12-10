# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import random
import json
import os
import re
import html  # 💥 חדש: ספרייה לטיפול בקודי HTML

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

def get_navigation_data():
    conn = get_db_connection()
    # המיון ORDER BY topic, id מבטיח שהמספור יהיה הגיוני ועוקב
    questions = conn.execute(
        'SELECT id, question_text, topic, sub_topic FROM Questions ORDER BY topic, id' 
    ).fetchall()
    conn.close()
    
    navigation_tree = {}
    topic_counters = {} # מונה לכל נושא ראשי
    
    for q in questions:
        topic = q['topic']
        sub_topic = q['sub_topic']
        
        # אתחול נושא חדש
        if topic not in navigation_tree:
            navigation_tree[topic] = {'sub_topics': {}}
            topic_counters[topic] = 0 # איפוס מונה לנושא
        
        # קידום המונה
        topic_counters[topic] += 1
        
        if sub_topic not in navigation_tree[topic]['sub_topics']:
            navigation_tree[topic]['sub_topics'][sub_topic] = []
            
        # יצירת הטקסט עם המספר
        q_text = q['question_text']
        short_text = q_text[:40] + '...' if len(q_text) > 40 else q_text
        numbered_text = f"{topic_counters[topic]}. {short_text}" # דוגמה: "1. מטופל..."
        
        navigation_tree[topic]['sub_topics'][sub_topic].append({
            'id': q['id'],
            'text': numbered_text
        })
        
    return navigation_tree
# 💥 פונקציית הניקוי האגרסיבית והבטוחה ביותר 💥
def clean_text_for_comparison(text):
    if not text:
        return ""
    
    # 1. המרה של קודי HTML (כמו &#39;) חזרה לסימנים רגילים (')
    text = html.unescape(text)
    
    # 2. שינוי לאותיות קטנות
    text = text.lower()
    
    # 3. השארת אותיות ומספרים בלבד (מוחק רווחים, גרשיים, סוגריים, הכל!)
    # בסוף נשאר משהו כמו: "hodgkinslymphoma"
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
        q = conn.execute('SELECT id FROM Questions WHERE topic = ? ORDER BY id LIMIT 1', (topic,)).fetchone()
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
    
    next_q = conn.execute('SELECT id FROM Questions WHERE id > ? ORDER BY id LIMIT 1', (question_id,)).fetchone()
    prev_q = conn.execute('SELECT id FROM Questions WHERE id < ? ORDER BY id DESC LIMIT 1', (question_id,)).fetchone()
    all_q_ids = [q['id'] for q in conn.execute('SELECT id FROM Questions ORDER BY id').fetchall()]
    conn.close()

    options = [question['correct_answer'], question['distractor_1'], question['distractor_2'], question['distractor_3']]
    options = [o for o in options if o and o.strip()]
    random.shuffle(options)
    
    return render_template('question.html', 
                           question=question, options=options, 
                           next_id=next_q['id'] if next_q else None,
                           prev_id=prev_q['id'] if prev_q else None,
                           all_q_ids=all_q_ids, navigation_data=get_navigation_data())

@app.route('/check_answer', methods=['POST'])
def check_answer():
    user_input = request.form.get('selected_answer')
    q_id = request.form.get('question_id')
    
    conn = get_db_connection()
    q = conn.execute('SELECT correct_answer, explanation FROM Questions WHERE id = ?', (q_id,)).fetchone()
    conn.close()

    if q is None: return jsonify({"error": "לא נמצא"}), 404
    
    # 💥 ניקוי והשוואה
    user_clean = clean_text_for_comparison(user_input)
    db_clean = clean_text_for_comparison(q['correct_answer'])
    
    # 🕵️ הדפסת דיבאג לטרמינל - תראה את זה כשתלחץ על כפתור
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