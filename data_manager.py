import sqlite3
import json
import os

DB_FILE = 'quiz_db.sqlite'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    # הוספנו את העמודה source_file
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_text TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            distractor_1 TEXT,
            distractor_2 TEXT,
            distractor_3 TEXT,
            explanation TEXT,
            topic TEXT,
            sub_topic TEXT,
            image_path TEXT,
            source_file TEXT
        );
    """)
    conn.commit()
    conn.close()

def insert_question(question_data: dict, filename: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        q_text = question_data.get('question_text')
        c_answer = question_data.get('correct_answer')
        
        # תמיכה ברשימת תשובות (המרה ל-JSON string אם זה list)
        if isinstance(c_answer, list):
            c_answer = json.dumps(c_answer, ensure_ascii=False)

        if not q_text or not c_answer:
            return False

        img_path = question_data.get('image') 

        sql_insert = """
            INSERT INTO Questions (
                question_text, correct_answer, distractor_1, distractor_2, 
                distractor_3, explanation, topic, sub_topic, image_path, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        cursor.execute(sql_insert, (
            q_text, c_answer, 
            question_data.get('distractor_1'), 
            question_data.get('distractor_2'), 
            question_data.get('distractor_3'), 
            question_data.get('explanation'), 
            question_data.get('topic', 'כללי'), 
            question_data.get('sub_topic', 'ללא פרק'),
            img_path,
            filename
        ))

        conn.commit()
        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"❌ שגיאה ב-SQLite: {e}")
        return False

def load_questions_from_file(file_path: str):
    if not os.path.exists(file_path):
        return

    print(f"--- טוען קובץ: {file_path} ---")
    create_tables()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            content = data
            if isinstance(data, dict) and 'fullContent' in data:
                content = data['fullContent']

            count = 0
            filename = os.path.basename(file_path)

            if isinstance(content, list):
                for q in content:
                    if insert_question(q, filename): count += 1
            elif isinstance(content, dict):
                if insert_question(content, filename): count += 1
            
            print(f"✅ נטענו {count} שאלות.")

    except json.JSONDecodeError as e:
        print(f"❌ שגיאה ב-JSON: {e}")

def update_json_file(filename, original_q_text, new_data):
    """עדכון הקובץ הפיזי בדיסק"""
    if not os.path.exists(filename):
        return False, "קובץ לא נמצא"
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        questions_list = data
        if isinstance(data, dict) and 'fullContent' in data:
            questions_list = data['fullContent']
        
        found = False
        for q in questions_list:
            # זיהוי השאלה לפי הטקסט המקורי (לפני השינוי)
            if q.get('question_text') == original_q_text:
                q['question_text'] = new_data['question_text']
                
                # אם התשובה היא JSON List, נשמור אותה כרשימה אמיתית בקובץ
                try:
                    parsed_ans = json.loads(new_data['correct_answer'])
                    if isinstance(parsed_ans, list):
                        q['correct_answer'] = parsed_ans
                    else:
                        q['correct_answer'] = new_data['correct_answer']
                except:
                    q['correct_answer'] = new_data['correct_answer']

                q['distractor_1'] = new_data['distractor_1']
                q['distractor_2'] = new_data['distractor_2']
                q['distractor_3'] = new_data['distractor_3']
                q['explanation'] = new_data['explanation']
                q['image'] = new_data['image_path']
                q['topic'] = new_data['topic']
                q['sub_topic'] = new_data['sub_topic']
                found = True
                break
        
        if found:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True, "עודכן בהצלחה"
        else:
            return False, "השאלה המקורית לא נמצאה בקובץ"

    except Exception as e:
        return False, str(e)