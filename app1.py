from flask import Flask, request, jsonify, render_template
from flask_cors import CORS # Ensure this is imported
import pandas as pd
import random
import os

app = Flask(__name__)
# app.secret_key = 'your_secret_key' # Uncomment and set if you use sessions

# --- Configuration ---
CSV_FILE_PATH = 'questions.csv'
df_questions = pd.DataFrame()

# --- IMPORTANT CORS FIX ---
# Explicitly allow both localhost and 127.0.0.1 on port 5000
# for all routes under '/api/'.
# If you are running your frontend via something like Python's http.server on port 8000,
# you would add 'http://127.0.0.1:8000' or 'http://localhost:8000' here as well.
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5000", "http://localhost:5000"]}})

# --- Data Loading Function ---
def load_questions_from_csv():
    global df_questions
    if not os.path.exists(CSV_FILE_PATH):
        print(f"Error: CSV file not found at {CSV_FILE_PATH}. Please ensure it's in the correct directory.")
        return False
    try:
        df_questions = pd.read_csv(CSV_FILE_PATH)
        df_questions['category'] = df_questions['category'].astype(str)
        df_questions['difficulty'] = df_questions['difficulty'].astype(str)
        df_questions['type'] = df_questions['type'].astype(str)
        print(f"Successfully loaded {len(df_questions)} questions from {CSV_FILE_PATH}")
        return True
    except Exception as e:
        print(f"An error occurred while loading the CSV: {e}")
        df_questions = pd.DataFrame()
        return False

if not load_questions_from_csv():
    print("Application started with no questions loaded. Please fix CSV path/errors.")

# --- Existing Frontend Serving Routes ---
@app.route('/')
def Index():
    return render_template('index.html')

@app.route('/test.html')
def test():
    return render_template('test.html')

# --- Backend API Endpoint for Test Generation ---
@app.route('/api/generate-test', methods=['POST'])
def generate_test():
    if df_questions.empty:
        return jsonify({"message": "Backend has no questions loaded. Check server logs."}), 500

    data = request.get_json()

    total_questions = data.get('total_questions')
    category_counts = data.get('category_counts', {})
    difficulty_counts = data.get('difficulty_counts', {})
    type_counts = data.get('type_counts', {})

    if not all([total_questions is not None, category_counts, difficulty_counts, type_counts]):
        return jsonify({"message": "Missing one or more required parameters (total_questions, category_counts, difficulty_counts, type_counts)."}), 400

    if sum(category_counts.values()) != total_questions or \
       sum(difficulty_counts.values()) != total_questions or \
       sum(type_counts.values()) != total_questions:
        return jsonify({"message": "Sum of counts for categories, difficulties, or types does not match total_questions."}), 400

    selected_questions = []
    remaining_questions = []
    available_pool = df_questions.to_dict(orient='records')
    random.shuffle(available_pool)

    current_category_selected = {cat: 0 for cat in category_counts}
    current_difficulty_selected = {diff: 0 for diff in difficulty_counts}
    current_type_selected = {q_type: 0 for q_type in type_counts}

    for question in available_pool:
        if len(selected_questions) >= total_questions:
            break

        q_id = question['id']
        q_category = question['category']
        q_difficulty = question['difficulty']
        q_type = question['type']

        if q_category not in category_counts or \
           q_difficulty not in difficulty_counts or \
           q_type not in type_counts:
           continue

        can_add = True
        can_add_diff = True
        can_add_type = True
        
        if current_category_selected[q_category] >= category_counts[q_category]:
            can_add = False
        if current_difficulty_selected[q_difficulty] >= difficulty_counts[q_difficulty]:
            can_add_diff = False
        if current_type_selected[q_type] >= type_counts[q_type]:
            can_add_type = False
        
        if can_add or can_add_diff or can_add_type:
            selected_questions.append(question)
            current_category_selected[q_category] += 1
            current_difficulty_selected[q_difficulty] += 1
            current_type_selected[q_type] += 1
    
    if len(selected_questions) < total_questions:
        print(current_category_selected[q_category])

    return jsonify(selected_questions)

# --- Run the Flask app ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

