import mysql.connector
from mysql.connector import Error
import os

# DB 연결 함수
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'vocab_db'),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', 'Inha1958')
        )
        return connection
    except Error as e:
        print(f"DB 연결 오류: {e}")
        return None

# 단어 추가 함수
def add_word(user_id, word, meaning, synonyms):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            # SQL Injection 방지를 위해 파라미터화된 쿼리 사용
            query = "INSERT INTO words (user_id, word, meaning, synonyms) VALUES (%s, %s, %s, %s)"
            values = (user_id, word, meaning, synonyms)
            
            cursor.execute(query, values)
            connection.commit()
            print(f"✅ DB에 '{word}' 추가 완료!")
        except Error as e:
            print(f"데이터 삽입 오류: {e}")
        finally:
            cursor.close()
            connection.close()

# 여러 단어 한 번에 추가하는 함수
def add_multiple_words(word_data_list):
    connection = get_db_connection()
    if connection and word_data_list:
        try:
            cursor = connection.cursor()
            query = "INSERT INTO words (word, meaning, synonyms, day, user_id) VALUES (%s, %s, %s, %s, %s)"
            
            cursor.executemany(query, word_data_list)
            connection.commit()
            print(f"✅ DB에 {cursor.rowcount}개의 단어 추가 완료!")
        except Error as e:
            print(f"데이터 대량 삽입 오류: {e}")
            connection.rollback() # 오류 발생 시 롤백
        finally:
            cursor.close()
            connection.close()

# 랜덤 시험지 생성 함수
def generate_test(user_id, num_questions=None, day=None, start_day=None, end_day=None):
    connection = get_db_connection()
    test_paper = []
    
    if connection:
        try:
            # dictionary=True를 주면 결과가 딕셔너리 형태로 반환되어 다루기 편합니다.
            cursor = connection.cursor(dictionary=True)
            if day is not None:
                # 데일리 테스트: 특정 Day의 모든 단어 (무작위 정렬)
                query = "SELECT id, word, meaning, synonyms FROM words WHERE user_id = %s AND day = %s ORDER BY RAND()"
                cursor.execute(query, (user_id, day))
            elif start_day is not None and end_day is not None:
                # 모의고사 (범위 지정): 특정 Day 범위의 단어 중 무작위
                query = "SELECT id, word, meaning, synonyms FROM words WHERE user_id = %s AND day BETWEEN %s AND %s ORDER BY RAND()"
                cursor.execute(query, (user_id, start_day, end_day))
            else:
                # 모의고사: 중복 필터링을 위해 전체를 무작위로 가져옴
                query = "SELECT id, word, meaning, synonyms FROM words WHERE user_id = %s ORDER BY RAND()"
                cursor.execute(query, (user_id,))
                
            results = cursor.fetchall()
            
            # 한 시험지에 같은 영어 단어가 중복 출제되지 않도록 필터링
            seen_words = set()
            for row in results:
                word_lower = row['word'].lower()
                if word_lower not in seen_words:
                    seen_words.add(word_lower)
                    test_paper.append(row)
                    
                    # 모의고사의 경우 목표 문제 수를 채우면 중단
                    if day is None and num_questions is not None and len(test_paper) >= int(num_questions):
                        break
        except Error as e:
            print(f"데이터 조회 오류: {e}")
        finally:
            cursor.close()
            connection.close()
            
    return test_paper

# 등록된 Day 목록 가져오는 함수
def get_available_days(user_id):
    connection = get_db_connection()
    days = []
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT DISTINCT day FROM words WHERE user_id = %s AND day IS NOT NULL ORDER BY day", (user_id,))
            days = [row['day'] for row in cursor.fetchall()]
        except Error as e:
            print(f"일차 조회 오류: {e}")
        finally:
            cursor.close()
            connection.close()
    return days

# 단어 ID 리스트로 정답 정보 가져오는 함수
def get_words_by_ids(user_id, id_list):
    connection = get_db_connection()
    words_data = {}
    if connection and id_list:
        try:
            cursor = connection.cursor(dictionary=True)
            # IN 절을 사용하여 여러 단어(ID)를 한 번에 조회
            format_strings = ','.join(['%s'] * len(id_list))
            query = f"SELECT id, word, meaning, synonyms FROM words WHERE user_id = %s AND id IN ({format_strings})"
            
            cursor.execute(query, (user_id,) + tuple(id_list))
            results = cursor.fetchall()
            # 단어 ID를 key로 하는 딕셔너리로 변환하여 사용하기 쉽게 만듦
            for row in results:
                words_data[str(row['id'])] = row
        except Error as e:
            print(f"데이터 조회 오류: {e}")
        finally:
            cursor.close()
            connection.close()
    return words_data

# 전체 단어 목록 가져오는 함수 (페이지네이션 적용)
def get_all_words(user_id, day=None, page=1, per_page=50):
    connection = get_db_connection()
    words = []
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            offset = (page - 1) * per_page
            if day:
                # LIMIT와 OFFSET을 이용해 지정된 개수만큼만 가져옵니다
                cursor.execute("SELECT id, day, word, meaning, synonyms FROM words WHERE user_id = %s AND day = %s ORDER BY day ASC, word ASC LIMIT %s OFFSET %s", (user_id, day, per_page, offset))
            else:
                cursor.execute("SELECT id, day, word, meaning, synonyms FROM words WHERE user_id = %s ORDER BY day ASC, word ASC LIMIT %s OFFSET %s", (user_id, per_page, offset))
            words = cursor.fetchall()
        except Error as e:
            print(f"전체 단어 조회 오류: {e}")
        finally:
            cursor.close()
            connection.close()
    return words

# 전체 단어 개수를 세는 함수 (페이지 수 계산용)
def get_total_words_count(user_id, day=None):
    connection = get_db_connection()
    count = 0
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            if day:
                cursor.execute("SELECT COUNT(*) as cnt FROM words WHERE user_id = %s AND day = %s", (user_id, day))
            else:
                cursor.execute("SELECT COUNT(*) as cnt FROM words WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            count = result['cnt'] if result else 0
        except Error as e:
            print(f"단어 개수 조회 오류: {e}")
        finally:
            cursor.close()
            connection.close()
    return count

# 특정 단어 1개 정보만 가져오는 함수 (수정용)
def get_word_by_id(user_id, word_id):
    connection = get_db_connection()
    word = None
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, day, word, meaning, synonyms FROM words WHERE user_id = %s AND id = %s", (user_id, word_id))
            word = cursor.fetchone()
        finally:
            cursor.close()
            connection.close()
    return word

# 특정 단어 수정 함수
def update_word(user_id, word_id, day, word, meaning, synonyms):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("UPDATE words SET day=%s, word=%s, meaning=%s, synonyms=%s WHERE user_id=%s AND id=%s",
                           (day, word, meaning, synonyms, user_id, word_id))
            connection.commit()
            print(f"✅ DB에 '{word}' 수정 완료!")
        finally:
            cursor.close()
            connection.close()

# 특정 단어 삭제 함수
def delete_word(user_id, word_id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM words WHERE user_id = %s AND id = %s", (user_id, word_id))
            connection.commit()
        finally:
            cursor.close()
            connection.close()

# --- 회원가입 / 로그인 관련 함수 ---
def get_user_by_username(username):
    connection = get_db_connection()
    user = None
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
        finally:
            cursor.close()
            connection.close()
    return user

def create_user(username, password_hash):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
            connection.commit()
            return True
        except Error as e:
            print(f"회원가입 오류: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False
