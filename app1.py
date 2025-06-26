from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import pandas as pd
import random
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes during development

# Configuration
CSV_FILE_PATH = 'questions.csv'
df_questions = pd.DataFrame()

def load_questions_from_csv():
    """Load questions from CSV with robust error handling"""
    global df_questions
    try:
        if not os.path.exists(CSV_FILE_PATH):
            raise FileNotFoundError(f"CSV file not found at {CSV_FILE_PATH}")
        
        df = pd.read_csv(CSV_FILE_PATH)
        
        # Validate required columns
        required_columns = ['id', 'question', 'category', 'difficulty', 'type']
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            raise ValueError(f"Missing required columns: {missing}")
        
        # Clean and standardize data
        df['category'] = df['category'].astype(str).str.upper().str.strip()
        df['difficulty'] = df['difficulty'].astype(str).str.capitalize().str.strip()
        df['type'] = df['type'].astype(str).str.strip()
        
        # Validate values
        valid_difficulties = ['Easy', 'Medium', 'Hard']
        invalid_diffs = df[~df['difficulty'].isin(valid_difficulties)]
        if not invalid_diffs.empty:
            raise ValueError(f"Invalid difficulty values: {invalid_diffs['difficulty'].unique()}")
        
        df_questions = df
        print(f"Successfully loaded {len(df)} questions")
        return True
        
    except Exception as e:
        print(f"Error loading CSV: {str(e)}")
        df_questions = pd.DataFrame(columns=required_columns)
        return False

# Load questions when starting
if not load_questions_from_csv():
    print("Warning: Starting with empty question bank")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test.html')
def test():
    return render_template('test.html')

@app.route('/api/generate-test', methods=['POST'])
def generate_test():
    """Generate test with proper quota enforcement"""
    try:
        if df_questions.empty:
            return jsonify({"error": "No questions available"}), 503

        data = request.get_json()
        
        # Validate input
        required_fields = ['total_questions', 'category_counts', 
                         'difficulty_counts', 'type_counts']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required parameters"}), 400

        total = data['total_questions']
        cat_counts = data['category_counts']
        diff_counts = data['difficulty_counts']
        type_counts = data['type_counts']

        # Verify quota sums match total
        if (sum(cat_counts.values()) != total or 
            sum(diff_counts.values()) != total or
            sum(type_counts.values()) != total):
            return jsonify({"error": "Quota sums must match total questions"}), 400

        # Initialize selection process
        selected = []
        remaining = {
            'category': cat_counts.copy(),
            'difficulty': diff_counts.copy(),
            'type': type_counts.copy()
        }
        pool = df_questions.to_dict('records')
        random.shuffle(pool)

        # Priority-based selection strategy
        for priority_level in [3, 2, 1]:
            for q in pool:
                if q in selected:
                    continue
                    
                # Check remaining quotas
                fits_category = remaining['category'][q['category']] > 0
                fits_diff = remaining['difficulty'][q['difficulty']] > 0
                fits_type = remaining['type'][q['type']] > 0
                
                # Priority level checks
                if priority_level == 3:  # All three must match
                    if not (fits_category and fits_diff and fits_type):
                        continue
                elif priority_level == 2:  # Any two must match
                    if not ((fits_category and fits_diff) or 
                           (fits_category and fits_type) or 
                           (fits_diff and fits_type)):
                        continue
                else:  # priority_level == 1 - Any one must match
                    if not (fits_category or fits_diff or fits_type):
                        continue
                
                # Add question and decrement quotas
                selected.append(q)
                if fits_category:
                    remaining['category'][q['category']] -= 1
                if fits_diff:
                    remaining['difficulty'][q['difficulty']] -= 1
                if fits_type:
                    remaining['type'][q['type']] -= 1
                
                if len(selected) >= total:
                    break
                    
            if len(selected) >= total:
                break        # Prepare response with standardized data
        response = [{
            'id': q['id'],
            'question': q['question'],
            'category': q['category'],
            'difficulty': q['difficulty'],
            'type': q['type']
        } for q in selected]

        return jsonify(response)

    except Exception as e:
        print(f"Error generating test: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
