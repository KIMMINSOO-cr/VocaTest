import sqlite3
from sqlite3 import Error
import os

# DB 연결 함수
def get_db_connection():
    # 현재 폴더에 vocab_db.sqlite 라는 파일로 DB 생성/연결
    db_path = os.path.join(os.path.dirname(__file__), 'vocab_db.sqlite')
    try:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row # 결과를 딕셔너리처럼 사용
        return connection
    except Error as e:
        print(f"DB 연결 오류: {e}")
        return None

# 테이블 자동 생성 (서버 켤 때 파일이 없으면 만들어줌)
def init_db():
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                word TEXT,
                meaning TEXT,
                synonyms TEXT,
                day INTEGER
            )
        ''')
        connection.commit()
        connection.close()

# 파일이 실행될 때 테이블 세팅 함수 자동 실행
init_db()

# 단어 추가 함수
def add_word(user_id, word, meaning, synonyms):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            query = "INSERT INTO words (user_id, word, meaning, synonyms) VALUES (?, ?, ?, ?)"
            values = (user_id, word, meaning, synonyms)
            cursor.execute(query, values)
            connection.commit()
        except Error as e:
            print(f"데이터 삽입 오류: {e}")
        finally:
            connection.close()

# 여러 단어 한 번에 추가하는 함수
def add_multiple_words(word_data_list):
    connection = get_db_connection()
    if connection and word_data_list:
        try:
            cursor = connection.cursor()
            query = "INSERT INTO words (word, meaning, synonyms, day, user_id) VALUES (?, ?, ?, ?, ?)"
            cursor.executemany(query, word_data_list)
            connection.commit()
        except Error as e:
            connection.rollback() # 오류 발생 시 롤백
        finally:
            connection.close()

# 랜덤 시험지 생성 함수
def generate_test(user_id, num_questions=None, day=None, start_day=None, end_day=None):
    connection = get_db_connection()
    test_paper = []
    if connection:
        try:
            cursor = connection.cursor()
            if day is not None:
                query = "SELECT id, word, meaning, synonyms FROM words WHERE user_id = ? AND day = ? ORDER BY RANDOM()"
                cursor.execute(query, (user_id, day))
            elif start_day is not None and end_day is not None:
                query = "SELECT id, word, meaning, synonyms FROM words WHERE user_id = ? AND day BETWEEN ? AND ? ORDER BY RANDOM()"
                cursor.execute(query, (user_id, start_day, end_day))
            else:
                query = "SELECT id, word, meaning, synonyms FROM words WHERE user_id = ? ORDER BY RANDOM()"
                cursor.execute(query, (user_id,))
                
            results = cursor.fetchall()
            seen_words = set()
            for row in results:
                word_lower = row['word'].lower()
                if word_lower not in seen_words:
                    seen_words.add(word_lower)
                    test_paper.append(dict(row)) # 데이터를 딕셔너리로 변환하여 추가
                    if day is None and num_questions is not None and len(test_paper) >= int(num_questions):
                        break
        finally:
            connection.close()
    return test_paper

# 등록된 Day 목록 가져오는 함수
def get_available_days(user_id):
    connection = get_db_connection()
    days = []
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT DISTINCT day FROM words WHERE user_id = ? AND day IS NOT NULL ORDER BY day", (user_id,))
            days = [row['day'] for row in cursor.fetchall()]
        finally:
            connection.close()
    return days

# 단어 ID 리스트로 정답 정보 가져오는 함수
def get_words_by_ids(user_id, id_list):
    connection = get_db_connection()
    words_data = {}
    if connection and id_list:
        try:
            cursor = connection.cursor()
            format_strings = ','.join(['?'] * len(id_list))
            query = f"SELECT id, word, meaning, synonyms FROM words WHERE user_id = ? AND id IN ({format_strings})"
            cursor.execute(query, (user_id,) + tuple(id_list))
            results = cursor.fetchall()
            for row in results:
                words_data[str(row['id'])] = dict(row)
        finally:
            connection.close()
    return words_data

# 전체 단어 목록 가져오는 함수 (페이지네이션 적용)
def get_all_words(user_id, day=None, page=1, per_page=50):
    connection = get_db_connection()
    words = []
    if connection:
        try:
            cursor = connection.cursor()
            offset = (page - 1) * per_page
            if day:
                cursor.execute("SELECT id, day, word, meaning, synonyms FROM words WHERE user_id = ? AND day = ? ORDER BY day ASC, word ASC LIMIT ? OFFSET ?", (user_id, day, per_page, offset))
            else:
                cursor.execute("SELECT id, day, word, meaning, synonyms FROM words WHERE user_id = ? ORDER BY day ASC, word ASC LIMIT ? OFFSET ?", (user_id, per_page, offset))
            words = [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()
    return words

# 전체 단어 개수를 세는 함수 (페이지 수 계산용)
def get_total_words_count(user_id, day=None):
    connection = get_db_connection()
    count = 0
    if connection:
        try:
            cursor = connection.cursor()
            if day:
                cursor.execute("SELECT COUNT(*) as cnt FROM words WHERE user_id = ? AND day = ?", (user_id, day))
            else:
                cursor.execute("SELECT COUNT(*) as cnt FROM words WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            count = result['cnt'] if result else 0
        finally:
            connection.close()
    return count

# 특정 단어 1개 정보만 가져오는 함수 (수정용)
def get_word_by_id(user_id, word_id):
    connection = get_db_connection()
    word = None
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT id, day, word, meaning, synonyms FROM words WHERE user_id = ? AND id = ?", (user_id, word_id))
            res = cursor.fetchone()
            if res:
                word = dict(res)
        finally:
            connection.close()
    return word

# 특정 단어 수정 함수
def update_word(user_id, word_id, day, word, meaning, synonyms):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("UPDATE words SET day=?, word=?, meaning=?, synonyms=? WHERE user_id=? AND id=?",
                           (day, word, meaning, synonyms, user_id, word_id))
            connection.commit()
        finally:
            connection.close()

# 특정 단어 삭제 함수
def delete_word(user_id, word_id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM words WHERE user_id = ? AND id = ?", (user_id, word_id))
            connection.commit()
        finally:
            connection.close()

# --- 회원가입 / 로그인 관련 함수 ---
def get_user_by_username(username):
    connection = get_db_connection()
    user = None
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            res = cursor.fetchone()
            if res:
                user = dict(res)
        finally:
            connection.close()
    return user

def create_user(username, password_hash):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
            connection.commit()
            return True
        except Error as e:
            return False
        finally:
            connection.close()
    return False
