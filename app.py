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
app.secret_key = 'quiz_secret_key_123' 

DB_FILE = 'quiz_db.sqlite'
QUESTIONS_PATTERN = '*.json' 

# ----------------------------------------------------------------------
# 🖼️ תמונות
# ----------------------------------------------------------------------
@app.route('/custom_img/<path:filename>')
def serve_image(filename):
    decoded = unquote(filename)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, 'static', 'images', decoded)
    if os.path.exists(path):
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
    return "Image not found", 404

# ----------------------------------------------------------------------
# 🔧 עזרים
# ----------------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def clean_text_for_comparison(text):
    if not text: return ""
    return re.sub(r'[^a-z0-9א-ת]', '', html.unescape(str(text)).lower())

def get_navigation_data():
    conn = get_db_connection()
    try: 
        q_list = conn.execute('SELECT id, question_text, topic, sub_topic FROM Questions ORDER BY topic, sub_topic, id').fetchall()
    except: 
        return {}
    finally:
        conn.close()
    
    tree = {}
    counters = {}
    
    for q in q_list:
        t, st = q['topic'], q['sub_topic']
        if t not in tree: tree[t] = {'sub_topics': {}}
        if st not in tree[t]['sub_topics']: 
            tree[t]['sub_topics'][st] = []
            counters[(t, st)] = 0
        counters[(t, st)] += 1
        tree[t]['sub_topics'][st].append({'id': q['id'], 'number': counters[(t, st)], 'text': q['question_text']})
    return tree

# ----------------------------------------------------------------------
# ✏️ עריכה
# ----------------------------------------------------------------------
@app.route('/edit_question/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    conn = get_db_connection()
    q_row = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    conn.close()
    
    if not q_row: return "לא נמצא", 404
    q = dict(q_row)

    if request.method == 'POST':
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
        
        conn = get_db_connection()
        conn.execute('''
            UPDATE Questions SET 
            question_text=?, correct_answer=?, distractor_1=?, distractor_2=?, 
            distractor_3=?, explanation=?, topic=?, sub_topic=?, image_path=?
            WHERE id=?
        ''', (*new_data.values(), question_id))
        conn.commit()
        conn.close()
        
        data_manager.update_json_file(q['source_file'], q['question_text'], new_data)
        return redirect(url_for('get_question', question_id=question_id, edited='true'))

    options, indices = [], []
    try:
        parsed = json.loads(q['correct_answer'])
        if isinstance(parsed, list):
            options.extend(parsed)
            indices = list(range(len(parsed)))
        else:
            options.append(str(parsed))
            indices = [0]
    except:
        options.append(q['correct_answer'])
        indices = [0]

    for d in ['distractor_1', 'distractor_2', 'distractor_3']:
        if q[d]: options.append(q[d])
    
    while len(options) < 4: options.append("")
    return render_template('edit_question.html', q=q, options=options, correct_indices=indices)

# ----------------------------------------------------------------------
# 🗑️ מחיקה
# ----------------------------------------------------------------------
@app.route('/delete_question/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    conn = get_db_connection()
    q = conn.execute('SELECT * FROM Questions WHERE id = ?', (question_id,)).fetchone()
    
    if not q:
        conn.close()
        return "לא נמצא", 404
        
    data_manager.delete_question_from_file(q['source_file'], q['question_text'])
    
    conn.execute('DELETE FROM Questions WHERE id = ?', (question_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

# ----------------------------------------------------------------------
# 🔍 בדיקה
# ----------------------------------------------------------------------
@app.route('/check_answer', methods=['POST'])
def check_answer():
    user_picks = request.form.getlist('selected_answer')
    q_id = request.form.get('question_id')
    
    conn = get_db_connection()
    q = conn.execute('SELECT correct_answer, explanation FROM Questions WHERE id=?', (q_id,)).fetchone()
    conn.close()
    
    if not q: return jsonify({"error": "Error"}), 404

    try: 
        correct_list = json.loads(q['correct_answer'])
        if not isinstance(correct_list, list): correct_list = [str(correct_list)]
    except: 
        correct_list = [q['correct_answer']]

    u_clean = {clean_text_for_comparison(x) for x in user_picks}
    c_clean = {clean_text_for_comparison(x) for x in correct_list}
    
    is_correct = (u_clean == c_clean) and (len(u_clean) > 0)
    is_partial = (len(u_clean.intersection(c_clean)) > 0) and not is_correct
    
    status = "wrong"
    msg = "❌ שגוי."
    
    if is_correct:
        status = "correct"
        msg = "✅ נכון!"
    elif is_partial:
        status = "partial"
        missing = len(c_clean) - len(u_clean.intersection(c_clean))
        msg = f"⚠️ תשובה חלקית (חסרות {missing})."
    
    return jsonify({
        "status": status, 
        "correct_answers": correct_list, 
        "message": msg, 
        "explanation": q['explanation']
    })

# ----------------------------------------------------------------------
# 🧭 ניווט
# ----------------------------------------------------------------------
@app.route('/')
def index():
    conn = get_db_connection()
    try: 
        topics = conn.execute('SELECT DISTINCT topic FROM Questions').fetchall()
        count = conn.execute('SELECT COUNT(*) as cnt FROM Questions').fetchone()['cnt']
    except: 
        topics, count = [], 0
    conn.close()
    return render_template('index.html', topics=topics, total_questions=count)

@app.route('/quiz')
def start_quiz():
    topic = request.args.get('topic')
    conn = get_db_connection()
    if topic:
        q = conn.execute('SELECT id FROM Questions WHERE topic=? ORDER BY sub_topic, id LIMIT 1', (topic,)).fetchone()
    else:
        q = conn.execute('SELECT id FROM Questions ORDER BY id LIMIT 1').fetchone()
    conn.close()
    return redirect(url_for('get_question', question_id=q['id'])) if q else redirect(url_for('index'))

@app.route('/question/<int:question_id>')
def get_question(question_id):
    conn = get_db_connection()
    q = conn.execute('SELECT * FROM Questions WHERE id=?', (question_id,)).fetchone()
    if not q: return "השאלה לא נמצאה (אולי נמחקה או DB לא אותחל)", 404
    
    sub = q['sub_topic']
    all_qs = conn.execute('SELECT id FROM Questions WHERE sub_topic=? ORDER BY id', (sub,)).fetchall()
    ids = [row['id'] for row in all_qs]
    conn.close()
    
    idx = ids.index(question_id) if question_id in ids else 0
    next_id = ids[idx+1] if idx+1 < len(ids) else None
    prev_id = ids[idx-1] if idx > 0 else None
    
    opts = []
    try: 
        parsed = json.loads(q['correct_answer'])
        opts.extend(parsed if isinstance(parsed, list) else [str(parsed)])
    except: 
        opts.append(q['correct_answer'])
    
    for d in ['distractor_1', 'distractor_2', 'distractor_3']:
        if q[d]: opts.append(q[d])
    random.shuffle(opts)
    
    return render_template('question.html', question=q, options=opts, 
                           next_id=next_id, prev_id=prev_id,
                           navigation_data=get_navigation_data(),
                           current_q_in_category=idx+1, total_q_in_category=len(ids))

# ----------------------------------------------------------------------
# 🎓 בחינה
# ----------------------------------------------------------------------
@app.route('/exam_setup')
def exam_setup():
    conn = get_db_connection()
    data = conn.execute('SELECT DISTINCT topic, sub_topic FROM Questions').fetchall()
    conn.close()
    topics = {}
    for r in data:
        if r['topic'] not in topics: topics[r['topic']] = []
        if r['sub_topic'] not in topics[r['topic']]: topics[r['topic']].append(r['sub_topic'])
    return render_template('exam_setup.html', topics=topics)

@app.route('/start_exam', methods=['POST'])
def start_exam():
    sub = request.form.get('sub_topic')
    conn = get_db_connection()
    ids = [r['id'] for r in conn.execute('SELECT id FROM Questions WHERE sub_topic=? ORDER BY id', (sub,)).fetchall()]
    conn.close()
    if not ids: return "ריק", 404
    session['exam_ids'] = ids
    session['exam_answers'] = {}
    session['exam_sub_topic'] = sub
    return redirect(url_for('exam_question', index=0))

@app.route('/exam/<int:index>', methods=['GET', 'POST'])
def exam_question(index):
    ids = session.get('exam_ids', [])
    if not ids or index >= len(ids): return redirect(url_for('exam_setup'))
    
    if request.method == 'POST':
        sel = request.form.getlist('selected_answer')
        if sel:
            ans = session.get('exam_answers', {})
            ans[str(ids[index])] = sel if len(sel) > 1 else sel[0]
            session['exam_answers'] = ans
            session.modified = True
        
        act = request.form.get('action')
        if act == 'next': return redirect(url_for('exam_question', index=index+1))
        elif act == 'prev': return redirect(url_for('exam_question', index=index-1))
        elif act == 'finish': return redirect(url_for('submit_exam'))
        elif act and 'jump_' in act: return redirect(url_for('exam_question', index=int(act.split('_')[1])))

    conn = get_db_connection()
    q = conn.execute('SELECT * FROM Questions WHERE id=?', (ids[index],)).fetchone()
    conn.close()
    
    opts = []
    try: 
        parsed = json.loads(q['correct_answer'])
        opts.extend(parsed if isinstance(parsed, list) else [str(parsed)])
    except: opts.append(q['correct_answer'])
    for d in ['distractor_1', 'distractor_2', 'distractor_3']:
        if q[d]: opts.append(q[d])
    random.shuffle(opts)
    
    user_sel = session.get('exam_answers', {}).get(str(ids[index]))
    if user_sel and not isinstance(user_sel, list): user_sel = [user_sel]
    
    nav = [{'index': i, 'number': i+1, 'status': 'answered' if str(uid) in session.get('exam_answers',{}) else 'default'} for i, uid in enumerate(ids)]
    nav[index]['status'] = 'active'
    
    return render_template('exam_question.html', question=q, options=opts, index=index, total=len(ids), user_selection=user_sel or [], exam_nav=nav, sub_topic=session.get('exam_sub_topic'))

@app.route('/submit_exam')
def submit_exam():
    ids = session.get('exam_ids', [])
    ans = session.get('exam_answers', {})
    if not ids: return redirect(url_for('exam_setup'))
    
    score, results = 0, []
    conn = get_db_connection()
    for qid in ids:
        q = conn.execute('SELECT * FROM Questions WHERE id=?', (qid,)).fetchone()
        
        u_raw = ans.get(str(qid))
        u_list = u_raw if isinstance(u_raw, list) else ([u_raw] if u_raw else [])
        u_clean = {clean_text_for_comparison(x) for x in u_list}
        
        try: c_list = json.loads(q['correct_answer'])
        except: c_list = [q['correct_answer']]
        if not isinstance(c_list, list): c_list = [str(c_list)]
        c_clean = {clean_text_for_comparison(x) for x in c_list}
        
        is_corr = (u_clean == c_clean) and len(u_clean) > 0
        if is_corr: score += 1
        
        results.append({
            'question': q,
            'user_answer': ", ".join(u_list),
            'correct_answer': ", ".join(c_list),
            'is_correct': is_corr,
            'is_partial': len(u_clean.intersection(c_clean)) > 0 and not is_corr,
            'explanation': q['explanation']
        })
    conn.close()
    return render_template('exam_result.html', score=int((score/len(ids))*100) if ids else 0, results=results, total=len(ids), correct_count=score)

# ----------------------------------------------------------------------
# 🚀 אתחול - התיקון החשוב: קריאה מחוץ ל-main
# ----------------------------------------------------------------------
def setup_database():
    try:
        data_manager.rebuild_database()
        files = glob.glob(QUESTIONS_PATTERN)
        if files:
            for f in files:
                data_manager.load_questions_from_file(f)
            print(f"✅ DB אותחל. נטענו {len(files)} קבצים.")
        else:
            print("⚠️ לא נמצאו קבצי JSON!")
    except Exception as e:
        print(f"❌ שגיאה באתחול: {e}")

# קריאה לאתחול מיד עם טעינת המודול, כך שזה ירוץ גם ב-flask run
with app.app_context():
    setup_database()

if __name__ == '__main__':
    app.run(debug=True)