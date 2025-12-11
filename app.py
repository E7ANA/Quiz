# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
import sqlite3
import random
import os
import re
import html
import glob
import data_manager
from urllib.parse import unquote  # קריטי לטיפול ברווחים בשמות קבצים

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_quiz_app_123' 

DB_FILE = 'quiz_db.sqlite'
QUESTIONS_PATTERN = 'questions*.json' 

# ----------------------------------------------------------------------
# 🖼️ נתיב מיוחד להגשת תמונות (פתרון לרווחים ולמיקום)
# ----------------------------------------------------------------------
@app.route('/custom_img/<path:filename>')
def serve_image(filename):
    # 1. ניקוי השם (הופך %20 לרווח רגיל)
    decoded_filename = unquote(filename)
    
    # 2. חישוב נתיב אבסולוטי לפי מיקום הקובץ app.py
    # זה מבטיח שהמערכת מחפשת בתיקייה הנכונה בדיוק, לא משנה מאיפה הרצת
    current_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(current_dir, 'static', 'images')
    full_path = os.path.join(images_dir, decoded_filename)
    
    # 3. הדפסות דיבוג לטרמינל (כדי שתוכל לראות אם יש בעיה)
    print(f"\n📸 --- בקשת תמונה ---")
    print(f"📂 נתיב התיקייה: {images_dir}")
    print(f"🔎 מחפש קובץ: '{decoded_filename}'")
    
    if os.path.exists(full_path):
        print("✅ הקובץ נמצא! מגיש אותו...")
        return send_from_directory(images_dir, decoded_filename)
    else:
        print(f"❌ הקובץ לא נמצא בנתיב: {full_path}")
        # בדיקה מה כן קיים בתיקייה (עוזר מאוד לפתרון בעיות)
        if os.path.exists(images_dir):
            print("👀 קבצים שכן קיימים בתיקייה הזו:")
            try:
                files = os.listdir(images_dir)
                # מדפיס רק את ה-5 הראשונים כדי לא להעמיס
                for f in files[:5]: 
                    print(f"   - '{f}'")
                if len(files) > 5: print("   ... (ועוד קבצים)")
            except Exception as e:
                print(f"   שגיאה בקריאת התיקייה: {e}")
        else:
            print("❌ שגיאה חמורה: התיקייה static/images בכלל לא קיימת!")
            
        return "Image not found", 404

# ----------------------------------------------------------------------
# 🔧 פונקציות עזר
# ----------------------------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_navigation_data():
    """בונה את עץ הניווט לסרגל הצד - עם מספור נפרד לכל פרק"""
    conn = get_db_connection()
    try:
        questions = conn.execute(
            'SELECT id, question_text, topic, sub_topic FROM Questions ORDER BY topic, sub_topic, id'
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    conn.close()
    
    navigation_tree = {}
    sub_topic_counters = {} 
    
    for q in questions:
        topic = q['topic']
        sub_topic = q['sub_topic']
        
        if topic not in navigation_tree:
            navigation_tree[topic] = {'sub_topics': {}}
        
        if sub_topic not in navigation_tree[topic]['sub_topics']:
            navigation_tree[topic]['sub_topics'][sub_topic] = []
            sub_topic_counters[(topic, sub_topic)] = 0
            
        sub_topic_counters[(topic, sub_topic)] += 1
        
        navigation_tree[topic]['sub_topics'][sub_topic].append({
            'id': q['id'],
            'number': sub_topic_counters[(topic, sub_topic)],
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
# 🔄 אתחול נתונים (תומך בריבוי קבצים ומחיקה בכל ריצה)
# ----------------------------------------------------------------------

def setup_database():
    print("\n🔄 --- אתחול מערכת: טעינת שאלות ---")
    
    # 1. מחיקת דאטה-בייס ישן
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print("🗑️  מסד הנתונים הישן נמחק.")
        except OSError:
            print("⚠️  לא ניתן למחוק את הקובץ (אולי פתוח?).")

    # 2. יצירה מחדש
    data_manager.create_tables()
    
    # 3. טעינת כל הקבצים שמתאימים לתבנית
    files = glob.glob(QUESTIONS_PATTERN)
    
    if not files:
        print(f"⚠️  לא נמצאו קבצי שאלות (חיפשתי: {QUESTIONS_PATTERN})")
        # ניסיון הדפסת מיקום נוכחי לעזרה
        print(f"📍 תיקיית העבודה הנוכחית: {os.getcwd()}")
    else:
        print(f"📂 נמצאו {len(files)} קבצי שאלות. מתחיל טעינה...")
        for file_path in files:
            print(f"   📥 טוען קובץ: {file_path}")
            data_manager.load_questions_from_file(file_path)
            
        print(f"✅ סיום טעינה כולל.")

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
    
    # חישוב המיקום היחסי בתוך ה-Sub-Topic בלבד
    current_sub_topic = question['sub_topic']
    
    topic_questions = conn.execute(
        'SELECT id FROM Questions WHERE sub_topic = ? ORDER BY id',
        (current_sub_topic,)
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
    
    if request.method == 'POST':
        selected = request.form.get('selected_answer')
        if selected:
            current_answers = session.get('exam_answers', {})
            question_id = str(exam_ids[index])
            current_answers[question_id] = selected
            session['exam_answers'] = current_answers
            session.modified = True 
            
        action = request.form.get('action')
        
        if action == 'next': return redirect(url_for('exam_question', index=index + 1))
        elif action == 'prev': return redirect(url_for('exam_question', index=index - 1))
        elif action == 'finish': return redirect(url_for('submit_exam'))
        elif action and action.startswith('jump_'):
            new_index = int(action.split('_')[1])
            return redirect(url_for('exam_question', index=new_index))

    question_id = exam_ids[index]
    conn = get_db_connection()
    question = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    conn.close()
    
    options = [question['correct_answer'], question['distractor_1'], question['distractor_2'], question['distractor_3']]
    options = [o for o in options if o and o.strip()]
    random.shuffle(options)
    
    user_selection = session.get('exam_answers', {}).get(str(question_id))

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
# 🚀 הפעלה אוטומטית (תומך ב-flask run וגם ב-python app.py)
# =======================================================
with app.app_context():
    setup_database()

if __name__ == '__main__':
    app.run(debug=True)