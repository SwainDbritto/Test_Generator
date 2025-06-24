from flask import Flask, render_template, request, redirect, session, url_for
import pandas as pd
import hashlib

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # required for sessions

# Load users data
def load_users():
    try:
        return pd.read_csv('data/users.csv')
    except:
        return pd.DataFrame(columns=['user_id', 'username', 'password', 'role'])

# Home Page (Landing Page)
@app.route('/')
def Index():
    return render_template('index.html')

# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

        user = users[(users['username'] == username) & (users['password'] == password)]
        if not user.empty:
            session['username'] = username
            session['role'] = user.iloc[0]['role']
            if session['role'] == 'teacher':
                return redirect('/teacher_dashboard')
            else:
                return redirect('/student_portal')
        else:
            return "Invalid credentials"

    return render_template('login.html')

# Teacher Dashboard
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if 'username' not in session or session['role'] != 'teacher':
        return redirect('/login')
    return render_template('teacher_dashboard.html')

# Student Portal
@app.route('/student_portal')
def student_portal():
    if 'username' not in session or session['role'] != 'student':
        return redirect('/login')
    return render_template('student_portal.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
