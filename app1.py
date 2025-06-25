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
    remaining_category = category_counts.copy()
    remaining_difficulty = difficulty_counts.copy()
    remaining_type = type_counts.copy()

    shuffled_questions = df_questions.to_dict(orient='records')
    random.shuffle(shuffled_questions)

    # --- STEP 1: STRICTLY FILL CATEGORIES FIRST ---
    category_based_selection = []
    for question in shuffled_questions:
        if remaining_category[question['category']] > 0:
            category_based_selection.append(question)
            remaining_category[question['category']] -= 1
            if sum(remaining_category.values()) == 0:
                break  # Stop once all categories are filled

    # --- STEP 2: NOW FILTER FOR DIFFICULTY/TYPE ---
    for question in category_based_selection:
        if (remaining_difficulty[question['difficulty']] > 0 and
            remaining_type[question['type']] > 0):
            
            selected_questions.append(question)
            remaining_difficulty[question['difficulty']] -= 1
            remaining_type[question['type']] -= 1

    # --- STEP 3: IF MISSING QUESTIONS, RELAX DIFFICULTY/TYPE ---
    if len(selected_questions) < total_questions:
        for question in category_based_selection:
            if question not in selected_questions:
                if (remaining_difficulty[question['difficulty']] > 0 or
                    remaining_type[question['type']] > 0):
                    
                    selected_questions.append(question)
                    remaining_difficulty[question['difficulty']] -= 1
                    remaining_type[question['type']] -= 1

    # --- FINAL CHECK ---
    if len(selected_questions) < total_questions:
        print(f"Warning: Only {len(selected_questions)}/{total_questions} selected. Check CSV data.")

    return jsonify(selected_questions)

# --- Run the Flask app ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

