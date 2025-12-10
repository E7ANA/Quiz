import sqlite3

DB_FILE = 'quiz_db.sqlite'

def create_database():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # הוספנו את sub_topic
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_text TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                distractor_1 TEXT,
                distractor_2 TEXT,
                distractor_3 TEXT,
                explanation TEXT,
                topic TEXT,
                sub_topic TEXT  
            );
        """)
        
        conn.commit()
        conn.close()
        print("✅ מסד הנתונים שודרג (כולל sub_topic).")

    except sqlite3.Error as e:
        print(f"❌ שגיאה: {e}")

if __name__ == '__main__':
    create_database()