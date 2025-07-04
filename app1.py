from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import pandas as pd
import random
import os
from collections import defaultdict
import secrets

# Configuration
CSV_FILE_PATH = 'questions.csv'
TOTAL_QUESTION_BANK_SIZE = 102  # Added constant for total question bank size
df_questions = pd.DataFrame()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes during development
app.secret_key = secrets.token_hex(16)  # Generate a random secret key for sessions

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
    # Initialize session variables if they don't exist
    if 'used_question_ids' not in session:
        session['used_question_ids'] = []  # Store as list instead of set
    if 'question_bank_exhausted' not in session:
        session['question_bank_exhausted'] = False
    return render_template('index.html')

@app.route('/test.html')
def test():
    return render_template('test.html')

@app.route('/api/generate-test', methods=['POST'])
def generate_test():
    """Generate test with partial fulfillment and proper reset logic"""
    try:
        if df_questions.empty:
            return jsonify({"error": "No questions available"}), 503

        # Initialize session variables if they don't exist
        if 'used_question_ids' not in session:
            session['used_question_ids'] = []
        if 'question_bank_exhausted' not in session:
            session['question_bank_exhausted'] = False

        data = request.get_json()
        
        # Validate input
        required_fields = ['total_questions', 'category_counts', 
                         'difficulty_counts', 'type_counts']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required parameters"}), 400

        total_requested = int(data['total_questions'])
        requested_cats = data['category_counts']
        requested_diffs = data['difficulty_counts']
        requested_types = data['type_counts']
        client_used_ids = set(data.get('used_question_ids', []))
        force_include_ids = set(data.get('force_include_ids', []))  # Wrong answers to retest

        # Convert session list to set for operations
        server_used_ids = set(session['used_question_ids'])
        
        # Combine client and server used IDs
        all_used_ids = server_used_ids.union(client_used_ids)
        
        # Calculate remaining questions
        remaining_questions = TOTAL_QUESTION_BANK_SIZE - len(all_used_ids)
        
        # Check if we need to serve partial batch
        serve_partial_batch = False
        if 0 < remaining_questions < total_requested:
            serve_partial_batch = True
            total_requested = remaining_questions
            print(f"Serving partial batch of {remaining_questions} questions")

        # Verify quota sums match total (only if not serving partial batch)
        if not serve_partial_batch and (
            sum(requested_cats.values()) != total_requested or 
            sum(requested_diffs.values()) != total_requested or
            sum(requested_types.values()) != total_requested
        ):
            return jsonify({"error": "Quota sums must match total questions"}), 400

        # Get available questions (not used yet, plus forced includes)
        available_questions = [
            q for q in df_questions.to_dict('records') 
            if (q['id'] not in all_used_ids) or (q['id'] in force_include_ids)
        ]
        
        # Check if we need to reset due to exhaustion
        reset_question_bank = False
        reset_message = ""
        if len(available_questions) < total_requested:
            reset_question_bank = True
            reset_message = "Question bank exhausted. All questions have been reset."
            available_questions = df_questions.to_dict('records')  # Use all questions
            all_used_ids = set()  # Reset tracking
            session['used_question_ids'] = []
            session['question_bank_exhausted'] = True
        
        # Initialize selection process
        selected = []
        remaining_quotas = {
            'category': requested_cats.copy(),
            'difficulty': requested_diffs.copy(),
            'type': requested_types.copy()
        }
        random.shuffle(available_questions)  # Shuffle available questions

        # Track actual counts and substitutions
        actual_counts = {
            'category': defaultdict(int),
            'difficulty': defaultdict(int),
            'type': defaultdict(int)
        }
        substitutions = {
            'category': defaultdict(list),
            'difficulty': defaultdict(list),
            'type': defaultdict(list)
        }
        
        # First pass: select questions that match all criteria
        for q in available_questions:
            if len(selected) >= total_requested:
                break
                
            # Force include wrong answers
            if q['id'] in force_include_ids and q['id'] not in [s['id'] for s in selected]:
                selected.append(q)
                if q['category'] in remaining_quotas['category']:
                    remaining_quotas['category'][q['category']] -= 1
                    actual_counts['category'][q['category']] += 1
                if q['difficulty'] in remaining_quotas['difficulty']:
                    remaining_quotas['difficulty'][q['difficulty']] -= 1
                    actual_counts['difficulty'][q['difficulty']] += 1
                if q['type'] in remaining_quotas['type']:
                    remaining_quotas['type'][q['type']] -= 1
                    actual_counts['type'][q['type']] += 1
                session['used_question_ids'].append(q['id'])
                continue
                
            # Check if this question matches all remaining quotas
            matches_all = (
                q['category'] in remaining_quotas['category'] and 
                remaining_quotas['category'][q['category']] > 0 and
                q['difficulty'] in remaining_quotas['difficulty'] and 
                remaining_quotas['difficulty'][q['difficulty']] > 0 and
                q['type'] in remaining_quotas['type'] and 
                remaining_quotas['type'][q['type']] > 0
            )
            
            if matches_all:
                selected.append(q)
                remaining_quotas['category'][q['category']] -= 1
                remaining_quotas['difficulty'][q['difficulty']] -= 1
                remaining_quotas['type'][q['type']] -= 1
                actual_counts['category'][q['category']] += 1
                actual_counts['difficulty'][q['difficulty']] += 1
                actual_counts['type'][q['type']] += 1
                session['used_question_ids'].append(q['id'])

        # Special handling for Medium difficulty substitutions
        if remaining_quotas['difficulty'].get('Medium', 0) > 0:
            # Try to fulfill Medium requests with Hard questions first
            for q in available_questions:
                if len(selected) >= total_requested:
                    break
                if q['id'] in [s['id'] for s in selected]:
                    continue
                    
                if (q['difficulty'] == 'Hard' and 
                    remaining_quotas['difficulty'].get('Medium', 0) > 0 and
                    q['category'] in remaining_quotas['category'] and 
                    remaining_quotas['category'][q['category']] > 0 and
                    q['type'] in remaining_quotas['type'] and 
                    remaining_quotas['type'][q['type']] > 0):
                    
                    selected.append(q)
                    remaining_quotas['difficulty']['Medium'] -= 1
                    actual_counts['difficulty']['Hard'] += 1
                    substitutions['difficulty']['Medium'].append('Hard')
                    # Update other quotas
                    remaining_quotas['category'][q['category']] -= 1
                    remaining_quotas['type'][q['type']] -= 1
                    actual_counts['category'][q['category']] += 1
                    actual_counts['type'][q['type']] += 1
                    session['used_question_ids'].append(q['id'])

        # Second pass: fill remaining with questions that match any criteria
        if len(selected) < total_requested:
            for q in available_questions:
                if len(selected) >= total_requested:
                    break
                if q['id'] in [s['id'] for s in selected]:
                    continue
                    
                matches_any = (
                    (q['category'] in remaining_quotas['category'] and remaining_quotas['category'][q['category']] > 0) or
                    (q['difficulty'] in remaining_quotas['difficulty'] and remaining_quotas['difficulty'][q['difficulty']] > 0) or
                    (q['type'] in remaining_quotas['type'] and remaining_quotas['type'][q['type']] > 0)
                )
                
                if matches_any:
                    selected.append(q)
                    # Track what we're substituting
                    original_target = None
                    if q['difficulty'] != 'Medium' and remaining_quotas['difficulty'].get('Medium', 0) > 0:
                        original_target = 'Medium'
                        remaining_quotas['difficulty']['Medium'] -= 1
                        substitutions['difficulty']['Medium'].append(q['difficulty'])
                    elif q['difficulty'] in remaining_quotas['difficulty'] and remaining_quotas['difficulty'][q['difficulty']] > 0:
                        remaining_quotas['difficulty'][q['difficulty']] -= 1
                    else:
                        original_target = None
                    
                    # Update counts
                    actual_counts['difficulty'][q['difficulty']] += 1
                    if q['category'] in remaining_quotas['category'] and remaining_quotas['category'][q['category']] > 0:
                        remaining_quotas['category'][q['category']] -= 1
                        actual_counts['category'][q['category']] += 1
                    if q['type'] in remaining_quotas['type'] and remaining_quotas['type'][q['type']] > 0:
                        remaining_quotas['type'][q['type']] -= 1
                        actual_counts['type'][q['type']] += 1
                    session['used_question_ids'].append(q['id'])

        # Mark session as modified since we're updating it
        session.modified = True

        # Generate deviation messages
        messages = []
        adjustments = []
        
        if serve_partial_batch:
            msg = f"Only {remaining_questions} questions available in this batch."
            messages.append(msg)
            adjustments.append(msg)
        
        if reset_question_bank:
            messages.append(reset_message)
            adjustments.append(reset_message)
        
        # Category deviations
        for cat, req_count in requested_cats.items():
            act_count = actual_counts['category'].get(cat, 0)
            if act_count != req_count:
                if act_count < req_count:
                    provided_instead = None
                    for c, cnt in actual_counts['category'].items():
                        if cnt > 0 and c != cat:
                            provided_instead = c
                            break
                    
                    if provided_instead:
                        msg = (f"Could only provide {act_count} out of {req_count} "
                              f"{cat} category questions (provided {provided_instead} instead)")
                    else:
                        msg = (f"Could only provide {act_count} out of {req_count} "
                              f"{cat} category questions")
                    messages.append(msg)
                    adjustments.append(msg)
        
        # Difficulty deviations - with accurate substitution reporting
        for diff, req_count in requested_diffs.items():
            act_count = actual_counts['difficulty'].get(diff, 0)
            if act_count != req_count:
                if act_count < req_count:
                    # Check if we have substitution records
                    if diff in substitutions['difficulty']:
                        # Get the most common substitution
                        if substitutions['difficulty'][diff]:
                            sub_counts = {}
                            for sub in substitutions['difficulty'][diff]:
                                sub_counts[sub] = sub_counts.get(sub, 0) + 1
                            most_common_sub = max(sub_counts.items(), key=lambda x: x[1])[0]
                            msg = (f"Could only provide {act_count} out of {req_count} "
                                  f"{diff} difficulty questions (provided {most_common_sub} instead)")
                        else:
                            msg = (f"Could only provide {act_count} out of {req_count} "
                                  f"{diff} difficulty questions")
                    else:
                        # Fallback to checking actual counts
                        provided_instead = None
                        if diff == 'Medium':
                            if actual_counts['difficulty'].get('Hard', 0) > 0:
                                provided_instead = 'Hard'
                            elif actual_counts['difficulty'].get('Easy', 0) > 0:
                                provided_instead = 'Easy'
                        else:
                            for d, cnt in actual_counts['difficulty'].items():
                                if cnt > 0 and d != diff:
                                    provided_instead = d
                                    break
                        
                        if provided_instead:
                            msg = (f"Could only provide {act_count} out of {req_count} "
                                  f"{diff} difficulty questions (provided {provided_instead} instead)")
                        else:
                            msg = (f"Could only provide {act_count} out of {req_count} "
                                  f"{diff} difficulty questions")
                    messages.append(msg)
                    adjustments.append(msg)
        
        # Type deviations
        for q_type, req_count in requested_types.items():
            act_count = actual_counts['type'].get(q_type, 0)
            if act_count != req_count:
                if act_count < req_count:
                    provided_instead = None
                    for t, cnt in actual_counts['type'].items():
                        if cnt > 0 and t != q_type:
                            provided_instead = t
                            break
                    
                    if provided_instead:
                        msg = (f"Could only provide {act_count} out of {req_count} "
                              f"{q_type} type questions (provided {provided_instead} instead)")
                    else:
                        msg = (f"Could only provide {act_count} out of {req_count} "
                              f"{q_type} type questions")
                    messages.append(msg)
                    adjustments.append(msg)

        # Prepare response
        response = {
            'test': [{
                'id': q['id'],
                'question': q['question'],
                'category': q['category'],
                'difficulty': q['difficulty'],
                'type': q['type'],
                'is_fallback': reset_question_bank,
                'was_substituted': any(
                    (q['difficulty'] in substitutions['difficulty'].get('Medium', []) and requested_diffs.get('Medium', 0) > 0) or
                    (q['difficulty'] in substitutions['difficulty'].get('Hard', []) and requested_diffs.get('Hard', 0) > 0)
                    for q in selected
                )
            } for q in selected],
            'messages': messages,
            'adjustments': adjustments,
            'reset_question_bank': reset_question_bank,
            'reset_message': reset_message if reset_question_bank else None,
            'partial_batch': serve_partial_batch,
            'substitutions': substitutions
        }

        return jsonify(response)

    except Exception as e:
        print(f"Error generating test: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)