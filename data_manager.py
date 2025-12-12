import sqlite3
import json
import os

DB_FILE = 'quiz_db.sqlite'

def get_db_connection():
    # check_same_thread=False מאפשר גמישות בעבודה עם Flask
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def rebuild_database():
    """מוחק את הטבלה ויוצר אותה מחדש נקייה"""
    print("♻️  בונה מחדש את מסד הנתונים...")
    conn = get_db_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS Questions;")
        conn.execute("""
            CREATE TABLE Questions (
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
        print("✅ טבלאות נוצרו בהצלחה.")
    except Exception as e:
        print(f"❌ שגיאה בבניית DB: {e}")
    finally:
        conn.close()

def insert_question(question_data: dict, filename: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        q_text = question_data.get('question_text')
        c_answer = question_data.get('correct_answer')
        
        # המרה ל-JSON string אם זו רשימה (עבור בחירה מרובה)
        if isinstance(c_answer, list):
            c_answer = json.dumps(c_answer, ensure_ascii=False)
        # המרה למחרוזת אם זה מספר או משהו אחר
        else:
            c_answer = str(c_answer)

        if not q_text or not c_answer:
            return False

        sql = """
            INSERT INTO Questions (
                question_text, correct_answer, distractor_1, distractor_2, 
                distractor_3, explanation, topic, sub_topic, image_path, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        cursor.execute(sql, (
            q_text, 
            c_answer, 
            str(question_data.get('distractor_1', '') or ''), 
            str(question_data.get('distractor_2', '') or ''), 
            str(question_data.get('distractor_3', '') or ''), 
            question_data.get('explanation', ''), 
            question_data.get('topic', 'כללי'), 
            question_data.get('sub_topic', 'ללא פרק'),
            question_data.get('image', ''), # שים לב: ב-JSON זה 'image', ב-DB זה 'image_path'
            filename
        ))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"❌ שגיאה בהכנסת שאלה: {e}")
        return False
    finally:
        conn.close()

def load_questions_from_file(file_path: str):
    if not os.path.exists(file_path):
        return

    print(f"--- טוען קובץ: {file_path} ---")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # תמיכה בפורמט dict עם fullContent או list ישיר
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
            
            print(f"✅ נטענו {count} שאלות מתוך {filename}.")

    except Exception as e:
        print(f"❌ שגיאה בטעינת הקובץ {file_path}: {e}")

def update_json_file(filename, original_q_text, new_data):
    if not os.path.exists(filename): return False, "קובץ לא נמצא"
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # זיהוי מבנה הקובץ
        content_list = data
        is_wrapper = False
        if isinstance(data, dict) and 'fullContent' in data:
            content_list = data['fullContent']
            is_wrapper = True
        
        found = False
        for q in content_list:
            if q.get('question_text') == original_q_text:
                q['question_text'] = new_data['question_text']
                
                # נסיון להמיר חזרה לרשימה אם זה JSON valid
                try:
                    parsed = json.loads(new_data['correct_answer'])
                    q['correct_answer'] = parsed if isinstance(parsed, list) else new_data['correct_answer']
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
        return False, "השאלה המקורית לא נמצאה"

    except Exception as e:
        return False, str(e)

def delete_question_from_file(filename, question_text):
    if not os.path.exists(filename): return False
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        content_list = data
        is_wrapper = False
        if isinstance(data, dict) and 'fullContent' in data:
            content_list = data['fullContent']
            is_wrapper = True
        
        # סינון (יצירת רשימה חדשה ללא השאלה המדוברת)
        original_len = len(content_list)
        new_list = [q for q in content_list if q.get('question_text') != question_text]
        
        if len(new_list) == original_len:
            return False # לא נמצאה שאלה למחיקה

        if is_wrapper:
            data['fullContent'] = new_list
        else:
            data = new_list
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Error deleting: {e}")
        return False