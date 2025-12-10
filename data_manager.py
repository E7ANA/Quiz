# data_manager.py

import sqlite3
import json

# הגדרת קובץ מסד הנתונים
DB_FILE = 'quiz_db.sqlite'

# פונקציה עזר להתחברות
def get_db_connection():
    """יוצר חיבור למסד הנתונים."""
    conn = sqlite3.connect(DB_FILE)
    return conn

def insert_question(question_data: dict):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        q_text = question_data['question_text']
        c_answer = question_data['correct_answer']
        d1 = question_data.get('distractor_1')
        d2 = question_data.get('distractor_2')
        d3 = question_data.get('distractor_3')
        explanation = question_data.get('explanation')
        topic = question_data.get('topic', 'כללי')
        # שדה חדש: תת-נושא (למשל: פרק 1)
        sub_topic = question_data.get('sub_topic', 'ללא פרק') 

        sql_insert = """
            INSERT INTO Questions (
                question_text, correct_answer, distractor_1, distractor_2, distractor_3, explanation, topic, sub_topic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        cursor.execute(sql_insert, (
            q_text, c_answer, d1, d2, d3, explanation, topic, sub_topic
        ))

        conn.commit()
        conn.close()
        print(f"✅ השאלה הוכנסה לפרק '{sub_topic}'.")
        return True

    except sqlite3.Error as e:
        print(f"❌ שגיאה ב-SQLite: {e}")
        return False
    except KeyError as e:
        print(f"❌ חסר שדה חובה: {e}")
        return False
    """
    מכניס שאלה בודדת (כמילון) למסד הנתונים.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # חילוץ הנתונים מהמילון (בהתאם לפורמט ה-JSON שקבענו)
        q_text = question_data['question_text']
        c_answer = question_data['correct_answer']
        
        # שימוש ב-get() עם ערך ברירת מחדל ריק (None) למסיחים והסבר, כדי למנוע שגיאות אם NotebookLM משמיט שדה אופציונלי
        d1 = question_data.get('distractor_1')
        d2 = question_data.get('distractor_2')
        d3 = question_data.get('distractor_3')
        explanation = question_data.get('explanation')
        topic = question_data.get('topic', 'לא מוגדר') # ערך ברירת מחדל לנושא

        # פקודת ה-SQL להכנסת נתונים
        sql_insert = """
            INSERT INTO Questions (
                question_text, correct_answer, distractor_1, distractor_2, distractor_3, explanation, topic
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        
        cursor.execute(sql_insert, (
            q_text, c_answer, d1, d2, d3, explanation, topic
        ))

        conn.commit()
        conn.close()
        print(f"✅ השאלה '{q_text[:40]}...' הוכנסה בהצלחה.")
        return True

    except sqlite3.Error as e:
        print(f"❌ אירעה שגיאה ב-SQLite: {e}")
        return False
    except KeyError as e:
        print(f"❌ חסר שדה חובה בנתוני השאלה (KeyError): {e}. נדרש question_text או correct_answer.")
        return False


def load_questions_from_file(file_path: str):
    """
    טוען נתונים מקובץ JSON ומכניס אותם לבסיס הנתונים.
    הקובץ יכול להכיל אובייקט JSON בודד (מילון) או רשימה של אובייקטים.
    """
    print(f"\n--- מתחיל טעינת נתונים מ- {file_path} ---")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f) 
            
            inserted_count = 0
            
            # אם NotebookLM יצר רשימה של שאלות
            if isinstance(data, list):
                for question in data:
                    if insert_question(question):
                        inserted_count += 1
            
            # אם הקובץ הוא שאלה אחת בודדת (מילון)
            elif isinstance(data, dict):
                if insert_question(data):
                    inserted_count += 1
            
            print(f"\n✅ סיום טעינה: הוזנו סך הכל {inserted_count} שאלות.")

    except FileNotFoundError:
        print(f"❌ שגיאה: קובץ לא נמצא בנתיב: {file_path}")
    except json.JSONDecodeError as e:
        print(f"❌ שגיאה בפענוח JSON: ודא שהפורמט תקין. ייתכן שחסר פסיק או סוגר. שגיאה: {e}")


if __name__ == '__main__':
    # -------------------------------------------------------------------------
    # דוגמה לשימוש בסקריפט
    # -------------------------------------------------------------------------
    
    # 1. צור קובץ JSON בתיקייה בשם 'questions.json' 
    #    (או שנה את השם למטה בהתאם לשם שנתן NotebookLM).
    
    # 2. הריץ את הפקודה בטרמינל:
    #    python3 data_manager.py
    
    # הערה: אם אתה רוצה לבדוק עם שאלה מובנית (ללא קריאת קובץ חיצוני):
    # sample_question_data = { ... }
    # insert_question(sample_question_data) 
    
    # טעינת כל השאלות מקובץ questions.json
    load_questions_from_file('questions.json')