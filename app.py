from flask import Flask, render_template, request, redirect, url_for, session, flash
from vocab_db import generate_test, get_words_by_ids, get_all_accepted_answers_for_words, add_multiple_words, get_available_days, get_all_words, delete_word, get_total_words_count, get_word_by_id, update_word, get_user_by_username, create_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import random
import math
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_key_for_session_management') # 로그인 세션 관리를 위한 비밀키

# --- 로그인 확인 데코레이터 ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 인증(회원가입/로그인) 라우트 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user_by_username(username)

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('home'))
        else:
            flash('아이디 또는 비밀번호가 올바르지 않습니다.')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if get_user_by_username(username):
            flash('이미 존재하는 아이디입니다.')
        else:
            hashed_pw = generate_password_hash(password)
            if create_user(username, hashed_pw):
                flash('회원가입 완료! 로그인해주세요.')
                return redirect(url_for('login'))
            else:
                flash('회원가입 중 오류가 발생했습니다.')
                
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    days = get_available_days(session['user_id'])
    return render_template('index.html', days=days)

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    test_type = request.form.get('test_type')
    question_type = request.form.get('question_type', 'en_to_ko')
    
    if test_type == 'daily':
        day = request.form.get('day')
        questions = generate_test(session['user_id'], day=day)
    elif test_type == 'mock':
        num_questions = request.form.get('num_questions', 20)
        range_type = request.form.get('range_type', 'all')
        
        if range_type == 'range':
            start_day = int(request.form.get('start_day', 1))
            end_day = int(request.form.get('end_day', 1))
            if start_day > end_day:
                start_day, end_day = end_day, start_day # 사용자가 시작과 끝을 반대로 선택했을 경우 자동 교정
            questions = generate_test(session['user_id'], num_questions=num_questions, start_day=start_day, end_day=end_day)
        else:
            questions = generate_test(session['user_id'], num_questions=num_questions)
        
    # 뜻이 여러 개일 경우, 그 중 하나만 랜덤으로 출제하도록 처리
    for q in questions:
        meanings = [m.strip() for m in q['meaning'].split(',') if m.strip()]
        q['random_meaning'] = random.choice(meanings) if meanings else q['meaning']

        # 랜덤 혼합 출제일 경우 개별 문제마다 타입을 랜덤으로 지정
        if question_type == 'random':
            q['q_type'] = random.choice(['en_to_ko', 'ko_to_en'])
        else:
            q['q_type'] = question_type

    return render_template('test.html', questions=questions, title='📝 영단어 랜덤 시험지', question_type=question_type)

@app.route('/submit', methods=['POST'])
@login_required
def submit_test():
    # 1. 사용자가 제출한 폼 데이터 가져오기
    user_answers = request.form
    question_type = request.form.get('question_type', 'en_to_ko')

    # 2. 폼 데이터에서 문제 단어 목록과 문제 개수 추출
    num_questions = 0
    ids_on_test = []
    words_on_test = []
    for key in user_answers:
        if key.startswith('word_id_'):
            num_questions += 1
            idx = key.replace('word_id_', '')
            ids_on_test.append(user_answers[key])
            word_text = user_answers.get(f'word_text_{idx}', '').strip()
            if word_text: words_on_test.append(word_text)

    # 3. DB에서 정답 데이터 가져오기
    correct_answers = get_words_by_ids(session['user_id'], ids_on_test)
    all_accepted_answers = get_all_accepted_answers_for_words(session['user_id'], words_on_test)

    # 4. 채점 시작
    results = []
    score = 0
    for i in range(1, num_questions + 1):
        word_id = user_answers[f'word_id_{i}']
        word_text = user_answers[f'word_text_{i}']
        user_synonyms_str = user_answers.get(f'synonyms_{i}', '').strip()

        correct_data = correct_answers.get(word_id)
        if not correct_data: continue

        # 개별 문제의 출제 타입 가져오기 (랜덤 모드 지원)
        current_q_type = user_answers.get(f'q_type_{i}', question_type)
        if current_q_type == 'random': # 프론트에서 타입이 누락되었을 경우를 대비한 2차 안전 장치
            current_q_type = 'ko_to_en' if f'word_ans_{i}' in user_answers else 'en_to_ko'

        word_text_lower = word_text.lower()
        accepted_data = all_accepted_answers.get(word_text_lower, {'meanings': set(), 'original_meanings': set(), 'synonyms': set()})

        # 유사어 채점 (대소문자 무시, 입력한 것 중 하나라도 정답에 포함되면 정답)
        user_synonyms_list = {s.strip().lower() for s in user_synonyms_str.split(',') if s.strip()}
        correct_synonyms_str = correct_data.get('synonyms', '')
        
        # DB에 등록된 동일한 철자 단어들의 유사어까지 모두 인정
        correct_synonyms_list = accepted_data.get('synonyms', set())

        # DB에 등록된 유사어가 아예 없을 때는 억울하게 틀리지 않도록 통과 처리
        if not correct_synonyms_str.strip():
            is_synonyms_correct = True
        else:
            is_synonyms_correct = len(user_synonyms_list & correct_synonyms_list) > 0

        # 출제 방식에 따른 메인 정답 채점
        if current_q_type == 'ko_to_en':
            user_ans = user_answers.get(f'word_ans_{i}', '').strip()
            correct_ans_str = correct_data['word']
            is_correct = (user_ans.lower() == correct_data['word'].strip().lower()) # DB에 들어간 공백 방지
            question_display = user_answers.get(f'asked_meaning_{i}', correct_data['meaning'])
        else:
            user_ans = user_answers.get(f'meaning_{i}', '').strip()
            
            # 해당 단어에 등록된 모든 뜻을 합쳐서 정답란에 보여줌
            if accepted_data.get('original_meanings'):
                correct_ans_str = ', '.join(sorted(accepted_data['original_meanings']))
            else:
                correct_ans_str = correct_data['meaning']
                
            # 사용자가 쉼표(,)로 여러 뜻을 입력했을 경우 쪼개서 검사 (하나라도 맞으면 정답)
            user_ans_list = {m.strip().lower() for m in user_ans.split(',') if m.strip()}
            correct_meanings_list = accepted_data.get('meanings', set())
            is_correct = len(user_ans_list & correct_meanings_list) > 0
            question_display = correct_data['word']

        if is_correct:
            score += 1
            is_synonyms_correct = True # 메인 정답(뜻/영어)이 맞으면 화면에서 틀렸다고 나오지 않게 강제로 True 처리

        results.append({
            'id': word_id,
            'word': word_text,
            'question_display': question_display, # 문제로 보여준 텍스트
            'user_answer': user_ans,
            'correct_answer': correct_ans_str,
            'is_correct': is_correct,
            'user_synonyms': user_synonyms_str,
            'correct_synonyms': correct_data.get('synonyms', ''),
            'is_synonyms_correct': is_synonyms_correct,
        })

    # 5. 결과 페이지 렌더링
    return render_template('result.html', results=results, score=score, total=num_questions, question_type=question_type)

# --- 틀린 문제 다시 풀기 ---
@app.route('/retake_test', methods=['POST'])
@login_required
def retake_test():
    # 1. 틀린 단어 목록을 폼에서 가져오기
    ids_to_retake = request.form.getlist('ids_to_retake')
    question_type = request.form.get('question_type', 'en_to_ko')

    if not ids_to_retake:
        # 혹시 모를 예외 처리: 틀린 단어가 없으면 홈으로 이동
        return redirect(url_for('home'))

    # 2. DB에서 해당 단어들의 정보 가져오기
    correct_answers_dict = get_words_by_ids(session['user_id'], ids_to_retake)
    
    # 순서를 유지하면서 리스트로 변환
    questions = []
    for wid in ids_to_retake:
        if wid in correct_answers_dict:
            q = correct_answers_dict[wid]
            meanings = [m.strip() for m in q['meaning'].split(',') if m.strip()]
            q['random_meaning'] = random.choice(meanings) if meanings else q['meaning']
            
            if question_type == 'random':
                q['q_type'] = random.choice(['en_to_ko', 'ko_to_en'])
            else:
                q['q_type'] = question_type
                
            questions.append(q)

    # 3. test.html 템플릿을 다시 사용하여 오답노트 시험지 렌더링
    return render_template('test.html', questions=questions, title='📝 틀린 문제 다시 풀기', question_type=question_type)

# --- 단어장 관리 (단어 추가) 화면 보여주기 ---
@app.route('/admin')
@login_required
def admin_page():
    return render_template('admin.html')

# --- 단어장 관리 (여러 단어 DB 저장) 기능 ---
@app.route('/add_words', methods=['POST'])
@login_required
def handle_add_words():
    try:
        day = int(request.form.get('day', 1)) # Day를 확실하게 숫자로 변환
    except ValueError:
        day = 1
        
    words = request.form.getlist('word')
    meanings = request.form.getlist('meaning')
    synonyms_list = request.form.getlist('synonyms')

    print(f"\n[디버깅] 폼에서 받은 영어단어들: {words}") # 서버 터미널에 확인용 출력

    words_to_add = []
    # zip을 사용하여 각 행의 데이터를 튜플로 묶습니다.
    for word, meaning, synonyms in zip(words, meanings, synonyms_list):
        # 단어와 뜻이 모두 입력된 행만 유효한 데이터로 간주합니다.
        if word.strip() and meaning.strip():
            words_to_add.append((word.strip(), meaning.strip(), synonyms.strip(), day, session['user_id']))
    
    if words_to_add:
        print(f"[디버깅] DB에 저장 시도할 완성된 데이터: {words_to_add}\n") # 서버 터미널에 확인용 출력
        add_multiple_words(words_to_add) # 새로운 DB 함수 호출
        
    return redirect(url_for('admin_page')) # 저장 후 다시 입력창 보여주기

# --- 전체 단어장 목록 보기 ---
@app.route('/voca_list')
@login_required
def voca_list():
    day_filter = request.args.get('day')
    page = request.args.get('page', 1, type=int) # 현재 페이지 번호
    per_page = 50 # 한 페이지에 보여줄 단어 수

    if day_filter and day_filter.isdigit():
        day_filter = int(day_filter)
    else:
        day_filter = None
        
    # 전체 데이터 개수 및 페이지 수 계산
    total_count = get_total_words_count(session['user_id'], day=day_filter)
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    
    # 페이지 번호가 범위를 벗어나지 않게 조정
    if page > total_pages: page = total_pages
    if page < 1: page = 1

    words = get_all_words(session['user_id'], day=day_filter, page=page, per_page=per_page)
    days = get_available_days(session['user_id'])

    # 화면 병합(rowspan)을 위한 계산 로직
    for i in range(len(words)):
        words[i]['show_word'] = True
        words[i]['rowspan'] = 1

    # 뒤에서부터 앞으로 비교하며 같은 단어일 경우 칸을 합칩니다.
    for i in range(len(words) - 2, -1, -1):
        if words[i]['day'] == words[i+1]['day'] and words[i]['word'].lower() == words[i+1]['word'].lower():
            words[i]['rowspan'] = words[i+1]['rowspan'] + 1
            words[i+1]['show_word'] = False

    return render_template('list.html', words=words, days=days, selected_day=day_filter, page=page, total_pages=total_pages, total_count=total_count)

# --- 단어 수정 기능 ---
@app.route('/edit_word/<int:word_id>')
@login_required
def edit_word(word_id):
    word = get_word_by_id(session['user_id'], word_id)
    if not word:
        return redirect(url_for('voca_list'))
    return render_template('edit.html', word=word)

@app.route('/update_word/<int:word_id>', methods=['POST'])
@login_required
def handle_update_word(word_id):
    day = request.form.get('day', 1, type=int)
    word_text = request.form.get('word', '').strip()
    meaning = request.form.get('meaning', '').strip()
    synonyms = request.form.get('synonyms', '').strip()

    if word_text and meaning:
        update_word(session['user_id'], word_id, day, word_text, meaning, synonyms)
        
    return redirect(url_for('voca_list'))

# --- 단어 삭제 기능 ---
@app.route('/delete_word/<int:word_id>', methods=['POST'])
@login_required
def handle_delete_word(word_id):
    delete_word(session['user_id'], word_id)
    return redirect(url_for('voca_list'))

if __name__ == '__main__':
    # debug=True는 개발 중에 코드가 변경되면 서버가 자동으로 재시작되게 해줍니다.
    app.run(debug=True)