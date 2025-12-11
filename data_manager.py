# data_manager.py

import sqlite3
import json
import os

DB_FILE = 'quiz_db.sqlite'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    """יוצר את הטבלה מחדש עם תמיכה בתמונות"""
    conn = get_db_connection()
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
            image_path TEXT
        );
    """)
    conn.commit()
    conn.close()
    print("✅ טבלאות נבדקו/נוצרו בהצלחה.")

def insert_question(question_data: dict):
    """מכניס שאלה בודדת למסד הנתונים"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        q_text = question_data.get('question_text')
        c_answer = question_data.get('correct_answer')
        
        # בדיקה בסיסית שקיימים שדות חובה
        if not q_text or not c_answer:
            return False

        # שליפת שם התמונה (אם קיים ב-JSON, אחרת None)
        img_path = question_data.get('image') 

        sql_insert = """
            INSERT INTO Questions (
                question_text, correct_answer, distractor_1, distractor_2, 
                distractor_3, explanation, topic, sub_topic, image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        cursor.execute(sql_insert, (
            q_text, c_answer, 
            question_data.get('distractor_1'), 
            question_data.get('distractor_2'), 
            question_data.get('distractor_3'), 
            question_data.get('explanation'), 
            question_data.get('topic', 'כללי'), 
            question_data.get('sub_topic', 'ללא פרק'),
            img_path 
        ))

        conn.commit()
        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"❌ שגיאה ב-SQLite: {e}")
        return False

# זו הפונקציה שהייתה חסרה לך:
def load_questions_from_file(file_path: str):
    """טוען שאלות מקובץ JSON"""
    if not os.path.exists(file_path):
        print(f"❌ הקובץ {file_path} לא נמצא.")
        return

    print(f"--- מתחיל טעינת נתונים מ- {file_path} ---")
    
    # וידוא שהטבלה קיימת לפני הטעינה
    create_tables()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            count = 0
            if isinstance(data, list):
                for q in data:
                    if insert_question(q): count += 1
            elif isinstance(data, dict):
                if insert_question(data): count += 1
            
            print(f"✅ סיום טעינה: נוספו {count} שאלות.")

    except json.JSONDecodeError as e:
        print(f"❌ שגיאה בפענוח JSON: {e}")