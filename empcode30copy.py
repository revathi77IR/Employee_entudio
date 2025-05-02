import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime
import time
import os
import cv2
import face_recognition
import numpy as np
from PIL import Image
import io
import base64
import random
import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
from io import BytesIO
from PIL import Image
import base64

# Initialize session state for user editing
if 'show_edit_form' not in st.session_state:
    st.session_state.show_edit_form = False
if 'editing_user_id' not in st.session_state:
    st.session_state.editing_user_id = None


from datetime import datetime, timedelta ,date
import pickle
import os
# Add these new imports at the top
import mediapipe as mp
import math
# Initialize Mediapipe FaceMesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Fixed Sales Login Credentials
SALES_USERNAME = "sales"
SALES_PASSWORD = "sales123" 

# Add this at the top with other imports
FACE_ENCODINGS_DIR = "face_encodings"

# Create directory if not exists
if not os.path.exists(FACE_ENCODINGS_DIR):
    os.makedirs(FACE_ENCODINGS_DIR)

# Initialize session states if they don't exist
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'face_encodings_db' not in st.session_state:
    st.session_state.face_encodings_db = {}
if 'is_sales_login' not in st.session_state:
        st.session_state.is_sales_login = False



# Database setup

def init_db():
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    # Create users table
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        department TEXT NOT NULL,
        join_date TEXT,
        face_encoding BLOB
    )
    ''')

    # Create projects table
    c.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        link TEXT,
        members TEXT,
        deadline TEXT,
        total_hours REAL,
        status TEXT
    )
    ''')

    # Add photo column if not exists
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    if 'photo' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN photo BLOB")

    # Create attendance table
    c.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        check_in TEXT,
        check_out TEXT,
        work_hours REAL,
        status TEXT,
        verification_method TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Create daily reports table
    c.execute('''
    CREATE TABLE IF NOT EXISTS daily_reports (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        project TEXT,
        activities TEXT,
        achievements TEXT,
        challenges TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Create salary table
    c.execute('''
    CREATE TABLE IF NOT EXISTS salary (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        year INTEGER NOT NULL,
        base_salary REAL NOT NULL,
        bonus REAL DEFAULT 0,
        deductions REAL DEFAULT 0,
        total_salary REAL NOT NULL,
        payment_status TEXT DEFAULT 'Pending',
        payment_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    # Create leave_requests table
    c.execute('''
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        leave_type TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT DEFAULT 'Pending',
        admin_approval TEXT,
        employee_verification TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Create an admin if no admin
    c.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if c.fetchone()[0] == 0:
        admin_password = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute(
            "INSERT INTO users (username, password, role, name, email, department, join_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("admin", admin_password, "admin", "Administrator", "admin@company.com", "Management",
             datetime.now().strftime("%Y-%m-%d")))

    conn.commit()
    conn.close()
# Add custom CSS and JS
def inject_custom_files():
    with open("assets/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
        
    with open("assets/script.js") as f:
        st.markdown(f"<script>{f.read()}</script>", unsafe_allow_html=True)

# Call the function at the start of your main()
inject_custom_files()

# User authentication
def authenticate(username, password):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT id, role, name FROM users WHERE username = ? AND password = ?", (username, hashed_password))
    result = c.fetchone()

    conn.close()

    if result:
        return {'id': result[0], 'role': result[1], 'name': result[2]}
    return None


def load_face_encodings():
    """Load all face encodings from pickle files"""
    face_encodings = {}
    try:
        for file_name in os.listdir(FACE_ENCODINGS_DIR):
            if file_name.endswith(".pkl"):
                user_id = int(file_name.split("_")[1].split(".")[0])
                with open(os.path.join(FACE_ENCODINGS_DIR, file_name), 'rb') as f:
                    face_encodings[user_id] = pickle.load(f)
    except Exception as e:
        st.error(f"Error loading face encodings: {e}")
    return face_encodings


def save_face_encoding(user_id, face_encoding):
    """Save face encoding to a pickle file"""
    try:
        file_path = os.path.join(FACE_ENCODINGS_DIR, f"user_{user_id}.pkl")
        with open(file_path, 'wb') as f:
            pickle.dump(face_encoding, f)
        return True
    except Exception as e:
        st.error(f"Error saving face encoding: {e}")
        return False


# Modified face registration function
def register_face(user_id):
    """Capture multiple angles and store all encodings"""
    encodings = []
    directions = ['front', 'left', 'right']
    
    for direction in directions:
        st.write(f"Face {direction} and click capture")
        img_file = st.camera_input(f"Face {direction}", key=f"cam_{direction}")
        
        if img_file:
            image = Image.open(img_file)
            image_array = np.array(image)
            
            # Get face encoding
            face_encodings = face_recognition.face_encodings(image_array)
            if face_encodings:
                encodings.extend(face_encodings)  # Store all encodings
                
    if len(encodings) < 3:
        st.error("Failed to capture sufficient angles")
        return False
    
    # Save ALL encodings to pickle file
    with open(os.path.join(FACE_ENCODINGS_DIR, f"user_{user_id}.pkl"), 'wb') as f:
        pickle.dump(encodings, f)
    
    return True

# Modified verification function
def verify_face(image_array, user_id):
    """Verify against all stored encodings"""
    try:
        with open(os.path.join(FACE_ENCODINGS_DIR, f"user_{user_id}.pkl"), 'rb') as f:
            stored_encodings = pickle.load(f)
    except:
        return False
    
    current_encoding = face_recognition.face_encodings(image_array)
    if not current_encoding:
        return False
    
    # Compare with all stored encodings
    matches = face_recognition.compare_faces(stored_encodings, current_encoding[0], tolerance=0.4)
    return any(matches)
# Attendance functions
def mark_attendance(user_id, verification_method):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M:%S")

    # Check if already checked in today
    c.execute("SELECT check_in, check_out FROM attendance WHERE user_id = ? AND date = ?", (user_id, today))
    result = c.fetchone()

    if result is None:
        # First check-in of the day
        c.execute(
            "INSERT INTO attendance (user_id, date, check_in, status, verification_method) VALUES (?, ?, ?, ?, ?)",
            (user_id, today, current_time, "Present", verification_method))
        message = f"Check-in recorded at {current_time}"
    elif result[1] is None:
        # Checking out for the day
        check_in_time = datetime.strptime(result[0], "%H:%M:%S")
        check_out_time = datetime.strptime(current_time, "%H:%M:%S")

        # Calculate work hours
        work_duration = check_out_time - check_in_time
        work_hours = round(work_duration.total_seconds() / 3600, 2)  # Convert to hours

        c.execute("UPDATE attendance SET check_out = ?, work_hours = ? WHERE user_id = ? AND date = ?",
                  (current_time, work_hours, user_id, today))
        message = f"Check-out recorded at {current_time}. You worked for {work_hours} hours today."
    else:
        # Already checked out for the day
        message = "You have already completed your attendance for today."

    conn.commit()
    conn.close()
    return message


def get_user_attendance(user_id, start_date=None, end_date=None):
    conn = sqlite3.connect('attendance_system.db')

    if start_date and end_date:
        query = f"""
        SELECT a.date, a.check_in, a.check_out, a.work_hours, a.status, a.verification_method
        FROM attendance a
        WHERE a.user_id = ? AND a.date BETWEEN ? AND ?
        ORDER BY a.date DESC
        """
        df = pd.read_sql_query(query, conn, params=(user_id, start_date, end_date))
    else:
        query = f"""
        SELECT a.date, a.check_in, a.check_out, a.work_hours, a.status, a.verification_method
        FROM attendance a
        WHERE a.user_id = ?
        ORDER BY a.date DESC
        """
        df = pd.read_sql_query(query, conn, params=(user_id,))

    conn.close()
    return df


def get_all_attendance(start_date=None, end_date=None):
    conn = sqlite3.connect('attendance_system.db')

    if start_date and end_date:
        query = f"""
        SELECT u.name, a.date, a.check_in, a.check_out, a.work_hours, a.status, a.verification_method
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE a.date BETWEEN ? AND ?
        ORDER BY a.date DESC, u.name
        """
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    else:
        query = f"""
        SELECT u.name, a.date, a.check_in, a.check_out, a.work_hours, a.status, a.verification_method
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.date DESC, u.name
        """
        df = pd.read_sql_query(query, conn)

    conn.close()
    return df


# Daily Report functions
def submit_daily_report(user_id, project, activities, achievements, challenges):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    # Check if report already exists for today and project
    c.execute("SELECT id FROM daily_reports WHERE user_id = ? AND date = ? AND project = ?", (user_id, today, project))
    result = c.fetchone()

    if result:
        # Update existing report
        c.execute("""UPDATE daily_reports 
                     SET activities = ?, achievements = ?, challenges = ? 
                     WHERE id = ?""",
                  (activities, achievements, challenges, result[0]))
        message = "Your daily report has been updated."
    else:
        # Insert new report
        c.execute("""INSERT INTO daily_reports 
                     (user_id, date, project, activities, achievements, challenges) 
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (user_id, today, project, activities, achievements, challenges))
        message = "Your daily report has been submitted."

    conn.commit()
    conn.close()
    return message


def get_user_reports(user_id, start_date=None, end_date=None, projects=None):
    conn = sqlite3.connect("attendance_system.db")

    query = """
        SELECT date, project, activities, achievements, challenges
        FROM daily_reports
        WHERE user_id = ?
    """
    params = [user_id]

    if start_date and end_date:
        query += " AND date BETWEEN ? AND ?"
        params += [start_date, end_date]

    if projects:
        placeholders = ','.join('?' for _ in projects)
        query += f" AND project IN ({placeholders})"
        params += projects

    query += " ORDER BY date DESC"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df



def get_all_reports(start_date=None, end_date=None, projects=None):
    conn = sqlite3.connect('attendance_system.db')

    query = """
        SELECT u.name, r.date, r.project, r.activities, r.achievements, r.challenges
        FROM daily_reports r
        JOIN users u ON r.user_id = u.id
        WHERE 1=1
    """
    params = []

    if start_date and end_date:
        query += " AND r.date BETWEEN ? AND ?"
        params += [start_date, end_date]

    if projects:
        placeholders = ','.join('?' for _ in projects)
        query += f" AND r.project IN ({placeholders})"
        params += projects

    query += " ORDER BY r.date DESC, u.name"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df



# Salary Management functions
def add_salary(user_id, month, year, base_salary, bonus=0, deductions=0):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    total_salary = base_salary + bonus - deductions

    # Check if salary record already exists for this month and year
    c.execute("SELECT id FROM salary WHERE user_id = ? AND month = ? AND year = ?", (user_id, month, year))
    result = c.fetchone()

    if result:
        # Update existing record
        c.execute("""
        UPDATE salary SET base_salary = ?, bonus = ?, deductions = ?, total_salary = ? 
        WHERE id = ?
        """, (base_salary, bonus, deductions, total_salary, result[0]))
        message = f"Salary record updated for {month} {year}"
    else:
        # Create new record
        c.execute("""
        INSERT INTO salary (user_id, month, year, base_salary, bonus, deductions, total_salary)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, month, year, base_salary, bonus, deductions, total_salary))
        message = f"Salary record created for {month} {year}"

    conn.commit()
    conn.close()
    return message


def process_payment(salary_id):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    payment_date = datetime.now().strftime("%Y-%m-%d")
    c.execute("UPDATE salary SET payment_status = 'Paid', payment_date = ? WHERE id = ?", (payment_date, salary_id))

    conn.commit()
    conn.close()
    return "Payment processed successfully"


def get_user_salary(user_id):
    conn = sqlite3.connect('attendance_system.db')

    query = f"""
    SELECT id, month, year, base_salary, bonus, deductions, total_salary, payment_status, payment_date
    FROM salary
    WHERE user_id = ?
    ORDER BY year DESC, CASE 
        WHEN month = 'January' THEN 1
        WHEN month = 'February' THEN 2
        WHEN month = 'March' THEN 3
        WHEN month = 'April' THEN 4
        WHEN month = 'May' THEN 5
        WHEN month = 'June' THEN 6
        WHEN month = 'July' THEN 7
        WHEN month = 'August' THEN 8
        WHEN month = 'September' THEN 9
        WHEN month = 'October' THEN 10
        WHEN month = 'November' THEN 11
        WHEN month = 'December' THEN 12
    END DESC
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))

    conn.close()
    return df


def get_all_salary(month=None, year=None):
    conn = sqlite3.connect('attendance_system.db')

    if month and year:
        query = f"""
        SELECT s.id, u.name, s.month, s.year, s.base_salary, s.bonus, s.deductions, s.total_salary, s.payment_status, s.payment_date
        FROM salary s
        JOIN users u ON s.user_id = u.id
        WHERE s.month = ? AND s.year = ?
        ORDER BY u.name
        """
        df = pd.read_sql_query(query, conn, params=(month, year))
    else:
        query = f"""
        SELECT s.id, u.name, s.month, s.year, s.base_salary, s.bonus, s.deductions, s.total_salary, s.payment_status, s.payment_date
        FROM salary s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.year DESC, CASE 
            WHEN s.month = 'January' THEN 1
            WHEN s.month = 'February' THEN 2
            WHEN s.month = 'March' THEN 3
            WHEN s.month = 'April' THEN 4
            WHEN s.month = 'May' THEN 5
            WHEN s.month = 'June' THEN 6
            WHEN s.month = 'July' THEN 7
            WHEN s.month = 'August' THEN 8
            WHEN s.month = 'September' THEN 9
            WHEN s.month = 'October' THEN 10
            WHEN s.month = 'November' THEN 11
            WHEN s.month = 'December' THEN 12
        END DESC, u.name
        """
        df = pd.read_sql_query(query, conn)

    conn.close()
    return df


# User Management functions
def get_all_users():
    try:
        conn = sqlite3.connect('attendance_system.db')
        query = """
        SELECT id, username, name, email, phone, department, join_date, role, photo
        FROM users
        ORDER BY name
        """
        users_df = pd.read_sql_query(query, conn)
        conn.close()
        return users_df
    except Exception as e:
        st.error(f"Error fetching users: {str(e)}")
        return pd.DataFrame()


# Function to delete a user
def delete_user(user_id):
    try:
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error deleting user: {str(e)}")
        return False

# Function to update user details
def update_user(user_id, name, email, phone, department, role, join_date=None):
    try:
        user_id = int(user_id)  # Ensure it's a regular Python int
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        
        c.execute("""
        UPDATE users SET name = ?, email = ?, phone = ?, department = ?, role = ?, join_date = ?
        WHERE id = ?
        """, (name, email, phone, department, role, join_date, user_id))
        
        conn.commit()
        conn.close()
        return True, "User updated successfully"
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    except Exception as e:
        return False, f"Error updating user: {str(e)}"

# Function to change password
def change_password(user_id, new_password):
    try:
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        
        hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
        c.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, user_id))
        
        conn.commit()
        conn.close()
        return True, "Password changed successfully"
    except sqlite3.Error as e:
        return False, f"Password change failed: {str(e)}"

# Function to get user information
def get_user_info(user_id):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    
    c.execute("""
    SELECT username, name, email, phone, department, join_date, role, photo
    FROM users WHERE id = ?
    """, (user_id,))
    
    result = c.fetchone()
    conn.close()
    
    if result:
        return {
            'username': result[0],
            'name': result[1],
            'email': result[2],
            'phone': result[3],
            'department': result[4],
            'join_date': result[5],
            'role': result[6],
            'photo': result[7]
        }
    return None

# Function to get user role (for admin protection)
def get_user_role(user_id):
    try:
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        role = c.fetchone()[0]
        conn.close()
        return role
    except:
        return None

# Function to display user image
def display_user_image(photo_bytes):
    if photo_bytes:
        try:
            image = Image.open(BytesIO(photo_bytes))
            return image
        except:
            return None
    return None

# Custom CSS for better UI
st.markdown("""
<style>
    .user-card {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
        background-color: #f9f9f9;
    }
    .required-field::after {
        content: "*";
        color: red;
        margin-left: 2px;
    }
    .user-image {
        border-radius: 50%;
        object-fit: cover;
    }
    .st-emotion-cache-16idsys p {
        font-weight: bold;
    }
    .delete-btn {
        color: white;
        background-color: #ff4b4b;
        border-radius: 5px;
        padding: 2px 8px;
        border: none;
        cursor: pointer;
    }
    .admin-badge {
        background-color: #4CAF50;
        color: white;
        padding: 2px 8px;
        border-radius: 5px;
        font-size: 0.8em;
    }
    .employee-badge {
        background-color: #2196F3;
        color: white;
        padding: 2px 8px;
        border-radius: 5px;
        font-size: 0.8em;
    }
</style>
""", unsafe_allow_html=True)


# Generate reports
def generate_attendance_report(month, year):
    conn = sqlite3.connect('attendance_system.db')

    # Get the first and last day of the specified month
    if month == 1:
        first_day = f"{year}-01-01"
        last_day = f"{year}-01-31"
    elif month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):  # Leap year
            last_day = 29
        else:
            last_day = 28
        first_day = f"{year}-02-01"
        last_day = f"{year}-02-{last_day}"
    elif month in [4, 6, 9, 11]:
        first_day = f"{year}-{month:02d}-01"
        last_day = f"{year}-{month:02d}-30"
    else:
        first_day = f"{year}-{month:02d}-01"
        last_day = f"{year}-{month:02d}-31"

    query = f"""
    SELECT u.name, u.department, 
           COUNT(CASE WHEN a.status = 'Present' THEN 1 END) as present_days,
           COUNT(DISTINCT a.date) as total_days,
           SUM(a.work_hours) as total_hours
    FROM users u
    LEFT JOIN attendance a ON u.id = a.user_id AND a.date BETWEEN ? AND ?
    WHERE u.role = 'employee'
    GROUP BY u.id
    ORDER BY u.name
    """

    df = pd.read_sql_query(query, conn, params=(first_day, last_day))

    conn.close()
    return df


# UI Functions
def login_page():
    st.title("Employee Attendance System")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("<h3 style='text-align: center;'>LOGIN</h3>", unsafe_allow_html=True)

        login_method = st.radio("Login Method", ["Password", "Biometric"], horizontal=True)

        if login_method == "Password":
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")

            if st.button("Login"):
                if username and password:
                      # First check fixed sales login
                    if username == SALES_USERNAME and password == SALES_PASSWORD:
                        st.session_state.authenticated = True
                        st.session_state.is_sales_login = True
                        st.session_state.username = SALES_USERNAME
                        st.success(f"Welcome, Sales User!")
                        st.rerun()
                    else:
                        # Normal database authentication
                        user = authenticate(username, password)
                        if user:
                            st.session_state.authenticated = True
                            st.session_state.user_id = user['id']
                            st.session_state.user_role = user['role']
                            st.session_state.username = username
                            st.session_state.is_sales_login = False
                            st.success(f"Welcome, {user['name']}!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
                else:
                    st.warning("Please enter both username and password")
        else:
            st.write("Look at the camera for face verification")
            img_file = st.camera_input("Take a photo for face verification", key="login_camera")

            if img_file is not None:
                image = Image.open(img_file)
                image_array = np.array(image)
                
                # Load face encodings
                face_encodings_db = load_face_encodings()
                
                # Detect faces
                face_locations = face_recognition.face_locations(image_array)
                if len(face_locations) != 1:
                    st.error("Please ensure only one face is in the frame")
                    return
                
                # Get encoding
                current_encoding = face_recognition.face_encodings(image_array, face_locations)[0]
                
                # Find matches
                matches = []
                for user_id, saved_encoding in face_encodings_db.items():
                    match = face_recognition.compare_faces([saved_encoding], current_encoding, tolerance=0.5)
                    if match[0]:
                        matches.append(user_id)
                
                if matches:
                    # Get the first match (you might want to handle multiple matches differently)
                    user_id = matches[0]
                    
                    # Get user details from database
                    conn = sqlite3.connect('attendance_system.db')
                    c = conn.cursor()
                    c.execute("SELECT id, username, role, name FROM users WHERE id = ?", (user_id,))
                    user = c.fetchone()
                    conn.close()
                    
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user_id = user[0]
                        st.session_state.username = user[1]
                        st.session_state.user_role = user[2]
                        st.success(f"Welcome, {user[3]}!")
                        st.rerun()
                    else:
                        st.error("User not found in database")
                else:
                    st.error("No matching face found. Please try again or use password login.")

    with col2:
    # Display system overview image
        st.image(
            r"Z:\bioattendance\images\system_overview.png",  # Path to your image file
            width=400,  # Adjust width as needed
            
            use_column_width='auto',  # Options: 'auto', 'always', or 'never'
        )
        
        # Optional: Add some styling to the image container
        st.markdown("""
        <style>
            .system-image {
                border: 2px solid #f0f2f6;
                border-radius: 10px;
                padding: 10px;
                background: white;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                
            }
        </style>
        """, unsafe_allow_html=True)

# Add this import at the top of your file with the other imports
import shutil
import os


# Add these functions to the database utility functions section

def get_all_salary_info(month, year):
    """Get all salary information for a specific month and year"""
    conn = sqlite3.connect('attendance_system.db')
    query = """
    SELECT u.name, s.month, s.year, s.base_salary, s.bonus, s.deductions, 
           s.total_salary, s.payment_status, s.payment_date
    FROM salary s
    JOIN users u ON s.user_id = u.id
    WHERE s.month = ? AND s.year = ?
    ORDER BY u.name
    """
    salary_df = pd.read_sql_query(query, conn, params=(month, year))
    conn.close()

    return salary_df


def get_monthly_attendance_summary(user_id, month, year):
    """Get attendance summary for a specific user for a month"""
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    # Get start and end date for the month
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day}"

    # Count present days
    c.execute("""
    SELECT COUNT(*), SUM(work_hours)
    FROM attendance
    WHERE user_id = ? AND date BETWEEN ? AND ? AND status = 'Present'
    """, (user_id, start_date, end_date))

    result = c.fetchone()
    present_days = result[0] if result[0] else 0
    work_hours = result[1] if result[1] else 0

    conn.close()

    return {
        'present_days': present_days,
        'work_hours': work_hours
    }


def save_salary_info(user_id, month, year, base_salary, bonus, deductions, total_salary, payment_status):
    """Save or update salary information for a user"""
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    
    # Check if record exists
    c.execute("""
    SELECT id FROM salary
    WHERE user_id = ? AND month = ? AND year = ?
    """, (user_id, month, year))
    
    existing = c.fetchone()
    payment_date = datetime.now().strftime("%Y-%m-%d") if payment_status == "Paid" else None
    
    if existing:
        # Update existing record
        c.execute("""
        UPDATE salary
        SET base_salary = ?, bonus = ?, deductions = ?, total_salary = ?,
            payment_status = ?, payment_date = ?
        WHERE user_id = ? AND month = ? AND year = ?
        """, (base_salary, bonus, deductions, total_salary, payment_status, 
              payment_date, user_id, month, year))
    else:
        # Create new record
        c.execute("""
        INSERT INTO salary (user_id, month, year, base_salary, bonus, deductions,
                            total_salary, payment_status, payment_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, month, year, base_salary, bonus, deductions, 
              total_salary, payment_status, payment_date))
    
    conn.commit()
    conn.close()
    
    return True

def get_salary_history(month=None, year=None):
    """Get salary history with optional month/year filter"""
    conn = sqlite3.connect('attendance_system.db')
    
    query = """
    SELECT u.name as employee_name, s.month, s.year, s.base_salary, s.bonus,
           s.deductions, s.total_salary, s.payment_status, s.payment_date
    FROM salary s
    JOIN users u ON s.user_id = u.id
    """
    
    params = []
    where_clauses = []
    
    # Add filters if provided
    if month:
        month_num = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }.get(month)
        if month_num:
            where_clauses.append("s.month = ?")
            params.append(month_num)
    
    if year and year != "All":
        where_clauses.append("s.year = ?")
        params.append(year)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " ORDER BY s.year DESC, s.month DESC, u.name"
    
    salary_df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Add month name column
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    
    if not salary_df.empty:
        salary_df['month_name'] = salary_df['month'].apply(
            lambda x: month_names.get(int(x), "") if pd.notnull(x) and str(x).isdigit() else ""
        )
    
    return salary_df

def logout():
    for key in st.session_state.keys():
        del st.session_state[key]
    st.rerun()


def employee_dashboard():
    st.title(f"Employee Dashboard - {st.session_state.username}")

    # Get user info
    user_info = get_user_info(st.session_state.user_id)

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "Mark Attendance", "View Attendance", "Daily Report", "Salary Information", "Leave Management", "Profile",
         "Biometric Setup"]
    )

    if st.sidebar.button("Logout"):
        logout()

    if menu == "Home":
        col1, col2 = st.columns([2, 1])

        with col1:
            st.header("Welcome to Employee Portal")
            st.markdown(f"""
            ### {user_info['name']}
            - **Department:** {user_info['department']}
            - **Joined:** {user_info['join_date']}
            """)

            # Show today's attendance status
            today = datetime.now().strftime("%Y-%m-%d")
            conn = sqlite3.connect('attendance_system.db')
            c = conn.cursor()
            c.execute("SELECT check_in, check_out FROM attendance WHERE user_id = ? AND date = ?",
                      (st.session_state.user_id, today))
            today_attendance = c.fetchone()
            conn.close()

            st.subheader("Today's Status")
            if today_attendance:
                if today_attendance[1]:  # Checked out
                    st.success(f"✅ Checked in at {today_attendance[0]} and checked out at {today_attendance[1]}")
                else:
                    st.info(f"⏳ Checked in at {today_attendance[0]}, not checked out yet")
            else:
                st.warning("❌ Not checked in today")

        with col2:
            st.subheader("Quick Actions")

            # Quick attendance button
            if today_attendance and today_attendance[1]:
                st.button("Already Completed Today", disabled=True)
            elif today_attendance:
                if st.button("Check Out"):
                    message = mark_attendance(st.session_state.user_id, "Manual")
                    st.success(message)
                    st.rerun()
            else:
                if st.button("Check In"):
                    message = mark_attendance(st.session_state.user_id, "Manual")
                    st.success(message)
                    st.rerun()

            

        # Show attendance summary
        st.subheader("Attendance Summary (Last 7 Days)")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        recent_attendance = get_user_attendance(
            st.session_state.user_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
        if not recent_attendance.empty:
            st.dataframe(recent_attendance, use_container_width=True)
        else:
            st.info("No recent attendance records found")

        # Show latest report
        st.subheader("Latest Daily Report")
        recent_reports = get_user_reports(
            st.session_state.user_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
        if not recent_reports.empty:
            latest_report = recent_reports.iloc[0]
            st.markdown(f"**Date:** {latest_report['date']}")
            st.markdown(f"**Activities:** {latest_report['activities']}")
            st.markdown(f"**Achievements:** {latest_report['achievements']}")
            st.markdown(f"**Challenges:** {latest_report['challenges']}")
        else:
            st.info("No recent daily reports found")

    elif menu == "Mark Attendance":
        st.header("Mark Attendance")

        today = datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        st.markdown(f"**Date:** {today} | **Time:** {current_time}")

        # Check current attendance status
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        c.execute("SELECT check_in, check_out FROM attendance WHERE user_id = ? AND date = ?",
                  (st.session_state.user_id, today))
        today_attendance = c.fetchone()
        conn.close()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Attendance Method")
            attendance_method = st.radio("Select verification method:",
                                         ["Manual", "Biometric (Face Recognition)"],
                                         horizontal=True)

            if attendance_method == "Biometric (Face Recognition)":
                # Check if user has facial data
                if st.session_state.face_encodings_db and st.session_state.user_id in st.session_state.face_encodings_db:
                    # Create the camera input once and store the result
                    img_file = st.camera_input("Look at the camera for face verification", key="attendance_camera")

                    # Check if an image was captured
                    if img_file is not None:
                        st.write("Processing face...")

                        try:
                            # Process the captured image
                            image = Image.open(img_file)
                            image_array = np.array(image)

                            # Verify face
                            is_verified = verify_face(image_array, st.session_state.user_id)
                            if is_verified:
                                message = mark_attendance(st.session_state.user_id, "Biometric")
                                st.success(f"Face verified! {message}")
                                st.rerun()
                            else:
                                st.error("Face verification failed. Please try again or use manual check-in.")
                        except Exception as e:
                            st.error(f"Error processing image: {str(e)}")
                    # No else needed here - the camera input will show until the user takes a photo
                else:
                    st.warning("You need to set up your face data in the Biometric Setup section first.")

            # For manual verification
            if attendance_method == "Manual":
                if today_attendance and today_attendance[1]:
                    st.info("You have already completed attendance for today.")
                elif today_attendance:
                    if st.button("Check Out"):
                        message = mark_attendance(st.session_state.user_id, "Manual")
                        st.success(message)
                        st.rerun()
                else:
                    if st.button("Check In"):
                        message = mark_attendance(st.session_state.user_id, "Manual")
                        st.success(message)
                        st.rerun()

        with col2:
            st.subheader("Attendance Status")
            if today_attendance:
                if today_attendance[1]:  # Checked out
                    st.success(f"✅ Checked in at {today_attendance[0]} and checked out at {today_attendance[1]}")
                else:
                    st.info(f"⏳ Checked in at {today_attendance[0]}, not checked out yet")
            else:
                st.warning("❌ Not checked in today")

    elif menu == "View Attendance":
        st.header("My Attendance Records")

        # Date filter
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("From", value=datetime.now() - timedelta(days=30))
        with col2:
            end_date = st.date_input("To", value=datetime.now())

        if start_date > end_date:
            st.error("End date must be after start date")
        else:
            # Get attendance data
            attendance_data = get_user_attendance(
                st.session_state.user_id,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d")
            )

            if not attendance_data.empty:
                # Calculate statistics
                total_days = (end_date - start_date).days + 1
                present_days = attendance_data.shape[0]
                total_work_hours = attendance_data['work_hours'].sum()

                # Display statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Working Days", total_days)
                with col2:
                    st.metric("Days Present", present_days)
                with col3:
                    st.metric("Total Work Hours", f"{total_work_hours:.2f}")

                # Display attendance table
                st.subheader("Attendance Details")
                st.dataframe(attendance_data, use_container_width=True)

                # Download option
                csv = attendance_data.to_csv(index=False)
                st.download_button(
                    label="Download as CSV",
                    data=csv,
                    file_name=f"attendance_{start_date}_to_{end_date}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No attendance records found for the selected date range")

    elif menu == "Daily Report":
        st.header("Daily Reports")
        tab1, tab2 = st.tabs(["Submit Report", "View Reports"])

        # --- TAB 1: SUBMIT REPORT ---
        with tab1:
            st.subheader("Submit Daily Report")
            conn = sqlite3.connect("attendance_system.db")
            c = conn.cursor()
            c.execute("SELECT name FROM projects")
            project_names = [row[0] for row in c.fetchall()]
            conn.close()

            project_options = ["General"] + project_names
            selected_projects = st.multiselect("Select at least one Project", options=project_options)

            if not selected_projects:
                st.warning("⚠️ Please select at least one project.")

            today = datetime.now().strftime("%Y-%m-%d")
            st.markdown(f"**Date:** {today}")
            activities = st.text_area("Activities Performed Today", height=150)
            achievements = st.text_area("Achievements", height=100)
            challenges = st.text_area("Challenges Faced", height=100)

            if st.button("Submit Report"):
                if not selected_projects:
                    st.error("❌ Report not submitted. Select at least one project.")
                else:
                    project_str = ", ".join(selected_projects)
                    conn = sqlite3.connect("attendance_system.db")
                    c = conn.cursor()
                    user_id = st.session_state.user_id

                    # Check if report already exists
                    c.execute("SELECT id FROM daily_reports WHERE user_id = ? AND date = ?", (user_id, today))
                    existing = c.fetchone()

                    if existing:
                        c.execute("""
                            UPDATE daily_reports
                            SET project = ?, activities = ?, achievements = ?, challenges = ?
                            WHERE id = ?
                        """, (project_str, activities, achievements, challenges, existing[0]))
                    else:
                        c.execute("""
                            INSERT INTO daily_reports
                            (user_id, date, project, activities, achievements, challenges)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (user_id, today, project_str, activities, achievements, challenges))

                    conn.commit()
                    conn.close()
                    st.success(f"✅ Report submitted for {today} with projects: {project_str}")

        # --- TAB 2: VIEW REPORTS ---
        with tab2:
            st.header("My Daily Reports")
            conn = sqlite3.connect("attendance_system.db")
            c = conn.cursor()
            c.execute("SELECT DISTINCT project FROM daily_reports WHERE user_id = ?", (st.session_state.user_id,))
            projects = list({p.strip() for row in c.fetchall() for p in row[0].split(",")})
            conn.close()

            selected_projects = st.multiselect("Select Project(s)", options=projects)
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("From", value=datetime.now() - timedelta(days=30))
            with col2:
                end_date = st.date_input("To", value=datetime.now())

            if start_date > end_date:
                st.error("End date must be after start date.")
            else:
                conn = sqlite3.connect("attendance_system.db")
                query = "SELECT date, project, activities, achievements, challenges FROM daily_reports WHERE user_id = ? AND date BETWEEN ? AND ?"
                params = [st.session_state.user_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]

                if selected_projects:
                    query += " AND (" + " OR ".join(["project LIKE ?"] * len(selected_projects)) + ")"
                    params.extend([f"%{proj}%" for proj in selected_projects])

                df = pd.read_sql_query(query, conn, params=params)
                conn.close()

                if not df.empty:
                    for _, row in df.iterrows():
                        with st.expander(f"Report: {row['date']} ({row['project']})"):
                            st.markdown(f"**Activities:** {row['activities']}")
                            st.markdown(f"**Achievements:** {row['achievements'] or 'None'}")
                            st.markdown(f"**Challenges:** {row['challenges'] or 'None'}")

                    csv = df.to_csv(index=False)
                    st.download_button("Download All Reports as CSV", data=csv, file_name="my_reports.csv", mime="text/csv")
                else:
                    st.info("No reports found for selected filters.")



    elif menu == "Leave Management":
        st.header("Leave Management")

        tab1, tab2 = st.tabs(["New Leave Request", "My Leave History"])

        with tab1:
            st.subheader("Submit Leave Request")
            with st.form("leave_form"):
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("Start Date")
                    leave_type = st.selectbox("Leave Type", ["Sick", "Vacation", "Personal", "Other"])
                with col2:
                    end_date = st.date_input("End Date")
                    reason = st.text_area("Reason")

                if st.form_submit_button("Submit Request"):
                    if start_date > end_date:
                        st.error("End date must be after start date")
                    else:
                        create_leave_request(
                            st.session_state.user_id,
                            start_date.strftime("%Y-%m-%d"),
                            end_date.strftime("%Y-%m-%d"),
                            leave_type,
                            reason
                        )
                        st.success("Leave request submitted for admin approval")

        with tab2:
            st.subheader("Leave History")
            leaves = get_employee_leave_requests(st.session_state.user_id)
            if not leaves.empty:
                for _, leave in leaves.iterrows():
                    with st.expander(f"{leave['start_date']} to {leave['end_date']} - {leave['status']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Type:** {leave['leave_type']}")
                            st.markdown(f"**Reason:** {leave['reason']}")
                        with col2:
                            st.markdown(f"**Status:** {leave['status']}")
                            if leave['admin_approval']:
                                st.markdown(f"**Admin Note:** {leave['admin_approval']}")
                                if leave['status'] == 'Approved' and not leave['employee_verification']:
                                    if st.button("Verify Leave", key=f"verify_{leave['id']}"):
                                        verify_leave_request(leave['id'])
                                        st.success("Leave verified!")
            else:
                st.info("No leave requests found")

    
    elif menu == "Salary Information":
        st.header("My Salary Information")

        # Get salary data
        salary_data = get_user_salary(st.session_state.user_id)

        if not salary_data.empty:
            st.subheader("Salary History")

            # Display each salary record as an expandable section
            for _, row in salary_data.iterrows():
                with st.expander(f"{row['month']} {row['year']} - {row['payment_status']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Base Salary:** ${row['base_salary']:.2f}")
                        st.markdown(f"**Bonus:** ${row['bonus']:.2f}")
                        st.markdown(f"**Deductions:** ${row['deductions']:.2f}")
                    with col2:
                        st.markdown(f"**Total Salary:** ${row['total_salary']:.2f}")
                        st.markdown(f"**Payment Status:** {row['payment_status']}")
                        if row['payment_date']:
                            st.markdown(f"**Payment Date:** {row['payment_date']}")
        else:
            st.info("No salary records found")

    elif menu == "Profile":
        st.header("My Profile")

        if user_info:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Personal Information")
                st.markdown(f"**Name:** {user_info['name']}")
                st.markdown(f"**Username:** {user_info['username']}")
                st.markdown(f"**Email:** {user_info['email']}")
                st.markdown(f"**Phone:** {user_info['phone']}")
                st.markdown(f"**Department:** {user_info['department']}")
                st.markdown(f"**Join Date:** {user_info['join_date']}")

            with col2:
                st.subheader("Change Password")
                current_password = st.text_input("Current Password", type="password")
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm New Password", type="password")

                if st.button("Update Password"):
                    if not current_password or not new_password or not confirm_password:
                        st.warning("Please fill all password fields")
                    elif new_password != confirm_password:
                        st.error("New passwords do not match")
                    else:
                        # Verify current password
                        hashed_current = hashlib.sha256(current_password.encode()).hexdigest()
                        conn = sqlite3.connect('attendance_system.db')
                        c = conn.cursor()
                        c.execute("SELECT id FROM users WHERE id = ? AND password = ?",
                                  (st.session_state.user_id, hashed_current))
                        user_verified = c.fetchone()
                        conn.close()

                        if user_verified:
                            message = change_password(st.session_state.user_id, new_password)
                            st.success(message)
                        else:
                            st.error("Current password is incorrect")

    elif menu == "Biometric Setup":
        st.header("Biometric Setup")

        st.markdown("""
        ### Face Recognition Setup
        Use this section to register or update your facial data for biometric login and attendance.
        """)

        # Check if user already has facial data
        if st.session_state.face_encodings_db and st.session_state.user_id in st.session_state.face_encodings_db:
            st.info("You already have facial data registered. You can update it below.")
        else:
            st.warning("No facial data registered yet. Please use the camera below to register your face.")

        st.write("For best results, ensure good lighting and position your face clearly in the frame.")
        face_image = st.camera_input("Take a photo for face registration", key="face_reg_camera")

        if face_image is not None:
            image = Image.open(face_image)
            image_array = np.array(image)
            face_locations = face_recognition.face_locations(image_array)

            if not face_locations:
                st.error("No face detected in the image. Please try again with better lighting and positioning.")
            else:
                if len(face_locations) > 1:
                    st.warning("Multiple faces detected. Using the most prominent face.")
                
                face_encoding = face_recognition.face_encodings(image_array, [face_locations[0]])[0]
                
                # Save to pickle file
                if save_face_encoding(st.session_state.user_id, face_encoding):
                    st.session_state.face_encodings_db = load_face_encodings()
                    st.success("Face registered successfully! You can now use face verification.")


def admin_dashboard():
    st.title("Admin Dashboard")

    # Get user info
    user_info = get_user_info(st.session_state.user_id)

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "User Management", "Attendance Management", "Leave Management", "Reports", "Project Reports", "Salary Management", "Employee Directory","Admin Directory",
         "Settings"],index=["Home", "User Management", "Attendance Management","Leave Management","Reports","Project Reports", "Salary Management",  "Employee Directory","Admin Directory","Settings"].index(
            st.session_state.get("menu", "Home")
        )
    )
    st.session_state.menu = menu  # Sync selected menu

    if st.sidebar.button("Logout"):
        logout()

    if menu == "Home":
        st.header(f"Welcome, {user_info['name']}")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("System Overview")

            # Get some system statistics
            conn = sqlite3.connect('attendance_system.db')
            c = conn.cursor()

            # Count total users
            c.execute("SELECT COUNT(*) FROM users WHERE role = 'employee'")
            employee_count = c.fetchone()[0]

            # Count today's attendance
            today = datetime.now().strftime("%Y-%m-%d")
            c.execute("SELECT COUNT(*) FROM attendance WHERE date = ?", (today,))
            today_attendance = c.fetchone()[0]

            # Count today's reports
            c.execute("SELECT COUNT(*) FROM daily_reports WHERE date = ?", (today,))
            today_reports = c.fetchone()[0]

            conn.close()

            # Display metrics
            st.metric("Total Employees", employee_count)
            st.metric("Today's Attendance", today_attendance)
            st.metric("Today's Reports", today_reports)

        with col2:
            st.subheader("Quick Actions")
            btn_col1, btn_col2 = st.columns(2)

            button_style = """
                <style>
                div.stButton > button {
                    width: 100%;
                }
                </style>
            """
            st.markdown(button_style, unsafe_allow_html=True)

            # Left side
            with btn_col1:
                if st.button("View Today's Attendance", key="btn_att"):
                    st.session_state.menu = "Attendance Management"
                    st.rerun()
                if st.button("Generate Monthly Report", key="btn_report"):
                    st.session_state.menu = "Reports"
                    st.rerun()

            # Right side
            with btn_col2:
                if st.button("Add New User", key="btn_add"):
                    st.session_state.menu = "User Management"
                    st.session_state.user_management_tab = "Add User"
                    st.rerun()
                if st.button("Open Sales Dashboard", key="btn_sales"):
                    st.session_state.is_sales_login = True
                    st.rerun()




    elif menu == "Admin Directory":
        display_user_directory("Admin Directory", "admin")

    elif menu == "Employee Directory":
        display_user_directory("Employee Directory", "employee")

    elif menu == "User Management":
        st.header("User Management")

        tab_labels = ["All Users", "Add User", "Edit User"]
        default_tab = st.session_state.get("user_management_tab", "All Users")

        tab1, tab2, tab3 = st.tabs(tab_labels)

        with tab1:
            st.subheader("All Users")
            users_df = get_all_users()
            
            if not users_df.empty:
                # Search and filter options
                col1, col2 = st.columns([2, 1])
                with col1:
                    search_query = st.text_input("Search users", placeholder="Enter name, email, or department")
                with col2:
                    filter_dept = st.selectbox("Filter by department", 
                                            ["All"] + list(users_df['department'].unique()), 
                                            index=0)
                
                # Apply filters
                filtered_df = users_df.copy()
                if search_query:
                    filtered_df = filtered_df[
                        filtered_df['name'].str.contains(search_query, case=False) |
                        filtered_df['email'].str.contains(search_query, case=False) |
                        filtered_df['department'].str.contains(search_query, case=False)
                    ]
                
                if filter_dept != "All":
                    filtered_df = filtered_df[filtered_df['department'] == filter_dept]
                
                # Display users with enhanced styling
                if not filtered_df.empty:
                    st.write(f"Showing {len(filtered_df)} users")
                    
                    # Use Streamlit's native dataframe with improved column config
                    st.dataframe(
                        filtered_df[['id', 'username', 'name', 'email', 'phone', 'department', 'join_date', 'role']],
                        column_config={
                            "id": st.column_config.NumberColumn("ID", width="small"),
                            "username": st.column_config.TextColumn("Username"),
                            "name": st.column_config.TextColumn("Full Name"),
                            "email": st.column_config.TextColumn("Email"),
                            "phone": st.column_config.TextColumn("Phone", width="medium"),
                            "department": st.column_config.TextColumn("Department"),
                            "join_date": st.column_config.DateColumn("Join Date"),
                            "role": st.column_config.TextColumn("Role", width="small"),
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # User detail section with action buttons
                    st.subheader("User Details & Actions")
                    for i, row in filtered_df.iterrows():
                        with st.container():
                            col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
                            
                            with col1:
                                # Display user photo if available
                                if row['photo']:
                                    user_img = display_user_image(row['photo'])
                                    if user_img:
                                        st.image(user_img, width=80, caption=f"ID: {row['id']}")
                                    else:
                                        st.image("https://via.placeholder.com/80", width=80, caption=f"ID: {row['id']}")
                                else:
                                    st.image("https://via.placeholder.com/80", width=80, caption=f"ID: {row['id']}")
                            
                            with col2:
                                st.markdown(f"**{row['name']}** ({row['username']})")
                                st.markdown(f"📧 {row['email'] if row['email'] else 'No email'}")
                                st.markdown(f"📱 {row['phone'] if row['phone'] else 'No phone'}")
                            
                            with col3:
                                st.markdown(f"**Department:** {row['department']}")
                                st.markdown(f"**Joined:** {row['join_date']}")
                                role_badge = "admin-badge" if row['role'] == "admin" else "employee-badge"
                                st.markdown(f"<span class='{role_badge}'>{row['role'].upper()}</span>", unsafe_allow_html=True)
                            
                            with col4:
                                # Action buttons column
                                action_col1, action_col2 = st.columns(2)
                                
                                # Edit button
                                if action_col1.button("✏️ Edit", key=f"edit_{row['id']}"):
                                    st.session_state.editing_user_id = row['id']
                                    st.session_state.show_edit_form = True
                                
                                # Delete button (not available for admins)
                                if row['role'] != 'admin':
                                    if action_col2.button("🗑️ Delete", key=f"delete_{row['id']}"):
                                        if delete_user(row['id']):
                                            st.success(f"User {row['username']} deleted successfully!")
                                            st.rerun()
                                else:
                                    action_col2.markdown("<span style='color:gray'>Protected</span>", unsafe_allow_html=True)
                        
                        st.divider()
                    
                    # Edit user form (appears when edit button is clicked)
                    if 'show_edit_form' in st.session_state and st.session_state.show_edit_form:
                        user_id = st.session_state.editing_user_id
                        user_info = get_user_info(user_id)
                        
                        if user_info:
                            st.subheader(f"Edit User: {user_info['name']}")
                            
                            with st.form(key=f"edit_user_form_{user_id}"):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    username = st.text_input("Username", user_info['username'], disabled=True)
                                    name = st.text_input("Full Name*", user_info['name'])
                                    email = st.text_input("Email", user_info['email'] if user_info['email'] else "")
                                
                                with col2:
                                    phone = st.text_input("Phone*", user_info['phone'] if user_info['phone'] else "", max_chars=10)
                                    department = st.selectbox("Department*", ["Software", "Hardware", "Sales"], 
                                                        index=["Software", "Hardware", "Sales"].index(user_info['department']) 
                                                        if user_info['department'] in ["Software", "Hardware", "Sales"] else 0)
                                    role = st.selectbox("Role*", ["admin", "employee"], 
                                                    index=["admin", "employee"].index(user_info['role']) 
                                                    if user_info['role'] in ["admin", "employee"] else 1)
                                    
                                
                                
                                col1, col2 = st.columns(2)
                                update_button = col1.form_submit_button("Update User")
                                cancel_button = col2.form_submit_button("Cancel")
                                
                                if cancel_button:
                                    st.session_state.show_edit_form = False
                                    st.rerun()
                                
                                if update_button:
                                    errors = []
                                    
                                    # Validate required fields
                                    if not name: errors.append("Full Name is required")
                                    if not phone: errors.append("Phone is required")
                                    if phone and (not phone.isdigit() or len(phone) != 10): 
                                        errors.append("Phone must be 10 digits")
                                    
                                    if errors:
                                        for error in errors:
                                            st.error(error)
                                    else:
                                        # Update user information
                                        success, message = update_user(
                                            user_id, name, email, phone, department, role, user_info['join_date']
                                        )
                                        
                                        
                    # Download option
                    export_df = filtered_df.drop(columns=['photo'], errors='ignore')
                    csv = export_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download User List",
                        data=csv,
                        file_name="users_list.csv",
                        mime="text/csv",
                        key="user_list_download"
                    )
                else:
                    st.info("No users match your search criteria")
            else:
                st.info("No users found in the system")

        # TAB 2: Add New User
        with tab2:
            st.subheader("Add New User")
            
            # Form with validation
            with st.form("add_user_form", clear_on_submit=True):
                # Create two columns for form layout
                col1, col2 = st.columns(2)
                
                with col1:
                    # Required fields are marked with *
                    st.markdown("<p class='required-field'>Username</p>", unsafe_allow_html=True)
                    username = st.text_input("", placeholder="Enter username", key="username_input")
                    
                    st.markdown("<p class='required-field'>Password</p>", unsafe_allow_html=True)
                    password = st.text_input("", placeholder="Enter password", type="password", key="password_input")
                    
                    st.markdown("<p class='required-field'>Full Name</p>", unsafe_allow_html=True)
                    name = st.text_input("", placeholder="Enter full name", key="name_input")
                    
                    email = st.text_input("Email", placeholder="user@company.com", key="email_input")
                
                with col2:
                    st.markdown("<p class='required-field'>Phone</p>", unsafe_allow_html=True)
                    phone = st.text_input("", placeholder="Enter 10-digit phone number", max_chars=10, key="phone_input")
                    
                    st.markdown("<p class='required-field'>Department</p>", unsafe_allow_html=True)
                    department = st.selectbox("", ["Software", "Hardware", "Sales"], key="department_input")
                    
                    st.markdown("<p class='required-field'>Role</p>", unsafe_allow_html=True)
                    role = st.selectbox("", ["employee", "admin"], key="role_input")
                    
                    st.markdown("<p class='required-field'>Joining Date</p>", unsafe_allow_html=True)
                    join_date = st.date_input("", value=datetime.now(), key="date_input")
                
                # Photo upload
                st.markdown("<p>Profile Photo</p>", unsafe_allow_html=True)
                photo = st.file_uploader("", type=["jpg", "jpeg", "png"], key="photo_input")
                
                st.markdown("**Fields marked with * are required**")
                
                submitted = st.form_submit_button("Add User", use_container_width=True)
                
                if submitted:
                    errors = []
                    
                    # Validate required fields
                    if not username: errors.append("Username is required")
                    if not password: errors.append("Password is required")
                    if not name: errors.append("Full Name is required")
                    if not phone: errors.append("Phone number is required")
                    if phone and (not phone.isdigit() or len(phone) != 10): 
                        errors.append("Phone must be 10 digits")
                    
                    if errors:
                        for error in errors:
                            st.error(error)
                    else:
                        # Process photo
                        photo_bytes = None
                        if photo is not None:
                            photo_bytes = photo.getvalue()
                        
                        # Add user
                        success, user_id, message = add_user(
                            username, password, role, name, 
                            email, phone, department, join_date, photo_bytes
                        )
                        
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

            # Display sample preview of the form
            with st.expander("Need help? See an example of a properly filled form"):
                st.markdown("""
                **Example User Information:**
                - **Username**: john_doe
                - **Password**: Secure password (at least 8 characters)
                - **Full Name**: John Doe
                - **Email**: john.doe@company.com
                - **Phone**: 1234567890 (10 digits)
                - **Department**: Software
                - **Role**: employee (or admin for administrative access)
                - **Photo**: Upload a square image for best results
                """)
        with tab3:
            st.subheader("Edit User")

            # First, get the absolute path to ensure consistent database access
            import os
            db_path = os.path.abspath('attendance_system.db')

            users_df = get_all_users()
            if not users_df.empty:
                user_to_edit = st.selectbox("Select User", users_df['username'].tolist(), key="user_to_edit_selectbox")

                # Get user details
                selected_user = users_df[users_df['username'] == user_to_edit]
                if not selected_user.empty:
                    selected_user = selected_user.iloc[0]
                    # Convert NumPy int64 to Python int
                    user_id = int(selected_user['id'])
                    st.subheader(f"Edit User (User ID: {user_id})") 

                    col1, col2 = st.columns(2)

                    with col1:
                        name = st.text_input("Full Name", value=selected_user['name'])
                        email = st.text_input("Email", value=selected_user['email'])
                        phone = st.text_input("Phone", value=selected_user['phone'])

                    with col2:
                        department = st.text_input("Department", value=selected_user['department'])

                        try:
                            default_date = datetime.strptime(selected_user['join_date'], "%Y-%m-%d").date() if \
                                selected_user['join_date'] else datetime.now().date()
                        except:
                            default_date = datetime.now().date()

                        join_date = st.date_input("Joining Date", value=default_date, key=f"join_date_{user_id}")

                        role = st.selectbox("Role", ["employee", "admin"], key="role_selectbox",
                                            index=0 if selected_user['role'] == "employee" else 1)
                        reset_password = st.checkbox("Reset Password")

                        if reset_password:
                            new_password = st.text_input("New Password", type="password")

                    if st.button("Update User", key="update_user_button"):
                        if not name.strip():
                            st.error("Name field cannot be empty")
                        else:
                            # Define a function that uses the same db_path
                            def update_user_with_path(user_id, name, email, phone, department, role, join_date):
                                try:
                                    conn = sqlite3.connect(db_path)
                                    c = conn.cursor()

                                    # Print debug info before update
                                    c.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
                                    before_update = c.fetchone()

                                    c.execute("""
                                    UPDATE users SET name = ?, email = ?, phone = ?, department = ?, join_date = ?, role = ?
                                    WHERE id = ?
                                    """, (name, email, phone, department, join_date, role, user_id))

                                    rows_affected = c.rowcount
                                    conn.commit()

                                    # Verify the update worked
                                    c.execute("SELECT id, username, name FROM users WHERE id = ?", (user_id,))
                                    after_update = c.fetchone()

                                    conn.close()
                                    return True, f"User updated successfully. Rows affected: {rows_affected}", before_update, after_update
                                except sqlite3.Error as e:
                                    return False, f"Database error: {str(e)}", None, None
                                except Exception as e:
                                    return False, f"Error updating user: {str(e)}", None, None

                            # Use the updated function
                            success, message, before, after = update_user_with_path(user_id, name, email, phone,
                                                                                    department, role, join_date)

                            if success:
                                st.success(message)
                                st.write(f"Before update: {before}")
                                st.write(f"After update: {after}")

                                # Handle password reset
                                if reset_password:
                                    if not new_password.strip():
                                        st.error("Please enter a new password")
                                    else:
                                        # Use the same db_path for password change
                                        def change_password_with_path(user_id, new_password):
                                            try:
                                                conn = sqlite3.connect(db_path)
                                                c = conn.cursor()

                                                hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
                                                c.execute("UPDATE users SET password = ? WHERE id = ?",
                                                          (hashed_password, user_id))

                                                conn.commit()
                                                conn.close()
                                                return True, "Password changed successfully"
                                            except sqlite3.Error as e:
                                                return False, f"Password change failed: {str(e)}"

                                        pw_success, pw_message = change_password_with_path(user_id, new_password)
                                        if pw_success:
                                            st.success(pw_message)
                                        else:
                                            st.error(pw_message)

                                # Put this inside a button to avoid automatic rerun that might disrupt debugging
                                if st.button("Reload Page"):
                                    st.rerun()
                            else:
                                st.error(message)
                else:
                    st.warning("Selected user not found")
            else:
                st.info("No users found to edit")
    
    elif menu == "Leave Management":
        st.header("Leave Management")
        tab1, tab2 = st.tabs(["Pending Approvals", "Leave History"])
    
        with tab1:
            pending_leaves = get_pending_leave_requests()
            if not pending_leaves.empty:
                st.subheader("Pending Leave Requests")
                for _, leave in pending_leaves.iterrows():
                    with st.expander(f"{leave['name']} - {leave['start_date']} to {leave['end_date']}"):
                        st.markdown(f"**Type:** {leave['leave_type']}")
                        st.markdown(f"**Reason:** {leave['reason']}")
                        
                        col1, col2 = st.columns(2)
                        approval_note = col1.text_input("Approval Note", key=f"note_{leave['id']}")
                        
                        col2.markdown("##")
                        if col2.button("Approve", key=f"approve_{leave['id']}"):
                            update_leave_status(leave['id'], "Approved", approval_note)
                            st.success("Leave approved")
                            st.rerun()
                        if col2.button("Reject", key=f"reject_{leave['id']}"):
                            update_leave_status(leave['id'], "Rejected", approval_note)
                            st.success("Leave rejected")
                            st.rerun()
            else:
                st.info("No pending leave requests")

        with tab2:
            st.subheader("Leave Request History")
            
            # Filters
            col1, col2, col3 = st.columns(3)
            with col1:
                status_filter = st.selectbox("Filter by Status", ["All", "Approved", "Rejected", "Pending"])
            with col2:
                start_date_filter = st.date_input("Start Date", value=datetime.now() - timedelta(days=30))
            with col3:
                end_date_filter = st.date_input("End Date", value=datetime.now())
            
            # Get filtered data
            all_leaves = get_all_leave_requests(
                status_filter if status_filter != "All" else None,
                start_date_filter.strftime("%Y-%m-%d"),
                end_date_filter.strftime("%Y-%m-%d")
            )
            
            if not all_leaves.empty:
                # Search functionality
                search_query = st.text_input("Search by Employee Name")
                
                # Apply search filter
                if search_query:
                    all_leaves = all_leaves[all_leaves['name'].str.contains(search_query, case=False)]
                
                # Display in a table format
                for _, leave in all_leaves.iterrows():
                    status_color = {
                        "Approved": "🟢",
                        "Rejected": "🔴",
                        "Pending": "🟡"
                    }.get(leave['status'], "⚪")
                    
                    with st.expander(f"{status_color} {leave['name']} - {leave['start_date']} to {leave['end_date']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Employee:** {leave['name']}")
                            st.markdown(f"**Type:** {leave['leave_type']}")
                            st.markdown(f"**Reason:** {leave['reason']}")
                        with col2:
                            st.markdown(f"**Status:** {leave['status']}")
                            st.markdown(f"**Admin Note:** {leave['admin_approval'] or 'None'}")
                            st.markdown(f"**Verification:** {leave['employee_verification'] or 'Pending'}")
                        
                        st.markdown(f"**Request Date:** {leave['created_at']}")
                
                # Download option
                csv = all_leaves.to_csv(index=False)
                st.download_button(
                    label="Download Leave History",
                    data=csv,
                    file_name="leave_history.csv",
                    mime="text/csv"
                )
            else:
                st.info("No leave requests found for the selected filters")


    elif menu == "Attendance Management":
        st.header("Attendance Management")

        tab1, tab2 = st.tabs(["View Attendance", "Attendance Summary"])

        with tab1:
            st.subheader("View Attendance Records")

            # Filters
            col1, col2, col3 = st.columns(3)

            with col1:
                start_date = st.date_input("From", value=datetime.now() - timedelta(days=7))
            with col2:
                end_date = st.date_input("To", value=datetime.now())
            with col3:
                filter_by = st.selectbox("Filter By", ["All Employees", "Department", "Individual"])

            if filter_by == "Department":
                # Get unique departments
                conn = sqlite3.connect('attendance_system.db')
                c = conn.cursor()
                c.execute("SELECT DISTINCT department FROM users WHERE department IS NOT NULL")
                departments = [dept[0] for dept in c.fetchall()]
                conn.close()

                selected_department = st.selectbox("Select Department", departments)

                # Get attendance with department filter
                if start_date > end_date:
                    st.error("End date must be after start date")
                else:
                    conn = sqlite3.connect('attendance_system.db')
                    query = f"""
                    SELECT u.name, a.date, a.check_in, a.check_out, a.work_hours, a.status, a.verification_method
                    FROM attendance a
                    JOIN users u ON a.user_id = u.id
                    WHERE a.date BETWEEN ? AND ? AND u.department = ?
                    ORDER BY a.date DESC, u.name
                    """
                    attendance_df = pd.read_sql_query(query, conn, params=(
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d"),
                        selected_department
                    ))
                    conn.close()

                    if not attendance_df.empty:
                        st.dataframe(attendance_df, use_container_width=True)

                        # Download option
                        csv = attendance_df.to_csv(index=False)
                        st.download_button(
                            label="Download Report",
                            data=csv,
                            file_name=f"attendance_{selected_department}_{start_date}_to_{end_date}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No attendance records found for the selected criteria")

            elif filter_by == "Individual":
                # Get all employees
                users_df = get_all_users()
                employees = users_df[users_df['role'] == 'employee']

                if not employees.empty:
                    selected_employee = st.selectbox("Select Employee", employees['name'].tolist())
                    selected_user_id = employees[employees['name'] == selected_employee]['id'].iloc[0]

                    # Get attendance for selected employee
                    if start_date > end_date:
                        st.error("End date must be after start date")
                    else:
                        attendance_df = get_user_attendance(
                            selected_user_id,
                            start_date.strftime("%Y-%m-%d"),
                            end_date.strftime("%Y-%m-%d")
                        )

                        if not attendance_df.empty:
                            st.dataframe(attendance_df, use_container_width=True)

                            # Download option
                            csv = attendance_df.to_csv(index=False)
                            st.download_button(
                                label="Download Report",
                                data=csv,
                                file_name=f"attendance_{selected_employee}_{start_date}_to_{end_date}.csv",
                                mime="text/csv"
                            )
                        else:
                            st.info("No attendance records found for the selected employee")
                else:
                    st.info("No employees found")

            else:  # All employees
                if start_date > end_date:
                    st.error("End date must be after start date")
                else:
                    attendance_df = get_all_attendance(
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d")
                    )

                    if not attendance_df.empty:
                        st.dataframe(attendance_df, use_container_width=True)

                        # Download option
                        csv = attendance_df.to_csv(index=False)
                        st.download_button(
                            label="Download Report",
                            data=csv,
                            file_name=f"attendance_all_{start_date}_to_{end_date}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No attendance records found for the selected date range")

        with tab2:
            st.subheader("Attendance Summary")

            # Select month and year
            col1, col2 = st.columns(2)

            with col1:
                selected_month = st.selectbox("Month", [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ])
                month_num = {
                    "January": 1, "February": 2, "March": 3, "April": 4,
                    "May": 5, "June": 6, "July": 7, "August": 8,
                    "September": 9, "October": 10, "November": 11, "December": 12
                }[selected_month]

            with col2:
                current_year = datetime.now().year
                selected_year = st.selectbox("Year", range(current_year - 2, current_year + 1), index=2)

            # Generate report
            attendance_summary = generate_attendance_report(month_num, selected_year)

            if not attendance_summary.empty:
                st.dataframe(attendance_summary, use_container_width=True)

                # Download option
                csv = attendance_summary.to_csv(index=False)
                st.download_button(
                    label="Download Summary",
                    data=csv,
                    file_name=f"attendance_summary_{selected_month}_{selected_year}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No attendance data found for the selected month and year")
            
    elif menu == "Reports":
        st.subheader("All Daily Reports")

        # Filters: Date range, Project, and Employee search
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            start_date = st.date_input("From", value=datetime.now() - timedelta(days=30), key="reports_start")
        with col2:
            end_date = st.date_input("To", value=datetime.now(), key="reports_end")
        with col3:

            conn = sqlite3.connect("attendance_system.db")
            c = conn.cursor()

            # Fetch all project values (comma-separated) from daily_reports
            c.execute("SELECT project FROM daily_reports")
            projects = c.fetchall()
            conn.close()

            # Extract individual project names from comma-separated values
            project_list = sorted(set(
                p.strip() for row in projects for p in row[0].split(",") if p.strip()
            ))

            # Ensure 'General' is included if not already
            if "General" not in project_list:
                project_list.append("General")

            # Multiselect filter
            selected_projects = st.multiselect("Filter by Project(s)", options=project_list)
        with col4:
            search_emp = st.text_input("Search by Employee Name or ID")

        # Validate date range
        if start_date > end_date:
            st.error("⚠️ End date must be after start date")
        else:
            # Build SQL query
            conn = sqlite3.connect("attendance_system.db")
            query = (
                "SELECT u.id AS EmployeeID, u.name AS Employee, r.date AS Date, r.project AS Project,"
                " r.activities AS Activities, r.achievements AS Achievements, r.challenges AS Challenges"
                " FROM daily_reports r"
                " JOIN users u ON r.user_id = u.id"
                " WHERE r.date BETWEEN ? AND ?"
            )
            params = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]

            # Apply project filter
            if selected_projects:
                like_conditions = " OR ".join(["r.project LIKE ?"] * len(selected_projects))
                query += f" AND ({like_conditions})"
                params.extend([f"%{p}%" for p in selected_projects])


            # Apply employee search
            if search_emp:
                # search_emp could be name or ID
                query += " AND (u.name LIKE ? OR u.id = ?)"
                params.append(f"%{search_emp}%")
                # If search_emp is not numeric, id filter won't match
                try:
                    params.append(int(search_emp))
                except ValueError:
                    params.append(-1)

            query += " ORDER BY r.date DESC, u.name"

            # Execute and fetch
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            # Display or inform
            if df.empty:
                st.info("No reports found for the selected filters.")
            else:
                st.dataframe(df, use_container_width=True)

                # Download as CSV
                csv = df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Reports as CSV",
                    data=csv,
                    file_name=f"daily_reports_{start_date}_to_{end_date}.csv",
                    mime="text/csv"
                )

    elif menu == "Project Reports":
            st.header("Project Reports")

            projects = get_projects()

            if projects:
                df = pd.DataFrame(projects, columns=[
                    "ID", "Name", "Description", "Link", "Members", "Deadline", "Total Hours", "Status"
                ])
                st.dataframe(df, use_container_width=True)

                # Download button
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download Project Report",
                    data=csv,
                    file_name="sales_project_report.csv",
                    mime="text/csv"
                )
            else:
                st.info("No project reports found.")
  
        
    
    elif menu == "Salary Management":
        st.header("Salary Management")
        
        tab1, tab2 = st.tabs(["Process Salary", "Salary History"])
        
        with tab1:
            st.subheader("Process Monthly Salary")
            
            # Select month and year
            col1, col2 = st.columns(2)
            
            with col1:
                selected_month = st.selectbox("Month", [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ], key="process_month")
                month_num = {
                    "January": 1, "February": 2, "March": 3, "April": 4,
                    "May": 5, "June": 6, "July": 7, "August": 8,
                    "September": 9, "October": 10, "November": 11, "December": 12
                }[selected_month]
            
            with col2:
                current_year = datetime.now().year
                selected_year = st.selectbox("Year", range(current_year-2, current_year+1), index=2, key="process_year")
            
            # Get all employees
            users_df = get_all_users()
            employees = users_df[users_df['role'] == 'employee']
            
            # Add search box
            search_name = st.text_input("Search Employee by Name").lower()
            
            # Add department filter
            department_filter = st.selectbox("Filter by Department", ["All"] + list(employees['department'].unique()))

            # Filter employees by search input and department filter
            if department_filter != "All":
                filtered_employees = employees[
                    employees['name'].str.lower().str.contains(search_name) &
                    (employees['department'] == department_filter)
                ]
            else:
                filtered_employees = employees[employees['name'].str.lower().str.contains(search_name)]

            if not filtered_employees.empty:
                # Table-style display with editable fields
                salary_data = []
                st.markdown("### 🧾 Employee Salary List")

                for idx, employee in filtered_employees.iterrows():
                    employee_id = employee['id']
                    employee_name = employee['name']

                    # Attendance Summary
                    summary = get_monthly_attendance_summary(employee_id, month_num, selected_year)
                    present_days = summary.get('present_days', 0)
                    work_hours = summary.get('work_hours', 0)

                    # Check existing salary
                    conn = sqlite3.connect('attendance_system.db')
                    c = conn.cursor()
                    c.execute("""
                        SELECT base_salary, bonus, deductions, total_salary, payment_status
                        FROM salary WHERE user_id = ? AND month = ? AND year = ?
                    """, (employee_id, month_num, selected_year))
                    existing_salary = c.fetchone()
                    conn.close()

                    # Show as horizontal table
                    with st.expander(f"💼 {employee_name}"):
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.write("**Present Days:**", present_days)
                            base_salary = st.number_input("Base Salary (₹)", value=existing_salary[0] if existing_salary else 0.0,
                                                    step=100.0, key=f"base_{employee_id}")

                        with col2:
                            st.write("**Work Hours:**", f"{work_hours:.2f}")
                            bonus = st.number_input("Bonus (₹)", value=existing_salary[1] if existing_salary else 0.0,
                                                step=10.0, key=f"bonus_{employee_id}")

                        with col3:
                            st.write("**Total Salary (₹):**")
                            deductions = st.number_input("Deductions (₹)", value=existing_salary[2] if existing_salary else 0.0,
                                                        step=10.0, key=f"deduct_{employee_id}")
                            total_salary = base_salary + bonus - deductions
                            st.success(f"₹ {total_salary:.2f}")

                        payment_status = st.selectbox("Payment Status", ["Pending", "Paid"],
                                                    index=0 if not existing_salary or existing_salary[4] == "Pending" else 1,
                                                    key=f"status_{employee_id}")

                        if st.button(f"Save for {employee_name}", key=f"save_{employee_id}"):
                            save_salary_info(employee_id, month_num, selected_year, base_salary, bonus, deductions, total_salary, payment_status)
                            st.success(f"Saved for {employee_name}")

                        salary_data.append({
                            'Employee ID': employee_id,
                            'Employee Name': employee_name,
                            'Base Salary': base_salary,
                            'Bonus': bonus,
                            'Deductions': deductions,
                            'Total Salary': total_salary,
                            'Status': payment_status
                        })
            else:
                st.warning("No matching employees found.")
        with tab2:

            # Streamlit UI section
            st.subheader("Salary History")

            # Filters
            col1, col2 = st.columns(2)  # Ensure this is not indented inside another block

            with col1:
                month_filter = st.selectbox("Month", ["All"] + [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ], key="month_select")

            with col2:
                current_year = datetime.now().year
                year_filter = st.selectbox("Year", ["All"] + list(range(current_year - 2, current_year + 1)), key="year_select")

            # Get salary history
            salary_history = get_salary_history(
                month_filter if month_filter != "All" else None,
                year_filter if year_filter != "All" else None
            )

            # Search by employee name
            search_name = st.text_input("Search Employee by Name", key="search_name")

            # Add a search button to trigger the filtering
            search_button = st.button("Search", key="search_button")

            # Convert year to string to avoid comma formatting
            if not salary_history.empty:
                salary_history['year'] = salary_history['year'].astype(str)

                # Apply filters only if the search button is pressed
                if search_button and search_name:
                    salary_history = salary_history[salary_history['employee_name'].str.contains(search_name, case=False)]

                if not salary_history.empty:
                    st.dataframe(salary_history, use_container_width=True)

                    # Download CSV
                    csv = salary_history.to_csv(index=False)
                    st.download_button(
                        label="Download Salary History",
                        data=csv,
                        file_name=f"salary_history_{month_filter}_{year_filter}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No records match your search.")
            else:
                st.info("No salary history found for the selected filters")

    elif menu == "Settings":
        st.header("System Settings")

        tab1, tab2 = st.tabs(["General Settings", "Backup/Restore"])

        with tab1:
            st.subheader("General Settings")

            # Working hours settings
            st.write("#### Working Hours")
            col1, col2 = st.columns(2)

            with col1:
                standard_start = st.time_input("Standard Work Start Time",
                                               value=datetime.strptime("09:00", "%H:%M").time())
            with col2:
                standard_end = st.time_input("Standard Work End Time", value=datetime.strptime("17:00", "%H:%M").time())

            # Late arrival threshold
            late_threshold = st.number_input("Late Arrival Threshold (minutes)", value=15, min_value=0, max_value=60)

            # Save settings
            if st.button("Save Settings"):
                # Save to database or config file
                conn = sqlite3.connect('attendance_system.db')
                c = conn.cursor()

                # Check if settings table exists
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
                if not c.fetchone():
                    c.execute("""
                    CREATE TABLE settings (
                        id INTEGER PRIMARY KEY,
                        key TEXT UNIQUE,
                        value TEXT
                    )
                    """)

                # Save settings
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                          ("standard_start", standard_start.strftime("%H:%M")))
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                          ("standard_end", standard_end.strftime("%H:%M")))
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                          ("late_threshold", str(late_threshold)))

                conn.commit()
                conn.close()
                st.success("Settings saved successfully!")

        with tab2:
            st.subheader("Backup and Restore")

            # Backup database
            if st.button("Backup Database"):
                # Create backup
                backup_file = f"attendance_system_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

                # Copy database
                shutil.copy('attendance_system.db', backup_file)

                # Create download link
                with open(backup_file, 'rb') as f:
                    backup_data = f.read()

                st.download_button(
                    label="Download Backup File",
                    data=backup_data,
                    file_name=backup_file,
                    mime="application/octet-stream"
                )

                # Cleanup temp file
                os.remove(backup_file)

                st.success("Database backup created successfully!")

            # Restore database
            st.write("#### Restore Database")
            uploaded_file = st.file_uploader("Upload backup file", type=["db"])

            if uploaded_file is not None:
                # Confirm restoration
                st.warning("Restoring from backup will overwrite the current database. This cannot be undone.")
                if st.button("Restore Database"):
                    # Save uploaded file
                    with open('temp_restore.db', 'wb') as f:
                        f.write(uploaded_file.getbuffer())

                    # Verify it's a valid database
                    try:
                        conn = sqlite3.connect('temp_restore.db')
                        c = conn.cursor()
                        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = c.fetchall()
                        conn.close()

                        # Check if it contains required tables
                        required_tables = ['users', 'attendance', 'daily_reports', 'salary']
                        table_names = [table[0] for table in tables]
                        missing_tables = [table for table in required_tables if table not in table_names]

                        if missing_tables:
                            st.error(f"Invalid database backup. Missing tables: {', '.join(missing_tables)}")
                            os.remove('temp_restore.db')
                        else:
                            # Backup current database
                            backup_file = f"attendance_system_auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                            shutil.copy('attendance_system.db', backup_file)

                            # Replace with restored file
                            os.remove('attendance_system.db')
                            shutil.move('temp_restore.db', 'attendance_system.db')

                            st.success("Database restored successfully! Please restart the application.")
                            st.balloons()
                    except Exception as e:
                        st.error(f"Error restoring database: {str(e)}")
                        # Clean up
                        if os.path.exists('temp_restore.db'):
                            os.remove('temp_restore.db')
def sales_dashboard():
    st.title("Sales Dashboard")

    # Sidebar menu (like admin dashboard)
    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "All Projects", "Add Project", "Edit Project"],
        index=["Home", "All Projects", "Add Project", "Edit Project"].index(
            st.session_state.get("sales_tab", "Home")
        )
    )
    st.session_state.sales_tab = menu

    if st.sidebar.button("Logout"):
        logout()
    

    if menu == "Home":
        st.header("Dashboard Overview")
        projects = get_projects()
        total = len(projects)
        ongoing = len([p for p in projects if p[7] == "Ongoing"])
        finished = len([p for p in projects if p[7] == "Finished"])
        not_assigned = len([p for p in projects if p[7] == "Not Assigned"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Projects", total)
        col2.metric("Ongoing", ongoing)
        col3.metric("Finished", finished)
        col4.metric("Not Assigned", not_assigned)

    elif menu == "All Projects":
        display_project_directory("All Projects")

    elif menu == "Add Project":
        st.header("Add New Project")
        with st.form("add_project_form"):
            name = st.text_input("Project Name")
            desc = st.text_area("Description")
            link = st.text_input("Project Link")
            members = st.multiselect("Assign Members", get_employees())
            deadline = st.date_input("Deadline")
            hours = st.number_input("Total Hours", min_value=0.0)
            submit = st.form_submit_button("Add Project")

        if submit:
            add_project(name, desc, link, members, deadline.strftime("%Y-%m-%d"), hours)
            st.success("✅ Project added successfully!")

    elif menu == "Edit Project":
        st.header("Edit Project")
        projects = get_projects()
        project_dict = {f"{p[0]} - {p[1]}": p for p in projects}
        selected = st.selectbox("Select Project", list(project_dict.keys()))
        project = project_dict[selected]

        with st.form("edit_project_form"):
            name = st.text_input("Project Name", value=project[1])
            desc = st.text_area("Description", value=project[2])
            link = st.text_input("Project Link", value=project[3])

            all_employees = get_employees()
            default_members = [m.strip() for m in project[4].split(",") if m.strip() in all_employees]
            members = st.multiselect("Assign Members", all_employees, default=default_members)

            deadline = st.date_input("Deadline", value=datetime.strptime(project[5], "%Y-%m-%d"))
            hours = st.number_input("Total Hours", value=project[6])
            status = st.selectbox("Status", ["Not Assigned", "Ongoing", "Finished"], index=["Not Assigned", "Ongoing", "Finished"].index(project[7]))

            update = st.form_submit_button("Update Project")

        if update:
            update_project(project[0], name, desc, link, members, deadline.strftime("%Y-%m-%d"), hours, status)
            st.success("✅ Project updated successfully!")


# Main function to determine which page to show
def main():
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if 'user_id' not in st.session_state:
        st.session_state.user_id = None

    if 'user_role' not in st.session_state:
        st.session_state.user_role = None

    if 'face_encodings_db' not in st.session_state:
        st.session_state.face_encodings_db = load_face_encodings()

    if 'is_sales_login' not in st.session_state:
        st.session_state.is_sales_login = False


    # Initialize database
    init_db()

    if not st.session_state.authenticated:
        login_page()
    else:
        if st.session_state.get('is_sales_login', False):
            sales_dashboard()
        else:
            if st.session_state.user_role == 'admin':
                admin_dashboard()
            else:
                employee_dashboard()

def get_user_role(user_id):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def delete_user(user_id):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
def check_liveness(image_array):
    # Basic liveness check using eye blink detection
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
    gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
    eyes = eye_cascade.detectMultiScale(gray, 1.1, 4)
    return len(eyes) >= 2  # At least two eyes detected
def detect_liveness(image_array):
    """Enhanced liveness detection using head orientation and eye blink"""
    img_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(img_rgb)
    
    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            # Detect head orientation
            direction = detect_direction(face_landmarks.landmark, image_array.shape[1], image_array.shape[0])
            
            # Eye blink detection
            left_eye = [face_landmarks.landmark[i] for i in [33, 160, 158, 133]]
            right_eye = [face_landmarks.landmark[i] for i in [362, 385, 387, 263]]
            
            if is_blinking(left_eye) or is_blinking(right_eye):
                return True, direction
            
    return False, None
# Update your registration page with these features
def biometric_registration():
    st.subheader("Face Registration")
    
    # Capture multiple angles
    if st.button("Start Face Registration"):
        success = register_face(st.session_state.user_id)
        if success:
            st.success("Registered face with multiple angles!")
        else:
            st.error("Registration failed")
def detect_direction(landmarks, width, height):
    """Detect head orientation using facial landmarks"""
    nose_tip = landmarks[1]
    left_eye = landmarks[33]
    right_eye = landmarks[263]

    nose_x = nose_tip.x * width
    eye_center_x = (left_eye.x + right_eye.x) * width / 2
    
    if nose_x < eye_center_x - 30:
        return 'left'
    elif nose_x > eye_center_x + 30:
        return 'right'
    return 'center'
def face_login():
    st.write("Look at the camera")
    img_file = st.camera_input("Real-time verification")
    
    if img_file:
        image = Image.open(img_file)
        image_array = np.array(image)
        
        if verify_face(image_array, st.session_state.user_id):
            st.success("Biometric verification passed!")
        else:
            st.error("Verification failed")
def is_blinking(eye_points):
    """Detect eye blink using EAR (Eye Aspect Ratio)"""
    vertical = [
        math.dist((eye_points[0].x, eye_points[0].y), 
        (eye_points[1].x, eye_points[1].y)),
        math.dist((eye_points[2].x, eye_points[2].y), 
        (eye_points[3].x, eye_points[3].y))
    ]
    horizontal = math.dist(
        (eye_points[0].x, eye_points[0].y),
        (eye_points[3].x, eye_points[3].y)
    )
    ear = (vertical[0] + vertical[1]) / (2.0 * horizontal)
    return ear < 0.2  # Threshold for blink detection

def display_user_directory(title, role_filter):
    st.header(title)

    # Get users based on role
    users_df = get_all_users()
    users = users_df[users_df['role'] == role_filter]

    if not users.empty:
        col1, col2 = st.columns(2)

        with col1:
            department_filter = st.selectbox(
                "Filter by Department",
                ["All Departments"] + sorted(users['department'].dropna().unique().tolist()),
                key=f"{role_filter}_dept"
            )
        with col2:
            search_query = st.text_input("Search by Name", key=f"{role_filter}_search")

        if department_filter != "All Departments":
            users = users[users['department'] == department_filter]
        if search_query:
            users = users[users['name'].str.contains(search_query, case=False)]

        st.subheader("User Cards")
        cols = st.columns(3)
        for idx, (_, user) in enumerate(users.iterrows()):
            with cols[idx % 3]:
                with st.container():
                    conn = sqlite3.connect('attendance_system.db')
                    c = conn.cursor()
                    c.execute("SELECT photo FROM users WHERE id = ?", (user['id'],))
                    photo_blob = c.fetchone()[0]
                    conn.close()

                    if photo_blob:
                        st.image(photo_blob, width=150)
                    else:
                        st.image("https://via.placeholder.com/150?text=No+Photo", width=150)

                    st.markdown(f"**{user['name']}**")
                    st.markdown(f"*{user['department']}*")

                    with st.expander("View Details"):
                        st.markdown(f"**Email:** {user['email']}")
                        st.markdown(f"**Phone:** {user['phone']}")
                        st.markdown(f"**Join Date:** {user['join_date']}")

                        salary_df = get_user_salary(user['id'])
                        if not salary_df.empty:
                            latest_salary = salary_df.iloc[0]
                            st.markdown("---")
                            st.markdown("**Salary Info**")
                            st.markdown(f"**Total Salary:** ₹{latest_salary['total_salary']:.2f}")
                            st.markdown(f"**Status:** {latest_salary['payment_status']}")
    else:
        st.info("No users found.")

def create_leave_request(user_id, start_date, end_date, leave_type, reason):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("""
    INSERT INTO leave_requests (user_id, start_date, end_date, leave_type, reason)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, start_date, end_date, leave_type, reason))
    conn.commit()
    conn.close()

def get_employee_leave_requests(user_id):
    conn = sqlite3.connect('attendance_system.db')
    query = """
    SELECT id, start_date, end_date, leave_type, reason, status, admin_approval, employee_verification
    FROM leave_requests
    WHERE user_id = ?
    ORDER BY created_at DESC
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def get_pending_leave_requests():
    conn = sqlite3.connect('attendance_system.db')
    query = """
    SELECT 
        lr.id,
        u.name,
        lr.start_date,
        lr.end_date,
        lr.leave_type,
        lr.reason,
        lr.created_at
    FROM leave_requests lr
    JOIN users u ON lr.user_id = u.id
    WHERE lr.status = 'Pending'
    ORDER BY lr.created_at DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def update_leave_status(leave_id, status, approval_note):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("""
    UPDATE leave_requests 
    SET status = ?, admin_approval = ?
    WHERE id = ?
    """, (status, approval_note, leave_id))
    conn.commit()
    conn.close()

def verify_leave_request(leave_id):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("""
    UPDATE leave_requests 
    SET employee_verification = 'Verified'
    WHERE id = ?
    """, (leave_id,))
    conn.commit()
    conn.close()

# Get employees from user table
def get_employees():
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE role='employee'")
    employees = [row[0] for row in c.fetchall()]
    conn.close()
    return employees

# Add a new project
def add_project(name, desc, link, members, deadline, hours):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    members_str = ", ".join(members)
    status = "Not Assigned" if not members else "Ongoing"
    c.execute("INSERT INTO projects (name, description, link, members, deadline, total_hours, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (name, desc, link, members_str, deadline, hours, status))
    conn.commit()
    conn.close()

# Fetch all projects
def get_projects():
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("SELECT * FROM projects")
    rows = c.fetchall()
    conn.close()
    return rows

# Update a project
def update_project(project_id, name, desc, link, members, deadline, hours, status):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    members_str = ", ".join(members)
    c.execute("""UPDATE projects SET name=?, description=?, link=?, members=?, deadline=?, total_hours=?, status=? WHERE id=?""",
              (name, desc, link, members_str, deadline, hours, status, project_id))
    conn.commit()
    conn.close()

def display_project_directory(title):
    st.header(title)

    # Fetch all projects
    projects = get_projects()
    if not projects:
        st.info("No projects available.")
        return

    # Convert to DataFrame for easier filtering (optional but cleaner)
    df = pd.DataFrame(projects, columns=[
        "id", "name", "description", "link", "members", "deadline", "hours", "status"
    ])

    # 🎯 Filter and Search Controls
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All"] + sorted(df["status"].unique().tolist()))
    with col2:
        search_query = st.text_input("Search by Project Name")

    # 🧠 Apply Filters
    if status_filter != "All":
        df = df[df["status"] == status_filter]
    if search_query:
        df = df[df["name"].str.contains(search_query, case=False)]

    # 🔁 Display Projects in 3 Columns
    st.subheader("Projects")
    cols = st.columns(3)
    for idx, row in df.iterrows():
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"""
                    <div style='
                        background-color: #f8f9fa;
                        padding: 15px;
                        border-radius: 10px;
                        box-shadow: 0 0 10px rgba(0,0,0,0.05);
                        margin-bottom: 15px;
                    '>
                        <h5>{row['name']}</h5>
                        <p><strong>Members:</strong> {row['members']}</p>
                        <p><strong>Deadline:</strong> {row['deadline']}</p>
                        <p><strong>Status:</strong> 
                            <span style='color: {"green" if row["status"]=="Finished" else "orange" if row["status"]=="Ongoing" else "red"}'>
                                {row["status"]}
                            </span>
                        </p>
                        <a href="{row['link']}" target="_blank">🔗 Project Link</a>
                    </div>
                """, unsafe_allow_html=True)
def add_user(username, password, role, name, email, phone, department, join_date, photo_bytes=None):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    try:
        # Validate phone number format
        if not phone.isdigit() or len(phone) != 10:
            return False, None, "Invalid phone number format (must be 10 digits)"
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        formatted_join_date = join_date.strftime("%Y-%m-%d") if isinstance(join_date, datetime) else join_date
        
        c.execute("""
            INSERT INTO users (username, password, role, name, email, phone, department, join_date, photo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, hashed_password, role, name, email, phone, department, formatted_join_date, photo_bytes))
        
        user_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, user_id, "User added successfully"
    except sqlite3.IntegrityError:
        conn.close()
        return False, None, "Username already exists"
    except Exception as e:
        conn.close()
        return False, None, f"Error adding user: {str(e)}"
def get_all_leave_requests(status=None, start_date=None, end_date=None):
    conn = sqlite3.connect('attendance_system.db')
    query = """
    SELECT 
        lr.id,
        u.name,
        lr.start_date,
        lr.end_date,
        lr.leave_type,
        lr.reason,
        lr.status,
        lr.admin_approval,
        lr.employee_verification,
        lr.created_at
    FROM leave_requests lr
    JOIN users u ON lr.user_id = u.id
    WHERE 1=1
    """
    
    params = []
    
    if status and status != "All":
        query += " AND lr.status = ?"
        params.append(status)
    
    if start_date and end_date:
        query += " AND lr.created_at BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    query += " ORDER BY lr.created_at DESC"
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_project_list():
    conn = sqlite3.connect("attendance_system.db")
    c = conn.cursor()
    c.execute("SELECT name FROM projects")
    projects = [row[0] for row in c.fetchall()]
    conn.close()
    projects.append("General")
    return projects

# Run the application
if __name__ == "__main__":
    main()