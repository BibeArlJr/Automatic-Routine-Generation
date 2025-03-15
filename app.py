from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, session
from flask_mail import Mail, Message
from pymongo import MongoClient, errors
import pandas as pd
from bson import ObjectId  # Import to handle ObjectId
import random, traceback
from pymongo.database import Database
import itertools
from flask import Flask, request
import copy, random, re
from twilio.rest import Client
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask import make_response
from collections import defaultdict


app = Flask(__name__, static_folder='static')
app.config['SESSION_PERMANENT'] = True
app.secret_key = 'your_unique_secret_key'  # Use a strong random key


# Flask-Mail configuration (example for Gmail's SMTP server)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'bibekaryal717@gmail.com'  # Your email address
app.config['MAIL_PASSWORD'] = 'tgum rjoz gqnb onhv'         # Your email password or app-specific password
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)


# Twilio Credentials (replace with your own Twilio credentials)
TWILIO_ACCOUNT_SID = 'ACb01c1959644a84b93f30a62b22ffd924'
TWILIO_AUTH_TOKEN = 'ec0e71bc19aeafb6be4557a0001fcf51'
TWILIO_VERIFY_SERVICE_SID = 'VA2e656ce8b504e5ae179a26c9ccb20cac'  # Replace with your Verify Service SID

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# MongoDB connection
def connect_to_mongodb():
    try:
        client = MongoClient("mongodb+srv://major:project@majorproject.nrvy0xw.mongodb.net/")
        client.admin.command('ping')  # Test connection
        print("MongoDB connection successful.")
        print("Available collections after connection:", client['Project1'].list_collection_names())
        return client
    except errors.ServerSelectionTimeoutError as err:
        print("MongoDB connection failed:", err)
        return None

client = connect_to_mongodb()

db = client['Project1'] if client else None

# Faculty and Semester options
FACULTIES = ['Civil', 'Computer', 'Electronics', 'Electrical']
SEMESTERS = [str(i) for i in range(1, 9)]  # Semesters 1 to 8

# Send email verification code
@app.route('/send_code', methods=['POST'])
def send_code():
    email = request.json.get('email')
    if email:
        try:
            verification_code = str(random.randint(100000, 999999))  # Generate a 6-digit code
            msg = Message('Your Verification Code',
                          sender=app.config['MAIL_USERNAME'],
                          recipients=[email])
            msg.body = f"Your verification code is: {verification_code}"
            mail.send(msg)

            # Store the code for later verification
            session['verification_code'] = verification_code
            print(f"Verification code sent to: {email}")  # Log the recipient email
            return jsonify({'success': True}), 200
        except Exception as e:
            print(f"Error while sending verification code: {str(e)}")
            return jsonify({'success': False, 'message': 'Failed to send verification code.'}), 500
    return jsonify({'success': False, 'message': 'Invalid email address'}), 400

# Verify email code
@app.route('/verify_code', methods=['POST'])
def verify_code():
    code = request.json.get('code')
    entered_code = session.get('verification_code')

    if entered_code and code == entered_code:
        session.pop('verification_code')  # Clear code after successful verification
        return jsonify({'success': True, 'message': 'Code verified successfully'}), 200
    return jsonify({'success': False, 'message': 'Invalid verification code'}), 400

# Route to handle sending email
@app.route('/send_message', methods=['POST'])
def send_message():
    if request.method == 'POST':
        user_email = request.form['email']
        user_message = request.form['message']

        # Compose the email
        msg = Message('New Message from Website', 
                      sender=user_email, 
                      recipients=['bibekaryal717@gmail.com'])  # Your receiving email
        msg.body = f"Message from {user_email}:\n\n{user_message}"

        # Send the email
        try:
            mail.send(msg)
            flash('Message sent successfully!', 'success')
        except Exception as e:
            flash(f"Error sending message: {e}", 'danger')

        return redirect(url_for('index'))  # Redirect back to the homepage or any other page


@app.route('/get_subjects', methods=['GET'])
def get_subjects():
    """Fetches elective subjects for a given faculty and semester."""
    
    faculty = request.args.get('faculty')
    semester = request.args.get('semester')

    if not faculty or not semester:
        return jsonify({"error": "Missing faculty or semester"}), 400

    try:
        semester = int(semester)  # Ensure semester is an integer
    except ValueError:
        return jsonify({"error": "Invalid semester value"}), 400

    # Fetch elective subjects for the given faculty and semester
    elective_subjects = list(db['subjects'].find(
    {"Faculty": faculty, "Semester": semester, "Type": "Elective"},  
    {"_id": 0, "Code": 1, "Name": 1, "Courses": 1}  # Fetch only necessary fields
))

    # Sort the courses inside each elective subject alphabetically
    for subject in elective_subjects:
        if "Courses" in subject and isinstance(subject["Courses"], list):
            subject["Courses"].sort(key=lambda x: x.get("Name", "").lower())  # Sort courses alphabetically

    print(f"Filtered Elective Subjects: {elective_subjects}")  # Debugging log

    return jsonify(elective_subjects)


lab_details_collection = db["Lab Details"]
timetables_collection = db["timetables"]
teachers_collection = db["teachers"]
subjects_collection = db["subjects"]
teacherRoutines = db["teacherRoutines"]
teacher_routines_collection = db["teacherRoutines"]


def add_lab_detail(subject_code, subject_name, lab_room, teacher, time_slot, day):
    """
    Inserts a lab detail document into the 'Lab Details' collection.
    
    Prevents overlapping lab room assignments.
    
    Parameters:
      - subject_code: (str) e.g., "CT 753"
      - subject_name: (str) e.g., "Simulation and Modelling"
      - lab_room: (str) e.g., "Software Lab"
      - teacher: (list) [{"name": "Dr. Kishore Adhikari", "designation": "Teacher", "workload": 4}]
      - time_slot: (str) e.g., "11:00 AM - 11:45 AM"
      - day: (str) e.g., "Monday"
    """

    # Check if lab room is occupied at the given time slot
    existing_lab = lab_details_collection.find_one({
        "Lab_Room": lab_room,
        "Time_Slot": time_slot,
        "Day": day,
    })

    if existing_lab:
        print(f"⚠️ Lab {lab_room} is already occupied on {day} at {time_slot}.")
        return None  # Return None if lab is unavailable

    # Insert lab detail
    lab_detail = {
        "Subject_Code": subject_code,
        "Subject_Name": subject_name,
        "Lab_Room": lab_room,
        "Teacher": teacher,
        "Time_Slot": time_slot,
        "Day": day
    }

    result = lab_details_collection.insert_one(lab_detail)
    print("✅ Inserted Lab Detail with ID:", result.inserted_id)
    return result.inserted_id  # Return inserted document ID




def find_available_teacher(subject_code, day, time_slot, current_tt, semester):
    teachers = list(db["teachers"].find({"Course_Code": subject_code}))
    if not teachers:
        print(f"⚠️ No teachers found for {subject_code}")
        return None

    teachers.sort(key=lambda t: 0 if t["type"].lower() == "part time" else 1)

    for teacher in teachers:
        if not check_teacher_workload_and_availability(teacher, day, time_slot):
            continue
        print(f"✅ Assigned {teacher['name']} to {subject_code} on {day} at {time_slot}")
        return teacher  # ✅ Found an available teacher

    print(f"⚠️ No available teacher for {subject_code} on {day} at {time_slot}")
    return None



def get_lab_details():
    """
    Fetch all lab details from the database.
    Returns: List of lab records.
    """
    labs = list(lab_details_collection.find({}, {"_id": 0}))  # Exclude ObjectId
    return labs

@app.route('/get_lab_details', methods=['GET'])
def fetch_lab_details():
    """
    API endpoint to fetch lab details.
    """
    labs = get_lab_details()
    return jsonify(labs)  # Return JSON response

@app.route("/manage_lab_details")
def manage_lab_details():
    """
    Fetch lab details from the database and render the table in HTML.
    """
    user = session.get('user')
    user_role = session.get('user_role')
    faculty_name = session.get('faculty_name')
    lab_details = list(db["Lab Details"].find({}, {"_id": 0}))  # Exclude ObjectId for display
    return render_template("lab_details.html", lab_details=lab_details, user=user, user_role=user_role, faculty_name=faculty_name)


def find_lab_teachers(teachers, subject, required_teachers):
    """
    Finds available teachers for lab classes.
    Prioritizes:
    1. Teachers who also teach theory classes of the same subject
    2. Part-time teachers who teach the subject
    3. Any available teacher who teaches the subject
    """
    available_teachers = [t for t in teachers if subject["Code"] in t.get("Course_Code", [])]

    # Prioritize teachers already assigned to the subject's theory
    theory_teachers = [t for t in available_teachers if "theory" in t.get("type", "").lower()]
    part_time_teachers = [t for t in available_teachers if "part time" in t.get("type", "").lower()]

    if len(theory_teachers) >= required_teachers:
        return theory_teachers[:required_teachers]
    elif len(theory_teachers) + len(part_time_teachers) >= required_teachers:
        return (theory_teachers + part_time_teachers)[:required_teachers]
    else:
        return available_teachers[:required_teachers]  # Assign any available teacher


LAB_CAPACITY = {
    "Hardware": 2,
    "Software": 5,
    "English Lab": 1,
    "Thermo Lab": 1,
    "Workshop": 1,
    "Chemistry Lab": 1,
    "Physic Lab": 1,
    "Drawing": 2,
    "Electrical Lab": 2
}


def store_teacher_routine(teacher_name, day, time_slot, subject_name):
    """Stores teacher routine in the 'teacherRoutines' collection."""
    try:
        result = db["teacherRoutines"].insert_one({
            "Teacher_Name": teacher_name,
            "Day": day,
            "Time_Slot": time_slot,
            "Subject": subject_name
        })
        if result.acknowledged:
            print(f"✅ Successfully stored routine for {teacher_name} on {day} at {time_slot} for subject {subject_name}.")
        else:
            print(f"❌ Failed to insert routine for {teacher_name} on {day}.")
    except Exception as e:
        print(f"❌ Error inserting teacher routine: {e}")



def store_lab_detail(subject_code, subject_name, lab_room, teacher_name, day, time_slot, faculty, semester):
    """
    Stores lab details in the 'Lab Details' collection with faculty and semester information.
    """
    lab_entry = {
        "Faculty": faculty,  # ✅ Add faculty field
        "Semester": semester,  # ✅ Add semester field
        "Subject_Code": subject_code,
        "Subject_Name": subject_name,
        "Lab_Room": lab_room,
        "Teacher": teacher_name,
        "Day": day,
        "Time_Slot": time_slot  # ✅ Match time slot to period format
    }

    existing_lab = db["Lab Details"].find_one({
        "Faculty": faculty,
        "Semester": semester,
        "Subject_Code": subject_code,
        "Day": day,
        "Time_Slot": time_slot
    })

    if existing_lab:
        print(f"⚠️ Lab for {subject_name} already exists at {time_slot} on {day}. Skipping duplicate entry.")
    else:
        db["Lab Details"].insert_one(lab_entry)
        print(f"✅ Lab session stored for {subject_name} at {time_slot} on {day}")



def is_teacher_assigned_to_other_semester(teacher_name, day, time_slot):
    """
    Checks if a teacher is already assigned to a different semester on the same day and time slot.
    """
    existing_assignment = db["teacherRoutines"].find_one({
        "Teacher_Name": teacher_name,
        "Day": day,
        "Time_Slot": time_slot
    })
    
    return existing_assignment is not None  # Returns True if teacher is already assigned


def get_college_days(days_per_week):
    """Returns the correct days of operation based on `days_per_week`."""
    week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return week_days[:days_per_week]


from datetime import datetime
from datetime import datetime
from pymongo.database import Database

from datetime import datetime
from pymongo.database import Database

def convert_24_to_12(time_range):
    """Converts 24-hour format (HH:MM-HH:MM) to 12-hour AM/PM format, handling single-digit hour cases."""
    try:
        start, end = time_range.split("-")
        
        # Ensure two-digit hours (prepend zero if needed)
        if len(start.strip().split(":")[0]) == 1:
            start = "0" + start.strip()
        if len(end.strip().split(":")[0]) == 1:
            end = "0" + end.strip()
        
        start_12 = datetime.strptime(start, "%H:%M").strftime("%I:%M %p")
        end_12 = datetime.strptime(end, "%H:%M").strftime("%I:%M %p")
        
        return f"{start_12} - {end_12}"
    except ValueError as e:
        print(f"❌ Incorrect format detected: {time_range} | Error: {e}")
        return None

def get_teacher_availability(teacher, day_name, start_time_str, end_time_str):
    """Returns the availability of a teacher on a given day."""
    if teacher.get("type") == "Full Time":
        return [f"{start_time_str} - {end_time_str}"]
    
    availability_data = teacher.get("availability", {})
    if not isinstance(availability_data, dict):
        print(f"❌ Invalid availability format for {teacher['name']}")
        return []
    
    raw_availability = availability_data.get(day_name, [])
    return list(filter(None, map(convert_24_to_12, raw_availability)))

def is_teacher_available(teacher_name, slot_time, day_name, db, start_time_str, end_time_str):
    """Checks if a teacher is available during the given slot."""
    teacher = db["teachers"].find_one({"name": teacher_name})
    if not teacher:
        print(f"   ❌ {teacher_name} not found in database.")
        return False
    
    day_availability = get_teacher_availability(teacher, day_name, start_time_str, end_time_str)
    slot_start, slot_end = map(str.strip, slot_time.split("-"))
    
    for time_range in day_availability:
        start, end = map(str.strip, time_range.split("-"))
        if start <= slot_start and slot_end <= end:
            return True
    return False



import random

def assign_theory_subjects(current_tt, subjects, teachers, semester, faculty, days_per_week, start_time_str, end_time_str, empty_slots, db, period_length, teachersRoutines):
    print("✅ Assigning Theory Subjects with Constraints...")
    timetable = current_tt["Timetable"]

    # ✅ Prioritize subjects with more required hours
    subjects.sort(key=lambda s: -((s.get("L", 0) + s.get("T", 0)) * 60 // period_length))

    # ✅ Shuffle subjects to ensure balanced distribution
    random.shuffle(subjects)

    # ✅ Filter subjects that need theory classes
    theory_subjects = [s for s in subjects if s.get("L", 0) > 0 or s.get("T", 0)]
    subject_day_count = {}  # Tracks subject slots per day
    unassigned_subjects = []  # Track subjects that could not be fully assigned

    day_subjects = {day["Day"]: set() for day in timetable}
    previous_day_subjects = set()  # Store assigned subjects on the previous day

    for subject in theory_subjects:

        subject_code = subject["Code"]
        required_hours = (subject.get("L", 0) + subject.get("T", 0)) * 60 // period_length
        assigned_hours = 0
        assigned_slots = []

        print(f"\n🔍 Processing Subject: {subject_code} | Required Hours: {required_hours}")

         # ✅ Get subjects that were NOT assigned on the previous day
        preferred_subjects = [s for s in theory_subjects if s["Code"] not in previous_day_subjects]

        # ✅ If all subjects were assigned on the previous day, allow any
        if not preferred_subjects:
            preferred_subjects = theory_subjects

        # ✅ Shuffle to avoid repetition patterns
        random.shuffle(preferred_subjects)
        
        for subject in preferred_subjects:
            subject_code = subject["Code"]
            required_hours = (subject.get("L", 0) + subject.get("T", 0)) * 60 // period_length
            assigned_hours = 0
            assigned_slots = []

            print(f"\n🔍 Processing Subject: {subject_code} | Required Hours: {required_hours}")

            # ✅ Filter teachers who can teach this subject
            subject_teachers = [t for t in teachers if subject_code in t.get("Course_Code", [])]

            if not subject_teachers:
                print(f"❌ No teachers found for {subject_code}. Attempting substitute assignment...")
                unassigned_subjects.append(subject)
                continue  # Move to next subject if no teachers found

            # ✅ Shuffle teachers for fairness
            random.shuffle(subject_teachers)

            # ✅ Sort teachers: Prioritize part-time teachers first, then those with lower assigned hours
            sorted_teachers = sorted(subject_teachers, key=lambda t: (t["type"] != "Part Time", len(t.get("availability", {}) or {})))

            successful_assignment = False

            # ✅ Step 1: Assign a **single teacher** if possible
            for teacher in sorted_teachers:
                teacher_assigned_hours = 0
                teacher_assigned_slots = []
                assigned_days = set()

                print(f"   🔎 Checking Teacher: {teacher['name']} ({teacher['type']})")

                for i in range(len(empty_slots) - 1):
                    day_idx, slot_idx, slot = empty_slots[i]
                    next_day_idx, next_slot_idx, next_slot = empty_slots[i + 1]

                    # ✅ Ensure consecutive slots are used
                    if next_day_idx != day_idx or next_slot_idx != slot_idx + 1:
                        continue

                    day_name = timetable[day_idx]["Day"]
                    slot_time = slot["Period"]
                    next_slot_time = next_slot["Period"]

                    # ✅ Restrict to max 2 slots per subject per day
                    if subject_day_count.get((subject_code, day_name), 0) >= 2:
                        continue  # Skip if 2 slots are already assigned

                    # ✅ Ensure full-time teachers are always available
                    if teacher["type"] == "Full Time":
                        teacher_available = True
                    else:
                        teacher_available = is_teacher_available(teacher["name"], slot_time, day_name, db, start_time_str, end_time_str) and \
                                            is_teacher_available(teacher["name"], next_slot_time, day_name, db, start_time_str, end_time_str)

                    if teacher_available:
                        slot["Subject"] = subject_code
                        slot["Teacher"] = teacher["name"]
                        next_slot["Subject"] = subject_code
                        next_slot["Teacher"] = teacher["name"]

                        teacher_assigned_slots.append((day_idx, slot_idx))
                        teacher_assigned_slots.append((day_idx, next_slot_idx))
                        teacher_assigned_hours += 2
                        assigned_days.add(day_name)

                        # ✅ Update subject count for the day
                        subject_day_count[(subject_code, day_name)] = subject_day_count.get((subject_code, day_name), 0) + 2

                        # ✅ Store in teacher's routine
                        if teacher["name"] not in teachersRoutines:
                            teachersRoutines[teacher["name"]] = {"Name": teacher["name"], "Classes": []}

                        teachersRoutines[teacher["name"]]["Classes"].append({
                            "day": day_name,
                            "timeslot": slot_time,
                            "faculty": faculty,
                            "semester": semester,
                            "type": "Theory",
                            "subject": subject_code
                        })
                        teachersRoutines[teacher["name"]]["Classes"].append({
                            "day": day_name,
                            "timeslot": next_slot_time,
                            "faculty": faculty,
                            "semester": semester,
                            "type": "Theory",
                            "subject": subject_code
                        })

                        print(f"   ✅ Assigned {subject_code} to {teacher['name']} on {day_name} [{slot_time}, {next_slot_time}]")
                        

                        

                        if teacher_assigned_hours >= required_hours:
                            assigned_slots.extend(teacher_assigned_slots)
                            assigned_hours += teacher_assigned_hours
                            successful_assignment = True
                            break  # Stop assigning if full hours are covered

                if successful_assignment:
                    assigned_slots.extend(teacher_assigned_slots)
                    assigned_hours += teacher_assigned_hours
                    successful_assignment = True
                    previous_day_subjects.add(subject_code)  # Store subject to avoid assigning it on consecutive days
                    break  # ✅ Move to next subject if fully assigned

            # ✅ Step 2: If no single teacher could satisfy, try two teachers
            if not successful_assignment:
                print(f"   ⚠ {subject_code} needs additional assignments. Trying two teachers...")
                found_valid_pair = False

                for teacher_1 in sorted_teachers:
                    for teacher_2 in sorted_teachers:
                        if teacher_1["name"] == teacher_2["name"]:
                            continue  

                        teacher_1_hours = 0
                        teacher_2_hours = 0
                        combined_slots = []
                        teacher_1_days = set()
                        teacher_2_days = set()

                        for i in range(len(empty_slots) - 1):
                            day_idx, slot_idx, slot = empty_slots[i]
                            next_day_idx, next_slot_idx, next_slot = empty_slots[i + 1]

                            if next_day_idx != day_idx or next_slot_idx != slot_idx + 1:
                                continue

                            day_name = timetable[day_idx]["Day"]
                            slot_time = slot["Period"]
                            next_slot_time = next_slot["Period"]

                            # ✅ Restrict to max 2 slots per subject per day
                            if subject_day_count.get((subject_code, day_name), 0) >= 2:
                                continue  # Skip if 2 slots are already assigned

                            if teacher_1_hours < required_hours / 2 and day_name not in teacher_1_days:
                                if teacher_1["type"] == "Full Time" or is_teacher_available(teacher_1["name"], slot_time, day_name, db, start_time_str, end_time_str):
                                    slot["Subject"] = subject_code
                                    slot["Teacher"] = teacher_1["name"]
                                    next_slot["Subject"] = subject_code
                                    next_slot["Teacher"] = teacher_1["name"]

                                    combined_slots.append((day_idx, slot_idx))
                                    combined_slots.append((day_idx, next_slot_idx))
                                    teacher_1_hours += 2
                                    teacher_1_days.add(day_name)

                                    subject_day_count[(subject_code, day_name)] = subject_day_count.get((subject_code, day_name), 0) + 2

                            elif teacher_2_hours < required_hours / 2 and day_name not in teacher_2_days:
                                if teacher_2["type"] == "Full Time" or is_teacher_available(teacher_2["name"], slot_time, day_name, db, start_time_str, end_time_str):
                                    slot["Subject"] = subject_code
                                    slot["Teacher"] = teacher_2["name"]
                                    next_slot["Subject"] = subject_code
                                    next_slot["Teacher"] = teacher_2["name"]

                                    combined_slots.append((day_idx, slot_idx))
                                    combined_slots.append((day_idx, next_slot_idx))
                                    teacher_2_hours += 2
                                    teacher_2_days.add(day_name)

                                    subject_day_count[(subject_code, day_name)] = subject_day_count.get((subject_code, day_name), 0) + 2

                            if teacher_1_hours + teacher_2_hours >= required_hours:
                                assigned_slots.extend(combined_slots)
                                assigned_hours += teacher_1_hours + teacher_2_hours
                                successful_assignment = True
                                found_valid_pair = True
                                break  

                        if found_valid_pair:
                            break  # Stop checking if a valid pair is found

            if not successful_assignment:
                print(f"   ⚠ {subject_code} needs additional assignments. Adding to retry list...")
                unassigned_subjects.append(subject)

            empty_slots[:] = [s for s in empty_slots if (s[0], s[1]) not in assigned_slots]

        previous_day_subjects.clear()  # Reset assigned subjects after each day

    for teacher_name, routine in teachersRoutines.items():
        teacher_routines_collection.update_one(
            {"Name": teacher_name},
            {
                "$set": {"Name": teacher_name},  # ✅ Set teacher name (string)
                "$push": {"Classes": {"$each": routine["Classes"]}}  # ✅ Append to the "Classes" array
            },
            upsert=True
        )

    print("✅ Finished assigning all theory subjects.")
    teachersRoutines = {}
    fill_remaining_slots(empty_slots, unassigned_subjects, teachers, timetable, subject_day_count, db, start_time_str, end_time_str, period_length, teachersRoutines, faculty, semester)



def fill_remaining_slots(empty_slots, unassigned_subjects, teachers, timetable, subject_day_count, db, start_time_str, end_time_str, period_length, teachersRoutines, faculty, semester):
    """ Assigns subjects to any remaining empty slots after the first pass, ensuring diverse subject distribution. """
    
    print("\n🔄 **Filling Remaining Empty Slots...**")

    # ✅ Prioritize subjects with the highest remaining required hours
    unassigned_subjects.sort(key=lambda s: -((s.get("L", 0) + s.get("T", 0)) * 60 // period_length))

    # ✅ Track which subjects have been assigned per day to avoid repeating the same subject
    day_subjects = {day["Day"]: set() for day in timetable}

    # ✅ Group empty slots by day to handle consecutive vs non-consecutive slots
    empty_slots_by_day = {}
    for slot_data in empty_slots:
        day_idx, slot_idx, slot = slot_data
        day_name = timetable[day_idx]["Day"]
        if day_name not in empty_slots_by_day:
            empty_slots_by_day[day_name] = []
        empty_slots_by_day[day_name].append((day_idx, slot_idx, slot))

    # ✅ Loop through each day's empty slots
    for day_name, slots in empty_slots_by_day.items():
        slots.sort(key=lambda x: x[1])  # Sort slots by index to detect consecutive ones
        i = 0

        while i < len(slots):
            day_idx, slot_idx, slot = slots[i]
            slot_time = slot["Period"]

            # ✅ Identify subjects that haven't been assigned on this day
            available_subjects = [s for s in unassigned_subjects if s["Code"] not in day_subjects[day_name]]

            if not available_subjects:
                # If all subjects have been assigned on this day, reset tracking to allow more assignments
                available_subjects = unassigned_subjects

            # ✅ Select a subject (shuffle to avoid repetition patterns)
            random.shuffle(available_subjects)
            subject = available_subjects.pop(0)
            subject_code = subject["Code"]
            remaining_hours = (subject.get("L", 0) + subject.get("T", 0)) * 60 // period_length

            # ✅ Find a teacher for this subject
            subject_teachers = [t for t in teachers if subject_code in t.get("Course_Code", [])]

            if not subject_teachers:
                print(f"❌ No teachers found for {subject_code}. Skipping this subject...")
                i += 1
                continue

            random.shuffle(subject_teachers)
            teacher = subject_teachers[0]  # Pick the first available teacher

            # ✅ Assign subject to the slot
            slot["Subject"] = subject_code
            slot["Teacher"] = teacher["name"]
            day_subjects[day_name].add(subject_code)  # Track subject assigned on this day

            print(f"   ✅ Assigned {subject_code} to {teacher['name']} on {day_name} [{slot_time}]")

            # ✅ Store in teacher's routine
            if teacher["name"] not in teachersRoutines:
                teachersRoutines[teacher["name"]] = {"Name": teacher["name"], "Classes": []}

            teachersRoutines[teacher["name"]]["Classes"].append({
                "timeslot": slot_time,
                "day": day_name,
                "faculty": faculty,
                "semester": semester,
                "type": "Theory",
                "subject": subject_code
            })

            # ✅ Check if the next slot is consecutive
            if i + 1 < len(slots) and slots[i + 1][1] == slot_idx + 1:
                # ✅ Two consecutive slots found, decide whether to assign the same subject or a different one
                next_day_idx, next_slot_idx, next_slot = slots[i + 1]
                next_slot_time = next_slot["Period"]

                # ✅ If we have remaining hours and a consecutive slot, assign the same subject
                if remaining_hours >= 2:
                    next_slot["Subject"] = subject_code
                    next_slot["Teacher"] = teacher["name"]
                    i += 1  # Skip next slot since it's assigned


                    # ✅ Store in teacher's routine
                    teachersRoutines[teacher["name"]]["Classes"].append({
                        "timeslot": next_slot_time,
                        "day": day_name,
                        "faculty": faculty,
                        "semester": semester,
                        "type": "Theory",
                        "subject": subject_code
                    })

                    print(f"   ✅ Also assigned {subject_code} to {teacher['name']} on {day_name} [{next_slot_time}]")
                else:
                    # ✅ If not enough remaining hours, assign a different subject
                    another_subjects = [s for s in unassigned_subjects if s["Code"] != subject_code and s["Code"] not in day_subjects[day_name]]
                    
                    if another_subjects:
                        random.shuffle(another_subjects)
                        different_subject = another_subjects.pop(0)
                        different_subject_code = different_subject["Code"]
                        different_subject_teachers = [t for t in teachers if different_subject_code in t.get("Course_Code", [])]

                        if different_subject_teachers:
                            random.shuffle(different_subject_teachers)
                            different_teacher = different_subject_teachers[0]

                            next_slot["Subject"] = different_subject_code
                            next_slot["Teacher"] = different_teacher["name"]
                            day_subjects[day_name].add(different_subject_code)

                            print(f"   ✅ Assigned {different_subject_code} to {different_teacher['name']} on {day_name} [{next_slot_time}]")

                i += 1  # Move to the next slot

            i += 1  # Continue to the next slot in the loop

    for teacher_name, routine in teachersRoutines.items():
        teacher_routines_collection.update_one(
            {"Name": teacher_name},
                {
                    "$set": {"Name": teacher_name},  # ✅ Set teacher name (string)
                    "$push": {"Classes": {"$each": routine["Classes"]}}  # ✅ Append to the "Classes" array
                },
                upsert=True
            )

    print("✅ **All remaining empty slots filled!**")


def assign_classes_and_store(current_tt, subjects, teachers, semester):

    # Assign lab sessions first
    print("🔍 Assigning Lab Sessions...")
    assigned_labs = assign_lab_sessions_new(current_tt, subjects, teachers)

    # Store lab details in 'Lab Details'
    for lab in assigned_labs:
        db["Lab Details"].insert_one({
            "Subject_Code": lab["Subject_Code"],
            "Subject_Name": lab["Subject_Name"],
            "Lab_Room": lab["Lab_Room"],
            "Teacher": lab["Teacher"],
            "Day": lab["Day"],
            "Time_Slot": lab["Time_Slot"]
        })
        print(f"✅ Stored lab assignment for {lab['Subject_Name']} on {lab['Day']} at {lab['Time_Slot']}")

    return current_tt




def assign_full_time_teachers(faculty, semester):
    """
    Assigns full-time teachers to remaining unassigned theory classes.
    - Ensures no teacher has more than 2 consecutive periods.
    - Ensures no teacher is assigned to multiple subjects in a single semester.
    """
    timetable = db["timetables"].find_one({"Faculty": faculty, "Semester": semester})
    if not timetable:
        print(f"⚠️ No timetable found for {faculty}, Semester {semester}. Skipping full-time teacher assignment.")
        return

    unassigned_subjects = [s for s in db["subjects"].find({"Faculty": faculty, "Semester": semester}) if not is_subject_assigned(s["Code"], timetable)]

    for subject in unassigned_subjects:
        teacher = find_available_teacher(subject["Code"], priority_part_time=False)

        assigned = False
        for day in timetable:
            for slot in day["Slots"]:
                if "Break" in slot["Period"]:
                    continue
                if not is_slot_occupied(timetable, day["Day"], slot["Period"]):
                    slot["Subject"] = f"{subject['Name']} ({subject['Code']})"
                    slot["Teacher"] = teacher["name"]
                    update_teacher_workload(teacher["_id"], subject["L"] + subject.get("T", 0))
                    assigned = True
                    print(f"✅ Assigned {teacher['name']} to {subject['Name']} on {day['Day']} at {slot['Period']}")
                    break
            if assigned:
                break



def is_subject_assigned(subject_code, timetable):
    """
    Checks if a subject **has already been assigned** in the timetable.
    """
    for day in timetable["Timetable"]:
        for slot in day["Slots"]:
            if slot.get("Subject") and subject_code in slot["Subject"]:
                return True  # ❌ Already assigned
    return False  # ✅ Not assigned yet


def is_teacher_assigned(teacher_name, day, time_slot):
    assignment = db["timetables"].find_one({
        "Timetable.Day": day,
        "Timetable.Slots.Teacher.name": teacher_name,
        "Timetable.Slots.Period": time_slot
    })
    return assignment is not None




def fill_empty_slots(timetable, subjects, teachers):
    for day_obj in timetable["Timetable"]:
        for slot in day_obj["Slots"]:
            if "Subject" not in slot or slot["Subject"] in ["Unavailable", None, ""]:
                available_subjects = [s for s in subjects if s.get("Code")]
                if available_subjects:
                    chosen_subject = random.choice(available_subjects)
                    chosen_teacher = find_available_teacher(chosen_subject["Code"])
                    slot["Subject"] = f"{chosen_subject['Name']} ({chosen_subject['Code']})"
                    slot["Teacher"] = chosen_teacher["name"] if chosen_teacher else "Unknown"
    return timetable

def clear_previous_lab_entries(faculty, semester):
    """Clears existing lab entries before saving new ones."""
    db["Lab Details"].delete_many({"Faculty": faculty, "Semester": semester})
    print(f"🗑️ Cleared previous lab entries for {faculty} Semester {semester}.")


def create_time_slots(start_time, end_time, period_length, break_start, break_end):
    slots = []
    start_dt = datetime.strptime(start_time, "%I:%M %p")
    end_dt = datetime.strptime(end_time, "%I:%M %p")
    break_start_dt = datetime.strptime(break_start, "%I:%M %p")
    break_end_dt = datetime.strptime(break_end, "%I:%M %p")

    current = start_dt
    while current < end_dt:
        next_time = current + timedelta(minutes=period_length)
        if current == break_start_dt:
            slots.append({"Period": f"{break_start_dt.strftime('%I:%M %p')} - {break_end_dt.strftime('%I:%M %p')}", "is_break": True})
            current = break_end_dt
            continue

        if next_time <= end_dt:
            slots.append({"Period": f"{current.strftime('%I:%M %p')} - {next_time.strftime('%I:%M %p')}", "is_break": False})
        current = next_time
    return slots



def transfer_lab_details_to_timetable(faculty, semester):
    """
    Transfers lab session details from 'Lab Details' to the 'timetables' collection
    while supporting parallel labs in the same time slot.
    """
    print(f"\n🔄 Transferring Lab Details to Timetable for {faculty}, Semester {semester}...")

    # ✅ Fetch existing timetable for the given faculty and semester
    timetable_entry = db["timetables"].find_one({"Faculty": faculty, "Semester": semester})
    
    if not timetable_entry:
        print(f"⚠️ No timetable found for {faculty}, Semester {semester}.")
        return

    timetable = timetable_entry["Timetable"]

    # ✅ Fetch all lab sessions for this faculty and semester
    lab_sessions = list(db["Lab Details"].find({"Faculty": faculty, "Semester": semester}))

    if not lab_sessions:
        print("⚠️ No lab sessions found in 'Lab Details'.")
        return

    # ✅ Map lab sessions by (day, time_slot)
    lab_mapping = {}
    for lab in lab_sessions:
        day = lab["Day"]
        time_slot = lab["Time_Slot"]
        lab_info = {
            "Subject": lab["Subject_Name"],
            "Subject_Code": lab["Subject_Code"],
            "Teacher": lab["Teacher"],
            "Lab_Room": lab["Lab_Room"],
            "Lab_Assigned": True
        }

        # ✅ Store multiple labs in the same slot as a list
        if (day, time_slot) not in lab_mapping:
            lab_mapping[(day, time_slot)] = []
        
        lab_mapping[(day, time_slot)].append(lab_info)

    # ✅ Update timetable with lab data
    for day_schedule in timetable:
        day = day_schedule["Day"]
        for slot in day_schedule["Slots"]:
            time_slot = slot["Period"]

            if (day, time_slot) in lab_mapping:
                # ✅ Store parallel labs as a list
                slot["Lab_Sessions"] = lab_mapping[(day, time_slot)]

    # ✅ Save the updated timetable back to the database
    db["timetables"].update_one(
        {"Faculty": faculty, "Semester": semester},
        {"$set": {"Timetable": timetable}}
    )

    print(f"✅ Lab sessions successfully transferred for {faculty}, Semester {semester}!")




def is_duplicate_assignment(day, time_slot, subject_code):
    """
    Checks if the lab for the given subject is already assigned during the same time slot on the same day.
    """
    existing_lab = db["Lab Details"].find_one({
        "Day": day,
        "Time_Slot": time_slot,
        "Subject_Code": subject_code
    })
    return existing_lab is not None

def has_reached_p_limit(subject_code, practical_hours):
    """
    Checks if a subject has already reached its practical session limit.
    """
    assigned_sessions = db["Lab Details"].count_documents({"Subject_Code": subject_code})
    # Each practical session is assumed to be 1.5 hours
    required_sessions = practical_hours / 1.5
    return assigned_sessions >= required_sessions


def fetch_lab_subjects(faculty, semester):
    lab_subjects = list(db["subjects"].find({
        "Faculty": faculty,
        "Semester": semester,
        "P": {"$gt": 0}  # Ensure only subjects with practical hours are fetched
    }))

    print(f"🔍 Lab Subjects for {faculty} Semester {semester}:")
    for subject in lab_subjects:
        print(f"➡️ {subject.get('Name')} ({subject.get('Code')}) - P: {subject.get('P')}")

    return lab_subjects



def is_slot_occupied(day, time_slot, lab_room):
    """
    Check if the given lab room is already booked for a time slot on a specific day.
    """
    existing = db["Lab Details"].find_one({
        "Day": day,
        "Time_Slot": time_slot,
        "Lab_Room": lab_room
    })
    
    if existing:
        print(f"⚠️ Lab {lab_room} is already occupied on {day} at {time_slot}. Trying next available slot.")
    return existing is not None



def update_teacher_workload(db):
    """
    Calculates the workload for each teacher based on their assigned theory and practical classes
    and updates the workload in the `teachers` collection.
    """

    print("🔄 Updating teacher workload...")

    # ✅ Fetch all teacher routines
    teacher_routines = db["teacherRoutines"].find()

    # ✅ Track workload per teacher
    teacher_workload = {}

    for routine in teacher_routines:
        teacher_name = routine.get("Name")
        if not teacher_name:
            continue  # Skip if teacher name is missing

        # ✅ Initialize workload count
        theory_count = 0
        practical_count = 0

        # ✅ Loop through all assigned classes
        for class_info in routine.get("Classes", []):
            if class_info.get("type") == "Theory":
                theory_count += 1  # Each theory class slot counts as 1
            elif class_info.get("type") == "Practical":
                practical_count += 1  # Each practical slot counts as 1

        # ✅ Compute total workload
        workload = (0.5 * theory_count) + (0.2 * practical_count)
        teacher_workload[teacher_name] = workload

        print(f"   ➝ {teacher_name}: {workload} workload (Theory: {theory_count}, Practical: {practical_count})")

    # ✅ Update workload field in `teachers` collection
    for teacher_name, workload in teacher_workload.items():
        db["teachers"].update_one(
            {"name": teacher_name},  # Find teacher by name
            {"$set": {"Workload": workload}},  # Update Workload field
            upsert=True  # Create if it doesn't exist
        )

    print("✅ Teacher workload updated successfully!")



def assign_lab_sessions_new(subjects, timetable, teachers, faculty, semester):
    print("🔍 Starting Lab Session Assignment...\n")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    preferred_slots = {
        "afternoon": [
            ["12:30 PM - 01:15 PM", "01:15 PM - 02:00 PM", "02:00 PM - 02:45 PM", "02:45 PM - 03:30 PM"]
        ],
        "morning": [
            ["07:15 AM - 08:00 AM", "08:00 AM - 08:45 AM", "08:45 AM - 09:30 AM", "09:30 AM - 10:15 AM"]
        ]
    }

    def normalize_time_format(time_str):
        from datetime import datetime
        try:
            start_time, end_time = time_str.strip().split(" - ")
            start_time_obj = datetime.strptime(start_time.strip(), "%I:%M %p")
            end_time_obj = datetime.strptime(end_time.strip(), "%I:%M %p")
            return f"{start_time_obj.strftime('%I:%M %p')} - {end_time_obj.strftime('%I:%M %p')}"
        except ValueError as e:
            print(f"⚠️ Time format error: {e} in '{time_str}'")
            return time_str.strip()

    for day_schedule in timetable:
        for slot in day_schedule["Slots"]:
            normalized_slot_period = normalize_time_format(slot["Period"])
            if normalized_slot_period in [normalize_time_format(period) for period in preferred_slots["afternoon"][0]]:
                slot["Reserved_For_Lab"] = True

    lab_subjects = [subject for subject in subjects if subject.get('P', 0) > 0]
    assigned_sessions = {subject['Code']: 0 for subject in lab_subjects}
    last_assigned_days = {subject['Code']: [] for subject in lab_subjects}

    def is_non_consecutive_day(subject_code, current_day):
        day_map = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
        current_day_index = day_map.get(current_day, -1)
        for assigned_day in last_assigned_days[subject_code]:
            if abs(current_day_index - day_map[assigned_day]) <= 1:
                return False
        return True

    def check_full_block_availability(day_schedule, start_index):
        block_slots = day_schedule["Slots"][start_index:start_index+4]
        return all(
            slot.get('Reserved_For_Lab', False) and not slot.get('Subject')
            for slot in block_slots
        )

    def assign_lab_block(subject, day_schedule, start_index, teacher):
        slots = day_schedule["Slots"][start_index:start_index+4]
        lab_sessions = []
        for slot in slots:
            slot["Subject"] = subject['Name']
            slot["Subject_Code"] = subject['Code']
            slot["Teacher"] = teacher["name"]
            slot["Lab_Room"] = subject.get('Ptype', 'General Lab')
            slot["Lab_Assigned"] = True
            store_lab_detail(subject['Code'], subject['Name'], subject.get('Ptype', 'General Lab'), teacher["name"], day_schedule['Day'], slot["Period"], faculty, semester)
        
        
        # ✅ Store Lab Class in teacherRoutines
        # ✅ Add each slot to lab_sessions list
            lab_sessions.append({
                "day": day_schedule["Day"],
                "timeslot": slot["Period"],
                "faculty": faculty,
                "semester": semester,
                "type": "Practical",
                "subject": subject['Code']
            })

        # ✅ Store all 4 consecutive lab slots in teacherRoutines using $push
        teacher_routines_collection.update_one(
            {"Name": teacher["name"]},
            {"$push": {"Classes": {"$each": lab_sessions}}},  # Store all four slots
            upsert=True
        )

        last_assigned_days[subject['Code']].append(day_schedule['Day'])
        assigned_sessions[subject['Code']] += 1

    def assign_session(subject, is_second_session=False):
        for slot_type in ["afternoon", "morning"]:
            for day in day_order:
                for day_schedule in timetable:
                    if day_schedule["Day"] != day:
                        continue
                    if is_second_session and not is_non_consecutive_day(subject['Code'], day):
                        continue
                    slots = day_schedule["Slots"]
                    for i in range(0, len(slots) - 3):
                        if check_full_block_availability(day_schedule, i):
                            if assigned_sessions[subject['Code']] >= (2 if subject['P'] == 3 else 1):
                                continue  # Avoid over-assignment
                            teacher = find_available_teacher(subject['Code'], day, slots[i]['Period'], timetable, subject['Semester'])
                            if teacher:
                                assign_lab_block(subject, day_schedule, i, teacher)
                                print(f"✅ Assigned 4-slot lab block for {subject['Name']} ({subject['Code']}) on {day} starting at {slots[i]['Period']}")
                                # Assign a parallel lab
                                parallel_assigned = 0
                                for parallel_subject in lab_subjects:
                                    if (parallel_subject['Code'] != subject['Code'] and
                                            assigned_sessions[parallel_subject['Code']] < (2 if parallel_subject['P'] == 3 else 1)):
                                        parallel_teacher = find_available_teacher(parallel_subject['Code'], day, slots[i]['Period'], timetable, parallel_subject['Semester'])
                                        if parallel_teacher:
                                            assign_lab_block(parallel_subject, day_schedule, i, parallel_teacher)
                                            print(f"✅ Parallel Lab Assigned for {parallel_subject['Name']} ({parallel_subject['Code']}) in same block.")
                                            parallel_assigned += 1
                                            if parallel_assigned >= 1:  # Allow only 2 parallel labs
                                                break
                                return True
        return False

    for subject in lab_subjects:
        required_sessions = 2 if subject['P'] == 3 else 1
        print(f"🟢 Starting assignment for {subject['Name']} ({subject['Code']}), requires {required_sessions} sessions.")
        for session_num in range(required_sessions):
            if assigned_sessions[subject['Code']] >= required_sessions:
                break  # Stop if required sessions are already assigned
            success = assign_session(subject, is_second_session=(session_num == 1))
            if not success:
                print(f"⚠️ Could not assign lab for {subject['Name']} ({subject['Code']}) session {session_num + 1}.")

    print("🟢 Lab session assignment process completed.\n")
    return timetable


def create_blank_timetable(faculty, semester, selected_days, slots):
    """
    Creates an initial blank timetable with only time slots and empty subject fields.
    This ensures that all slots are available before assigning subjects and labs.
    """

    blank_timetable = []
    for day in selected_days:
        blank_timetable.append({
            "Day": day,
            "Slots": [{"Period": slot["Period"], "is_break": slot["is_break"]} for slot in slots]
        })

    # ✅ Store the blank timetable in MongoDB
    db["timetables"].update_one(
        {"Faculty": faculty, "Semester": semester},
        {"$set": {"Timetable": blank_timetable}},
        upsert=True
    )

    print(f"✅ Created a blank timetable for {faculty}, Semester {semester}")


def generate_backtracking_timetable(faculty, subjects, teachers, days_per_week, start_time_str, end_time_str, period_length, break_start, break_end, semester, holidays=[]):
    """
    Generates the timetable and ensures lab assignments are correctly stored without overwriting.
    """
    assignment = None
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    selected_days = [d for d in day_names if d not in holidays][:days_per_week]

    slots = create_time_slots(start_time_str, end_time_str, period_length, break_start, break_end)


    # Step 1: Create an empty timetable
    create_blank_timetable(faculty, semester, selected_days, slots)

    # Step 2: Assign lab sessions first
    print("✅ Assigning Lab Sessions...")
    timetable = [{"Day": day, "Slots": [copy.deepcopy(slot) for slot in slots]} for day in selected_days]
    assign_lab_sessions_new(subjects, timetable, teachers, faculty, semester)

    # ✅ Save Lab Assignments (Ensures Labs are stored in 'Lab Details')
    print("✅ Saving Lab Assignments to 'Lab Details'...")
    for day_schedule in timetable:
        day = day_schedule["Day"]
        for slot in day_schedule["Slots"]:
            if "Lab_Assigned" in slot and slot["Lab_Assigned"]:
                subject_code = slot.get("Subject_Code", "Unknown")
                subject_name = slot.get("Subject", "Unknown")
                lab_room = slot.get("Lab_Room", "General Lab")
                teacher = slot.get("Teacher", "Unknown")
                teacher_name = teacher["name"] if isinstance(teacher, dict) else teacher
                store_lab_detail(subject_code, subject_name, lab_room, teacher_name, day, slot["Period"], faculty, semester)

    # Step 3: Transfer Lab Details to Timetable AFTER storing in Lab Details
    print("✅ Transferring Lab Details to Timetable...")
    transfer_lab_details_to_timetable(faculty, semester)

    # Step 4: Fetch the updated timetable from the database (this ensures it includes labs)
    timetable_entry = db["timetables"].find_one({"Faculty": faculty, "Semester": semester})
    if not timetable_entry:
        print(f"❌ No timetable found for {faculty} Semester {semester}")
        return

    timetable = timetable_entry["Timetable"]  # ✅ Now contains transferred lab details
    current_tt = {"Timetable": timetable}

    # ✅ Step 5: Identify empty slots before assigning theory subjects
    empty_slots = []

    # Fetch timetable from the database
    timetable_entry = db["timetables"].find_one({"Faculty": faculty, "Semester": semester})
    if not timetable_entry:
        print(f"❌ No timetable found for {faculty} Semester {semester}")
    else:
        timetable = timetable_entry["Timetable"]

        for day_idx, day in enumerate(timetable):  # ✅ Loop through timetable days with index
            for slot_idx, slot in enumerate(day["Slots"]):  # ✅ Loop through slots with index
                # ✅ Check if the slot is truly empty (No lab or subject assigned)
                if ("Lab_Sessions" not in slot or not slot["Lab_Sessions"]) and "Subject" not in slot:
                    if not slot.get("is_break", False):  # ✅ Ensure the slot is NOT a break period
                        empty_slots.append((day_idx, slot_idx, slot))  # ✅ Store (day_index, slot_index, slot_object)

    # 🟢 Debug: Print available empty slots (Excluding break slots)
    # 🟢 Debug: Print all available empty slots properly
    print("\n🟢 Total Empty Slots for Theory (Excluding Breaks):", len(empty_slots))

    if len(empty_slots) == 0:
        print("⚠ No available empty slots for theory classes.")
    else:
        print("\n📋 **Complete List of Available Slots for Theory**:")
        for slot in empty_slots:
            day_name = timetable[slot[0]]['Day']
            period = slot[2]['Period']
            print(f"➖ Available Slot on {day_name} at {period}")

        print("\n✅ All empty slots successfully listed.")



    # Step 5: Assign theory subjects
    print("✅ Assigning Theory Subjects using Backtracking...")
    teachersRoutines = {}  # ✅ Initialize teacher schedules dictionary
    assign_theory_subjects(current_tt, subjects, teachers, semester, faculty, days_per_week, start_time_str, end_time_str, empty_slots, db, period_length, teachersRoutines)

    # 🔥 Fix: Ensure assignment is always a dictionary
    if not assignment:  
        print("⚠️ Warning: No assignments were made.")
        assignment = {}  # ✅ Prevent NoneType error

    # 🔥 Fix: Ensure assigned_classes always exists inside `assign_theory_subjects()`
    if not isinstance(assignment, dict):  
        print("❌ Unexpected data type from assign_theory_subjects(). Expected a dictionary.")
        assignment = {}
        
    # Step 6: Save final theory assignments to timetable
    for key, value in assignment.items():
        if isinstance(key, tuple) and isinstance(value, tuple) and len(value) == 2:
            (day_idx, slot_idx) = key
            (subject_code, teacher_name) = value
        else:
            print(f"⚠️ Skipping unexpected format: {key} -> {value}")
            continue 

        day = timetable[day_idx]["Day"]
        time_slot = timetable[day_idx]["Slots"][slot_idx]["Period"]
        subject = next((s for s in subjects if s["Code"] == subject_code), None)

        if subject:
            existing_entry = db["teacherRoutines"].find_one({
                "Teacher_Name": teacher_name, "Day": day, "Time_Slot": time_slot
            })
            if not existing_entry:
                store_teacher_routine(teacher_name, day, time_slot, subject["Name"])
            else:
                print(f"⚠ Skipping duplicate routine entry for {teacher_name} on {day} at {time_slot}.")


     # ✅ Step 7: Calculate and Update Teacher Workload
    print("✅ Updating Teacher Workload...")
    update_teacher_workload(db)  # 🔥 **Call the function here after all assignments are done**

    # ✅ Step 8: Save the updated timetable (Ensures that labs are already present before updating)
    print("✅ Saving Final Timetable...")
    for day_schedule in timetable:
        db["timetables"].update_one(
            {"Faculty": faculty, "Semester": semester, "Timetable.Day": day_schedule["Day"]},
            {"$set": {"Timetable.$.Slots": day_schedule["Slots"]}}
        )

    print(f"✅ Timetable successfully generated and stored for {faculty} Semester {semester}")
    return {"Timetable": timetable}


def remove_duplicate_lab_entries():
    # ✅ Remove entries where subject code is marked as 'Unknown'
    deleted_count = db["Lab Details"].delete_many({"Subject_Code": "Unknown"}).deleted_count
    print(f"🗑️ Removed {deleted_count} duplicate lab entries with 'Unknown' subject code.")




def fetch_lab_details():
    """
    Fetch all lab details from the database.
    Ensures correct mapping of Subject, Teacher, and Lab Room.
    """
    labs = list(db["Lab Details"].find({}, {"_id": 0}))  # Exclude ObjectId
    return labs



def assign_lab_details(subject_id):
    subject = db["subjects"].find_one({"_id": ObjectId(subject_id)})
    if not subject:
        print(f"⚠️ Subject with ID {subject_id} not found.")
        return None
    subject_code = subject.get("Code", "Unknown")
    subject_name = subject.get("Name", "Unnamed Subject")
    lab_room = subject.get("Ptype", None)
    if not lab_room:
        print(f"ℹ️ No practicals for subject {subject_name} ({subject_code}). Skipping lab assignment.")
        return None
    teachers = list(db["teachers"].find({"Course_Code": subject_code}))
    teacher_1 = teachers[0] if len(teachers) > 0 else None
    teacher_2 = teachers[1] if len(teachers) > 1 else None
    time_slot = "11:00 AM - 12:30 PM"  # Example; replace with dynamic logic if needed
    day = "Monday"  # Example; replace with dynamic logic if needed
    existing_lab = db["Lab Details"].find_one({"Lab_Room": lab_room, "Time_Slot": time_slot, "Day": day})
    if existing_lab:
        print(f"⚠️ Lab {lab_room} already booked on {day} at {time_slot}.")
        return None
    lab_detail = {
        "Subject_Code": subject_code,
        "Subject_Name": subject_name,
        "Lab_Room": lab_room,
        "Teacher_1": {"name": teacher_1["name"], "designation": teacher_1["designation"]} if teacher_1 else None,
        "Teacher_2": {"name": teacher_2["name"], "designation": teacher_2["designation"]} if teacher_2 else None,
        "Time_Slot": time_slot,
        "Day": day
    }
    result = db["Lab Details"].insert_one(lab_detail)
    print(f"✅ Lab assigned for {subject_name} ({subject_code}) in {lab_room} at {time_slot} on {day}.")
    return result.inserted_id


def check_lab_capacity(lab_room, day, time_slot):
    """Ensures that lab room capacity is not exceeded."""
    assigned_count = db["Lab Details"].count_documents({
        "Lab_Room": lab_room,
        "Day": day,
        "Time_Slot": time_slot
    })
    max_capacity = LAB_CAPACITY.get(lab_room, 1)
    return assigned_count < max_capacity



# Function to check lab availability
def check_lab_availability(lab_type, day, time_slot):
    count = lab_details_collection.count_documents({
        "Lab_Room": lab_type,
        "Day": day,
        "Time_Slot": time_slot
    })
    return count < LAB_CAPACITY.get(lab_type, 1)


def check_lab_conflict(lab_room, time_slot, day):
    existing_lab = db["Lab Details"].find_one({
        "Lab_Room": lab_room,
        "Time_Slot": time_slot,
        "Day": day
    })
    if existing_lab:
        return True  # ✅ Conflict exists

    # ✅ Also check if any teacher assigned to this lab is available
    assigned_teachers = [lab["Teacher"]["name"] for lab in db["Lab Details"].find({"Time_Slot": time_slot, "Day": day})]
    available_teachers = db["teachers"].find({"name": {"$nin": assigned_teachers}})
    
    return not bool(list(available_teachers))  # ✅ Returns True if **no available teacher**




FACULTIES = ["Computer", "Civil", "Electronics", "Electrical"]
SEMESTERS = [1, 2, 3, 4, 5, 6, 7, 8]

# Predefined lab room capacities (lab type -> available number of rooms)
LAB_ROOM_CAPACITY = {
    "Hardware": 2,
    "Software": 5,
    "English Lab": 1,
    "Thermo Lab": 1,
    "Workshop": 1,
    "Chemistry Lab": 1,
    "Physic Lab": 1,
    "Drawing": 2,
    "Electrical Lab": 2
}

def convert_teacher_availability(availability):
    converted = {}
    for day, times in availability.items():
        converted[day] = [f"{convert_24_to_12(t.split('-')[0])} - {convert_24_to_12(t.split('-')[1])}" for t in times]
    return converted


@app.route('/input', methods=['GET', 'POST'])
def index():
    subjects = []
    db_status = {
        "connected": db is not None,
        "database_name": db.name if db is not None else "Not Connected",
        "collections": db.list_collection_names() if db is not None else []
    }
    user = session.get('user')
    user_role = session.get('user_role')
    faculty_name = session.get('faculty_name')

    print(f"Database status: {db_status}")

    if request.method == 'POST':
        faculty = request.form['faculty']
        semester = int(request.form['semester'])
        days_per_week = int(request.form['days'])
        start_time = request.form['start'].strip()
        end_time = request.form['end'].strip()
        period_length = int(request.form['period_length'])
        break_length = int(request.form['break_length'])

        # Convert to 12-hour format
        def convert_to_12hr(time_str):
            return datetime.strptime(time_str, "%H:%M").strftime("%I:%M %p")

        start_time_12hr = convert_to_12hr(start_time)
        end_time_12hr = convert_to_12hr(end_time)

        # Auto-calculate break time
        start_dt = datetime.strptime(start_time_12hr, "%I:%M %p")
        break_start_dt = start_dt + timedelta(hours=3)
        break_end_dt = break_start_dt + timedelta(minutes=break_length)
        break_start = break_start_dt.strftime("%I:%M %p")
        break_end = break_end_dt.strftime("%I:%M %p")

        print(f"🟢 Auto-Calculated Break Time: {break_start} - {break_end}")

        time_slots = create_time_slots(start_time_12hr, end_time_12hr, period_length, break_start, break_end)
        holidays = request.form.getlist('holidays[]')

        elective_subjects = {}
        for key in request.form:
            if key.startswith('elective_'):
                elective_name = key.replace('elective_', '').replace('_', ' ')
                elective_subjects[elective_name] = request.form.getlist(key)

        # Fetch subjects and teachers
        print(f"Querying subjects for Faculty: {faculty}, Semester: {semester}")
        try:
            subjects = list(db['subjects'].find({
                "Semester": semester,
                "Faculty": {'$regex': f"^{faculty}$", '$options': 'i'}
            }))
            print(f"Subjects found: {subjects}")
        except Exception as e:
            print(f"Error while fetching subjects: {e}")
            return "Error occurred while fetching subjects."

        teachers = list(db['teachers'].find())
        print(f"Teachers found: {teachers}")

        if not subjects:
            return "No subjects found for the selected semester and faculty."
        if not teachers:
            return "No teachers found in the database."

        # ✅ Step 1: Generate Timetable (Both Lab & Theory)
        timetable_data = {
            "Faculty": faculty,
            "Semester": semester,
            "Days_per_Week": days_per_week,
            "Holidays": holidays,
            "Start_Time": start_time,
            "End_Time": end_time,
            "Period_Length": period_length,
            "Break_Length": break_length,
            "Elective_Subjects": elective_subjects,
            "Time_Slots": time_slots
        }

        timetable = generate_backtracking_timetable(
            subjects, teachers, days_per_week, start_time_12hr, end_time_12hr, period_length, break_start, break_end,semester, holidays
        )

        # ✅ Step 2: Save Timetable
        save_timetable(timetable, faculty, semester, timetable_data)

        return redirect(url_for('generate_timetable_route'))

    return render_template('input.html', faculties=FACULTIES, semesters=SEMESTERS, subjects=subjects, db_status=db_status, user=user, user_role=user_role, faculty_name=faculty_name)





def consecutive_teacher_limit_reached(day_schedule, teacher_name):
    consecutive_count = 0
    for slot in day_schedule["Slots"]:
        if slot.get("Teacher") == teacher_name:
            consecutive_count += 1
            if consecutive_count >= 2:
                print(f"⚠️ {teacher_name} already has {consecutive_count} consecutive periods. Skipping.")
                return True
        else:
            consecutive_count = 0  # Reset count if different teacher
    return False


@app.route('/generate_timetable', methods=['POST'])
def generate_timetable_route():
    try:
        faculty = request.form['faculty']
        semester = int(request.form['semester'])
        days_per_week = int(request.form['days'])
        period_length = int(request.form['period_length'])
        break_length = int(request.form['break_length'])
        start_time_str = request.form['start'].strip()
        end_time_str = request.form['end'].strip()

        # Convert time to 12-hour format
        def convert_to_12hr(time_str):
            return datetime.strptime(time_str, "%H:%M").strftime("%I:%M %p")

        start_time_12hr = convert_to_12hr(start_time_str)
        end_time_12hr = convert_to_12hr(end_time_str)

        start_dt = datetime.strptime(start_time_12hr, "%I:%M %p")
        break_start_dt = start_dt + timedelta(hours=3)
        break_end_dt = break_start_dt + timedelta(minutes=break_length)
        break_start = break_start_dt.strftime("%I:%M %p")
        break_end = break_end_dt.strftime("%I:%M %p")

        holidays = request.form.getlist('holidays[]')

        subjects = list(db['subjects'].find({
            "Semester": semester,
            "Faculty": {'$regex': f"^{faculty}$", '$options': 'i'}
        }))
        teachers = list(db['teachers'].find())

        if not subjects or not teachers:
            return "No subjects or teachers found."

        subject_names = {s["Code"]: s["Name"] for s in subjects if "Code" in s and "Name" in s}


        # ✅ Generate Timetable
        timetable_data = generate_backtracking_timetable(
            faculty, subjects, teachers, days_per_week, start_time_12hr, end_time_12hr,  # ✅ Pass start & end time
            period_length, break_start, break_end, semester, holidays
        )


        # ✅ Save Timetable
        db['timetables'].update_one(
            {"Faculty": faculty, "Semester": semester},
            {"$set": {"Timetable": timetable_data["Timetable"]}},
            upsert=True
        )

        periods = get_periods(faculty, semester)

        return render_template('timetable.html', timetable=timetable_data, periods=periods, faculty=faculty, semester=semester, subject_names=subject_names)

    except Exception as e:
        print(f"❌ Error while generating timetable: {str(e)}")
        traceback.print_exc()
        return f"Error: {str(e)}"



def distribute_subjects_evenly(subjects, days_per_week):
    subject_list = []
    for subject in subjects:
        for _ in range(2):  # Ensuring subjects appear at least twice
            subject_list.append(subject)
    
    # Shuffle to ensure random distribution
    random.shuffle(subject_list)

    # Create a mapping of days to subjects
    subject_mapping = {day: [] for day in range(days_per_week)}
    for i, subject in enumerate(subject_list):
        day_index = i % days_per_week  # Distribute subjects across days
        subject_mapping[day_index].append(subject)
    
    return subject_mapping



def reserve_lab_slots(faculty, semester, timetable):
    """
    Reserves lab slots before assigning theory classes.
    Prioritizes start time or 2 PM slots for lab assignments.
    """
    lab_subjects = list(db["subjects"].find({
        "Faculty": faculty,
        "Semester": semester,
        "P": {"$gt": 0}  # Only subjects with practical hours
    }))

    if not lab_subjects:
        print(f"⚠️ No lab subjects found for {faculty} Semester {semester}.")
        return timetable  # Return unchanged timetable if no labs exist

    print(f"🔍 Found {len(lab_subjects)} lab subjects. Reserving slots...")

    for subject in lab_subjects:
        subject_code = subject["Code"]
        subject_name = subject["Name"]
        lab_room = subject.get("Ptype", "General Lab")
        practical_hours = subject.get("P", 0)

        # ✅ Determine required sessions (P=3 needs 2 sessions)
        required_sessions = int(practical_hours // 1.5)
        sessions_assigned = 0

        for day_obj in timetable:
            if sessions_assigned >= required_sessions:
                break  # Stop once required sessions are assigned

            day_name = day_obj["Day"]
            slots = day_obj["Slots"]

            # ✅ **Try reserving at the start time or 2 PM**
            preferred_slots = [0]  # First slot of the day
            for idx, slot in enumerate(slots):
                if "2:00 PM" in slot["Period"]:  
                    preferred_slots.append(idx)  # Add 2 PM slot if available

            for idx in preferred_slots:
                slot = slots[idx]
                if slot.get("is_break") or "Subject" in slot:
                    continue  # Skip occupied slots

                teacher = find_available_teacher(subject_code, day=day_name, time_slot=slot["Period"])
                if not teacher:
                    print(f"⚠️ No teacher found for {subject_name} ({subject_code}). Skipping.")
                    continue

                # ✅ Assign Lab to the slot
                slot["Subject"] = f"{subject_name} ({subject_code}) - LAB"
                slot["Teacher"] = teacher["name"]

                # ✅ Store in "Lab Details" Collection
                lab_entry = {
                    "Subject_Code": subject_code,
                    "Subject_Name": subject_name,
                    "Lab_Room": lab_room,
                    "Teacher": {"name": teacher["name"], "designation": teacher.get("designation", "N/A")},
                    "Time_Slot": slot["Period"],
                    "Day": day_name
                }
                db["Lab Details"].insert_one(lab_entry)
                print(f"✅ Reserved Lab for {subject_name} at {slot['Period']} on {day_name}")

                sessions_assigned += 1
                break  # Move to the next lab subject

    return timetable




def assign_part_time_teachers(faculty, semester):
    """
    Assigns part-time teachers to subjects based on availability.
    - Prioritizes part-time teachers before assigning full-time teachers.
    - Ensures teachers are not double-booked.
    - Updates teacher workload dynamically.
    """
    
    # Fetch subjects for the given faculty and semester
    subjects = list(db["subjects"].find({"Faculty": faculty, "Semester": semester}))

    # Fetch the timetable for this faculty and semester
    timetable = db["timetables"].find_one({"Faculty": faculty, "Semester": semester})

    if not timetable:
        print(f"⚠️ No timetable found for {faculty}, Semester {semester}. Skipping part-time teacher assignment.")
        return

    # Extract time slots from the timetable
    time_slots = [slot["Period"] for day in timetable["Timetable"] for slot in day["Slots"] if "Break" not in slot["Period"]]

    # Assign teachers to subjects
    for subject in subjects:
        subject_code = subject["Code"]
        assigned = False  # Flag to track if teacher is assigned

        # Fetch part-time teachers who can teach this subject
        teachers = list(db["teachers"].find({"Course_Code": subject_code, "type": "Part Time"}))

        for teacher in teachers:
            if assigned:
                break  # Skip if already assigned

            for day in timetable["Timetable"]:
                for slot in day["Slots"]:
                    time_slot = slot["Period"]
                    
                    # Skip breaks
                    if "Break" in time_slot:
                        continue
                    
                    # Check if teacher is available during this time slot
                    if teacher["availability"].get(day["Day"], []):
                        for available_range in teacher["availability"][day["Day"]]:
                            available_start, available_end = map(pd.to_datetime, available_range.split('-'))
                            slot_start, slot_end = map(pd.to_datetime, time_slot.split('-'))

                            # If teacher is available during this time slot
                            if available_start <= slot_start and available_end >= slot_end:
                                if not is_teacher_assigned(teacher["name"], day["Day"], time_slot):
                                    # ✅ Assign the teacher to this subject and time slot
                                    slot["Subject"] = f"{subject['Name']} ({subject['Code']})"
                                    slot["Teacher"] = {
                                        "name": teacher["name"],
                                        "designation": teacher["designation"],
                                        "workload": calculate_workload(subject["L"], subject["T"], subject["P"])
                                    }

                                    # ✅ Update teacher workload
                                    update_teacher_workload(teacher["_id"], slot["Teacher"]["workload"])
                                    assigned = True
                                    print(f"✅ Assigned {teacher['name']} to {subject['Name']} on {day['Day']} at {time_slot}")
                                    break
                if assigned:
                    break  # Move to next subject if assigned

        if not assigned:
            print(f"⚠️ No part-time teacher available for {subject['Name']} ({subject_code}). Will assign full-time teacher later.")

    # Update the database with assigned timetable
    db["timetables"].update_one({"Faculty": faculty, "Semester": semester}, {"$set": {"Timetable": timetable["Timetable"]}})


def parse_time(time_str):
    """Try to parse time in both 12-hour and 24-hour formats."""
    try:
        return datetime.strptime(time_str, "%I:%M %p")  # First, try 12-hour format
    except ValueError:
        try:
            return datetime.strptime(time_str, "%H:%M")  # If it fails, try 24-hour format
        except ValueError:
            raise ValueError(f"⚠ Invalid time format: {time_str}. Expected HH:MM or HH:MM AM/PM.")


def check_teacher_workload(teacher):
    max_workload = WORKLOAD_LIMITS.get(teacher.get("designation", "Teacher"), 20)
    current_workload = teacher.get("workload", 0)
    return current_workload < max_workload



def check_teacher_workload_and_availability(teacher, day, time_slot):
    max_workload = WORKLOAD_LIMITS.get(teacher.get('designation', 'Teacher'), 20)
    current_workload = teacher.get('workload', 0)

    if current_workload >= max_workload:
        return False  # Exceeds workload limit

    # Check if the teacher is already teaching another semester at the same time
    if is_teacher_assigned_to_other_semester(teacher["name"], day, time_slot):
        return False  # Conflict exists, teacher already assigned

    return True  # ✅ Teacher is available




def count_lab_sessions(lab_type, day, time_period):
    """Returns the number of lab sessions already scheduled for a given lab type, day and starting time."""
    return db["Lab Details"].count_documents({
        "Lab_Type": lab_type,
        "Day": day,
        "Time_Slot": time_period
    })


def assign_lab_time_slots_during_timetable(faculty, semester, timetable):
    """
    Assigns lab time slots dynamically **during** timetable generation.
    - Ensures teachers are available.
    - Prioritizes slots after the break.
    - Avoids conflicts with other lab sessions.
    """
    lab_details = list(db["Lab Details"].find({"Faculty": faculty, "Semester": semester, "Time_Slot": None}))

    for lab in lab_details:
        subject_code = lab["Subject_Code"]
        lab_room = lab["Lab_Room"]
        teacher_1 = find_available_teacher(subject_code)
        teacher_2 = find_available_teacher(subject_code, exclude_teacher=teacher_1["name"])

        if not teacher_1:
            print(f"⚠️ No available teacher for lab {subject_code}. Skipping assignment.")
            continue

        assigned = False

        # Try assigning after the break first
        for day in timetable["Timetable"]:
            for slot in reversed(timetable["Time_Slots"]):  # Start from the last available slot
                if not is_slot_occupied(lab_room, day, slot) and not is_teacher_assigned(teacher_1["name"], day, slot):
                    # Assign the lab here
                    lab_entry = {
                        "Time_Slot": slot,
                        "Day": day,
                        "Teacher_1": teacher_1,
                        "Teacher_2": teacher_2 if teacher_2 else None
                    }
                    db["Lab Details"].update_one({"Subject_Code": subject_code}, {"$set": lab_entry})
                    assigned = True
                    print(f"✅ Assigned Lab: {subject_code} on {day} at {slot} in {lab_room}")
                    break
            if assigned:
                break

        if not assigned:
            print(f"⚠️ Could not assign lab for {subject_code}. Consider manual assignment.")


# Function to check if a teacher is available for a given time slot on a specific day
def check_teacher_availability(teacher, day, time_slot, current_tt):
    for day_schedule in current_tt["Timetable"]:
        if day_schedule["Day"] == day:
            for slot in day_schedule["Slots"]:
                if slot["Period"] == time_slot and slot.get("Teacher") == teacher["name"]:
                    return False
    return True


def save_timetable(timetable, faculty, semester, timetable_data):
    db['timetables'].update_one(
        {"Faculty": faculty, "Semester": semester},
        {"$set": {
            "Timetable": timetable,
            "Time_Slots": timetable_data.get("Time_Slots"),
            "Metadata": timetable_data
        }},
        upsert=True
    )


def get_periods(faculty, semester):
    # Fetch timetable from MongoDB
    timetable = db['timetables'].find_one({"Faculty": faculty, "Semester": semester})

    if not timetable:
        print(f"⚠️ No timetable found for Faculty: {faculty}, Semester: {semester}")
        return []  # Return empty list if no timetable is found

    # Extract unique periods from all slots
    periods = list(set(slot['Period'] for day in timetable["Timetable"] for slot in day["Slots"]))

    # Sort periods in chronological order
    def sort_time(period):
        start_time = period.split(" - ")[0]  # Extract the start time (e.g., "09:00 AM")
        return datetime.strptime(start_time, "%I:%M %p")  # Convert to datetime for proper sorting

    periods.sort(key=sort_time)

    print(f"🟢 Retrieved Periods for {faculty}, Semester {semester}: {periods}")
    return periods  # Return sorted list of periods




def read_timetable(faculty, semester):
    # Fetch the timetable data from the database (MongoDB)
    timetable_data = db.timetables.find_one({"Faculty": faculty, "Semester": semester})
    
    if not timetable_data:
        return "No timetable found for the selected faculty and semester."
    
    # Extract the timetable details (it is a list)
    timetable = timetable_data.get("Timetable", [])
    
    return render_template('timetable.html', timetable=timetable, faculty=faculty, semester=semester)



@app.route('/')  # Root URL
@app.route('/index')  # /index URL
def home():
    return render_template('index.html')


@app.route("/get_teacher_routine_v2", methods=["GET"])
def get_teacher_routine_v2():
    teacher_name = request.args.get("name")
    if not teacher_name:
        return jsonify([])

    teacher_routine = list(db["teacherRoutines"].find(
        {"Teacher_Name": teacher_name}, {"_id": 0}
    ))
    
    return jsonify(teacher_routine)


# ✅ Route to delete a teacher's routine
@app.route("/delete_teacher_routine/<teacher_name>")
def delete_teacher_routine(teacher_name):
    teacher_routines_collection.delete_many({"Teacher_Name": teacher_name})
    flash(f"Routine for {teacher_name} deleted successfully.", "success")
    return (url_for("teacher_routine"))


# 1️⃣ Get list of teachers in `teacherRoutines`
@app.route("/get_teachers_routine", methods=["GET"])
def get_teachers_routine():
    teachers = db["teacherRoutines"].distinct("Teacher_Name")  # Fetch unique teacher names
    return jsonify([{"Teacher_Name": t} for t in teachers])

# 2️⃣ Get specific teacher's routine
@app.route("/get_teacher_routine", methods=["GET"])
def get_teacher_routine():
    teacher_name = request.args.get("name")
    if not teacher_name:
        return jsonify([])

    teacher_routine = list(db["teacherRoutines"].find({"Teacher_Name": teacher_name}, {"_id": 0}))
    return jsonify(teacher_routine)

@app.route("/teacher_routine")
def teacher_routine():
    # Get the logged-in user details (modify this part based on your authentication logic)
    user = session.get("user")  # Assuming user data is stored in session
    user_role = session.get("user_role", "Guest")  # Default role is Guest if not found
    faculty_name = session.get("faculty_name", "")

    # ✅ Fetch only unique teacher names
    teacher_routines = list(db["teacherRoutines"].distinct("Name"))

    return render_template(
        "teacherRoutine.html",
        teacher_routines=teacher_routines,  # Pass only teacher names (list)
        user=user,
        user_role=user_role,
        faculty_name=faculty_name
    )



# ✅ Route to view a specific teacher's timetable
@app.route("/teacher_timetable/<teacher_name>")
def view_teacher_timetable(teacher_name):
    teacher_data = teacher_routines_collection.find_one({"Name": teacher_name})
    
    if not teacher_data:
        flash("No timetable available for this teacher.", "warning")
        return redirect(url_for("teacher_routine"))

    # Extract assigned classes
    teacher_classes = teacher_data.get("Classes", [])
    
    # Fetch all available slots and days from a reference timetable
    reference_timetable = db.timetables.find_one({}, {"_id": 0, "Timetable": 1})
    
    if not reference_timetable:
        flash("No reference timetable found!", "danger")
        return redirect(url_for("teacher_routine"))

    reference_timetable = reference_timetable["Timetable"]
    periods = [slot["Period"] for slot in reference_timetable[0]["Slots"]]
    
    # Initialize empty timetable matrix
    timetable_matrix = []
    for day in reference_timetable:
        day_name = day["Day"]
        day_slots = [{"Subject": None} for _ in range(len(periods))]

        # Fill assigned classes in the respective slots
        for assigned_class in teacher_classes:
            if assigned_class["day"] == day_name:
                time_slot = assigned_class["timeslot"]
                if time_slot in periods:
                    slot_index = periods.index(time_slot)
                    day_slots[slot_index] = {
                        "Subject": assigned_class["subject"],
                        "Faculty": assigned_class["faculty"],
                        "Semester": assigned_class["semester"],
                        "Type": assigned_class["type"]
                    }

        timetable_matrix.append({"Day": day_name, "Slots": day_slots})

    return render_template("teacher_timetable.html", teacher_name=teacher_name, timetable=timetable_matrix, periods=periods)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Find the user in the database
        user = db['credentials'].find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            print("Password is correct")  # Debug print
            # Store user role in the session
            session['username'] = user['username']
            session['user_role'] = user.get('role')  # 'Admin' or 'HOD/DHOD'
            session['faculty_name'] = user.get('faculty')  # Faculty assigned to HOD/DHOD users
            session['user'] = {'username': user['username']}
            
            # Use flash to indicate a successful login
            flash('Login successful!', 'success')

            # Redirect based on user role
            if user.get('role') == 'Admin':
                return redirect(url_for('dashboard_admin'))
            elif user['role'] == 'HOD':
                return redirect(url_for('dashboard_hod'))
            
        else:
            flash('Invalid username or password!', 'danger')
            return redirect(url_for('login'))  # Redirect back to login page

    # This block handles GET requests
    response = make_response(render_template('login.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Get data from the request
        full_name = request.form.get('full_name')
        contact_number = request.form.get('contact_number')
        email = request.form.get('email')
        role = request.form.get('role')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        gender = request.form.get('gender')

        # Get faculty only if the role is HOD or DHOD
        faculty = request.form.get('faculty') if role in ['HOD', 'DHOD'] else None

        # Check if all required fields are filled
        if not all([full_name, contact_number, username, password, confirm_password, gender, (faculty if role in ['HOD', 'DHOD'] else True)]):
            return jsonify({"error": "All fields are required!"}), 400
        
        # Validate password match
        if password != confirm_password:
            return jsonify({"error": "Passwords do not match!"}), 400
        
        # Hash the password
        hashed_password = generate_password_hash(password)

        # Check if username already exists
        existing_user = db['credentials'].find_one({"username": username})
        if existing_user:
            return jsonify({"error": "Username already exists!"}), 400

        # Create a user document
        user_data = {
            "full_name": full_name,
            "contact_number": contact_number,
            "email": email,
            "role": role,
            "username": username,
            "password": hashed_password,
            "faculty": faculty,
            "gender": gender,
            "created_at": datetime.now()
        }

        # Store the user data in MongoDB
        db['credentials'].insert_one(user_data)
        flash("Signup successful. Please log in.", "success")
        return redirect(url_for('login'))

    # If the request method is GET, render the signup page
    return render_template('signup.html')



@app.route('/dashboard_admin')
def dashboard_admin():
   # Retrieve user data from the session
    user = session.get('user')  # This should ideally be a dictionary containing user details
    user_role = session.get('user_role')  # Retrieve user role from the session
    faculty_name = session.get('faculty_name')  # Retrieve faculty name for HOD/DHOD users

    # Ensure only HOD and DHOD roles can access this route
    if 'username' in session and user_role == 'Admin':
        return render_template('dashboard_admin.html', user=user, user_role=user_role, faculty_name=faculty_name)

    return redirect(url_for('login'))


@app.route('/dashboard_hod')
def dashboard_hod():
    # Retrieve user data from the session
    user = session.get('user')  # This should ideally be a dictionary containing user details
    user_role = session.get('user_role')  # Retrieve user role from the session
    faculty_name = session.get('faculty_name')  # Retrieve faculty name for HOD/DHOD users

    # Ensure only HOD and DHOD roles can access this route
    if 'username' in session and user_role in ['HOD', 'DHOD']:
        return render_template('dashboard_hod.html', user=user, user_role=user_role, faculty_name=faculty_name)

    return redirect(url_for('login'))


# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))



# Subjects CRUD
@app.route('/subjects', methods=['GET', 'POST'])
def manage_subjects():
    # Get the user's role and faculty from the session
    user_role = session.get('user_role')
    faculty_name = session.get('faculty_name')  # Faculty assigned to HOD/DHOD users

    # Fetch subjects based on user role
    if user_role == 'Admin':
        # Admins can view all subjects
        subjects = list(db['subjects'].find())
    elif user_role in ['HOD', 'DHOD']:
        # HOD/DHOD can only view subjects for their faculty
        subjects = list(db['subjects'].find({"Faculty": faculty_name}))
    else:
        # Redirect unrecognized roles to login
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('login'))

    # Sort subjects by 'Semester' (ascending) and then by 'Name' (alphabetically)
    subjects = sorted(subjects, key=lambda x: (int(x.get('Semester', 0)), x.get('Name', '').lower()))

    # Add a new subject (only allowed for Admin)
    if request.method == 'POST' and user_role == 'Admin':
        subject_data = {
            "Name": request.form['name'],
            "Code": request.form['code'],
            "Faculty": request.form['faculty'],
            "Semester": request.form['semester'],
            "L": int(request.form.get('L', 0)),   # Lecture Hours
            "T": int(request.form.get('T', 0)),   # Tutorial Hours
            "P": int(request.form.get('P', 0)),   # Practical Hours
            "Total": int(request.form.get('Total', 0)),
            "Courses": request.form.get('courses')  # Assuming elective subjects include 'Courses' field
        }
        db['subjects'].insert_one(subject_data)
        flash('Subject added successfully!', 'success')
        return redirect(url_for('manage_subjects'))

    # Pass user information to the template
    user = session.get('user')

    return render_template(
        'manage_subjects.html',
        user=user,
        subjects=subjects,
        user_role=user_role,
        faculty_name=faculty_name
    )



@app.route('/add_subject', methods=['GET', 'POST'])
def add_subject():
    if request.method == 'POST':
        # Fetch form data for courses
        course_names = request.form.getlist('course_name[]')
        course_codes = request.form.getlist('course_code[]')

        # Detailed Debug: Print form data received
        print("Received Course Names:", course_names)  
        print("Received Course Codes:", course_codes)  

        # Determine if "Elective" type is selected
        subject_type = request.form.get('Type')
        if subject_type == "Elective":
            # Ensure both lists are populated before processing
            if not course_names or not course_codes:
                print("No elective courses received; check form submission.")
                flash("Error: No elective courses were submitted.", "error")
                return redirect(url_for('add_subject'))

            # Create list of elective courses if both lists have values
            courses = [{"Name": name, "Code": code} for name, code in zip(course_names, course_codes) if name and code]
        else:
            # For "Regular" type, no elective courses are needed
            courses = []  # Set courses to an empty list if regular type

        # Construct new subject data with courses field based on type
        new_subject = {
            "Name": request.form['Name'],
            "Code": request.form['Code'],
            "L": float(request.form.get('L', 0)),
            "T": float(request.form.get('T', 0)),
            "P": float(request.form.get('P', 0)),
            "Total": float(request.form.get('Total', 0)),
            "Semester": int(request.form['Semester']),
            "Faculty": request.form['Faculty'],
            "Courses": courses
        }

        # Insert the new subject into the database
        db.subjects.insert_one(new_subject)
        flash("Subject added successfully", "success")
        return redirect(url_for('manage_subjects'))

    # Handle GET request for the form
    user = session.get('user')
    user_role = session.get('user_role')
    faculty_name = session.get('faculty_name')

    return render_template('add_subject.html', faculty_name=faculty_name, user=user, user_role=user_role)


@app.route('/edit_subject/<object_id>', methods=['GET', 'POST'])
def edit_subject(object_id):
    user = session.get('user')
    subject_id = ObjectId(object_id)  # Convert object_id from string to ObjectId

    if request.method == 'POST':
        # Prepare the updated subject details from the form
        updated_subject = {
            "Name": request.form.get("Name"),
            "Code": request.form.get("Code"),
            "L": float(request.form.get("L") or 0),  # Use 0 if empty
            "T": float(request.form.get("T") or 0),  # Use 0 if empty
            "P": float(request.form.get("P") or 0),  # Use 0 if empty
            "Total": float(request.form.get("Total") or 0),  # Use 0 if empty
            "Semester": int(request.form.get("Semester") or 0),  # Handle semester accordingly
            "Faculty": request.form.get("Faculty"),
            "Type": request.form.get("Type"),
            # Store courses as a list of dictionaries with 'Name' and 'Code'
            "Courses": [
                {"Name": name, "Code": code}
                for name, code in zip(request.form.getlist("course_name[]"), request.form.getlist("course_code[]"))
            ]
        }

        # Update subject based on ObjectId
        db['subjects'].update_one({"_id": subject_id}, {"$set": updated_subject})
        flash("Subject updated successfully!", "success")
        return redirect(url_for('manage_subjects'))

    # GET request: Fetch subject details by ObjectId
    subject = db['subjects'].find_one({"_id": subject_id})  # Query by ObjectId
    if not subject:
        flash("Subject not found.", "error")
        return redirect(url_for('manage_subjects'))
    
    return render_template('edit_subject.html', subject_id=subject_id, subject=subject, user=user)



@app.route('/delete_subject/<subject_id>')
def delete_subject(subject_id):
    try:
        # Try to delete by _id (subject_id)
        result = db.subjects.delete_one({"_id": ObjectId(subject_id)})
        if result.deleted_count > 0:
            flash("Subject deleted successfully", "danger")
        else:
            flash("Subject not found or already deleted", "warning")
    except Exception as e:
        flash("An error occurred: " + str(e), "warning")

    return redirect(url_for('manage_subjects'))


@app.route('/manage_users')
def manage_users():
    user = session.get('user')
    user_role = session.get('user_role')  # Role of the logged-in user (e.g., Admin, HOD, DHOD)
    faculty_name = session.get('faculty_name')  # Faculty of HOD/DHOD users

    # Get user data
    users = list(db['credentials'].find())
    users = [{**user, "_id": str(user["_id"])} for user in users]

    # Check role to fetch appropriate data
    if user_role == 'Admin':
        # Admin views all teachers and subjects
        teachers = list(db['teachers'].find())
    else:
        # HOD/DHOD views only data related to their faculty
        faculty_subjects = db['subjects'].find({"faculty": faculty_name})
        faculty_subject_codes = [subject['Code'] for subject in faculty_subjects if 'Code' in subject]

        # Filter teachers by matching their Course_Code with subject codes of the faculty
        teachers = list(db['teachers'].find({
            "Course_Code": {"$in": faculty_subject_codes}
        }))
    
    # Render page with data
    return render_template('manage_users.html',user=user, users=users, teachers=teachers, user_role=user_role, faculty_name=faculty_name)

# Route for AJAX faculty filter (only for Admin)
@app.route('/filter_by_faculty', methods=['POST'])
def filter_by_faculty():
    selected_faculty = request.json.get('faculty')
    
    # Retrieve teachers and subjects based on selected faculty
    if selected_faculty == 'all':
        teachers = list(db['teachers'].find())
        subjects = list(db['subjects'].find())
    else:
        faculty_subjects = db['subjects'].find({"faculty": selected_faculty})
        faculty_subject_codes = [subject['Code'] for subject in faculty_subjects]
        
        teachers = list(db['teachers'].find({
            "Course_Code": {"$in": faculty_subject_codes}
        }))
        subjects = list(db['subjects'].find({"faculty": selected_faculty}))
    
    # Convert MongoDB documents to JSON serializable format
    teachers = [{**teacher, "_id": str(teacher["_id"])} for teacher in teachers]
    subjects = [{**subject, "_id": str(subject["_id"])} for subject in subjects]
    
    return jsonify({
        "teachers": teachers,
        "subjects": subjects
    })

@app.route('/edit_user/<user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    # Find user by ID
    user = db['credentials'].find_one({"_id": ObjectId(user_id)})
    
    if request.method == 'POST':
        # Get updated form data
        updated_data = {
            "full_name": request.form['full_name'],
            "contact_number": request.form['contact_number'],
            "email": request.form['email'],
            "username": request.form['username'],
            "gender": request.form['gender'],
            "role": request.form['role'],
            "faculty": request.form['faculty'] if request.form['role'] in ['HOD', 'DHOD'] else None

        }
        
        # Update user in MongoDB
        db['credentials'].update_one({"_id": ObjectId(user_id)}, {"$set": updated_data})
        flash("User details updated successfully", "success")
        return redirect(url_for('manage_users'))  # Redirect back to user management page

    # Render edit form with current user data
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<user_id>', methods=['GET'])
def delete_user(user_id):
    try:
        # Delete the user from the MongoDB collection
        db['credentials'].delete_one({"_id": ObjectId(user_id)})
        flash("User deleted successfully", "success")
    except Exception as e:
        flash("An error occurred while deleting the user: " + str(e), "error")
    
    # Redirect back to the user management page
    return redirect(url_for('manage_users'))

@app.route('/add_teacher', methods=['GET', 'POST'])
def process_add_teacher():
    try:
        if request.method == 'POST':
            name = request.form['name']
            teacher_type = request.form['type']
            designation = request.form['designation']

             # Check if the user selected a custom designation and retrieve its value
            if designation == "Custom":
                custom_designation = request.form.get('custom_designation')
                if custom_designation:  # Only overwrite if a custom designation is provided
                    designation = custom_designation

        
            # Debugging print statements
            print(f"Received Name: {name}")
            print(f"Teacher Type: {teacher_type}")
            print(f"Designation: {designation}")

            # Get course codes
            course_codes = request.form.getlist('course_code[]')
            print(f"Course Codes: {course_codes}")

            # Initialize teacher data with common fields
            teacher_data = {
                "name": name,
                "type": teacher_type,
                "designation": designation,
                "Course_Code": course_codes,
                "workload": 0
            }

            # Only add availability if the teacher is part-time
            if teacher_type == "Part Time":
                # Collect availability days and times
                availability_days = request.form.getlist('availability[day][]')
                availability_times = request.form.getlist('availability[time][]')
                print(f"Availability Days: {availability_days}")
                print(f"Availability Times: {availability_times}")

                # Prepare availability as a dictionary
                availability = {}
                for day, time in zip(availability_days, availability_times):
                    if day not in availability:
                        availability[day] = []
                    availability[day].append(time)

                teacher_data["availability"] = availability
                print(f"Availability: {availability}")

            # Insert teacher data into the database
            db['teachers'].insert_one(teacher_data)
            print("Teacher data inserted successfully.")

            # Flash success message and redirect
            flash("Teacher added successfully", "success")
            return redirect(url_for('manage_teachers'))  # Ensure this route exists or replace it

        user = session.get('user')
        user_role = session.get('user_role')  # Role of the logged-in user (e.g., Admin, HOD, DHOD)
        faculty_name = session.get('faculty_name')  # Faculty of HOD/DHOD users
        teacher = {}  # Initialize 'teacher' as an empty dictionary for new entries

        # Render form if GET request
        return render_template('add_teacher.html',user=user, user_role=user_role, faculty_name=faculty_name, teacher=teacher # Pass an empty dictionary if no specific teacher is being edited
)
    except Exception as e:
        # Print full error traceback to console and flash error message
        print("Error occurred:", e)
        traceback.print_exc()
        flash("An error occurred while adding the teacher. Please try again.", "error")
        return redirect(url_for('add_teacher'))




WORKLOAD_LIMITS = {
    "CEO": 4,
    "Principal": 6,
    "Vice Principal": 8,
    "HOD": 14,
    "DHOD": 16,
    "Teacher": 20
}

def calculate_workload(L, T, P):
    """
    Formula:
    - Theory (L + T) = 1x per hour
    - Practical (P) = 0.8x per hour
    """
    return (L + T) + (P * 0.8)


@app.route('/manage_teachers')
def manage_teachers():
    """
    Fetches all teachers and displays them in the UI.
    """
    user = session.get('user')
    user_role = session.get('user_role')
    faculty_name = session.get('faculty_name')

    # Fetch all teachers from the database
    all_teachers = list(teachers_collection.find().sort('name', 1))

    full_time_teachers = [t for t in all_teachers if t.get("type", "").lower() == "full time"]
    part_time_teachers = [t for t in all_teachers if t.get("type", "").lower() == "part time"]

    return render_template(
        'manage_teachers.html',
        full_time_teachers=full_time_teachers,
        part_time_teachers=part_time_teachers,
        user_role=user_role, faculty_name=faculty_name, user=user
    )


@app.route('/edit_teacher/<teacher_id>', methods=['GET', 'POST'])
def edit_teacher(teacher_id):
    teacher = db.teachers.find_one({"_id": ObjectId(teacher_id)})
    user = session.get('user')

    if request.method == 'POST':
        # Retrieve values from the form
        name = request.form.get('name')
        teacher_type = request.form.get('type')
        designation = request.form.get('designation')

        if not designation:
            flash("Designation is required.", 'danger')
            return redirect(url_for('edit_teacher', teacher_id=teacher_id))

        if designation == 'Custom':
            custom_designation = request.form.get('custom_designation', '').strip()
            if custom_designation:
                designation = custom_designation
            else:
                flash("Custom designation cannot be empty.", 'danger')
                return redirect(url_for('edit_teacher', teacher_id=teacher_id))

        course_codes = request.form.getlist('course_code[]')

        # Handle availability data for part-time teachers
        availability = {}
        if teacher_type == 'Part Time':
            days = request.form.getlist('availability[day][]')
            times = request.form.getlist('availability[time][]')

            for i, day in enumerate(days):
                if day in availability:
                    availability[day].append(times[i])
                else:
                    availability[day] = [times[i]]

            # Sort availability by day of the week (Sunday to Saturday)
            day_order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            availability = {day: availability[day] for day in day_order if day in availability}

        # Update teacher information in the database
        db.teachers.update_one(
            {"_id": ObjectId(teacher_id)},
            {"$set": {
                "name": name,
                "type": teacher_type,
                "designation": designation,
                "Course_Code": course_codes,
                "availability": availability if teacher_type == 'Part Time' else None
            }}
        )
        flash('Teacher updated successfully!', 'success')
        return redirect(url_for('manage_teachers'))

    return render_template('edit_teacher.html', teacher=teacher, user=user)




# DELETE: Remove a teacher
@app.route('/delete_teacher/<teacher_id>')
def delete_teacher(teacher_id):
    db['teachers'].delete_one({"_id": ObjectId(teacher_id)})
    flash("Teacher deleted successfully", "success")
    return redirect(url_for('manage_teachers'))

# Route for the form page
@app.route('/add_teacher_page')
def add_teacher_page():
    user = session.get('user')
    user_role = session.get('user_role')  # This should be set based on login data
    faculty_name = session.get('faculty_name')  # Faculty name for HOD/DHOD users
    teacher = {}
    return render_template('add_teacher.html', user=user, user_role=user_role, faculty_name=faculty_name, teacher=teacher)

# Route to process form submission (assuming you have this)
@app.route('/add_teacher', methods=['POST'])
def add_teacher():
    # Your form handling logic here
    return redirect(url_for('manage_teachers'))

@app.route('/navbar')
def navbar():
    # Your form handling logic here
    return render_template('navbar.html')

# Route to show the list of generated timetables
@app.route('/manage_routines_page')
def manage_routines():
    user = session.get('user')
    user_role = session.get('user_role')  # This should be set based on login data
    faculty_name = session.get('faculty_name')  # Faculty name for HOD/DHOD users
    # Fetch all generated routines from the 'timetables' collection
    routines = db['timetables'].find()  # This returns all documents in the collection
    return render_template('manage_routines.html', routines=routines, user=user, user_role=user_role, faculty_name=faculty_name)


@app.route('/view_timetable', methods=['GET'])
def view_timetable():
    """
    Fetches the timetable and ensures lab assignments from 'Lab Details' are mapped correctly.
    """
    faculty = request.args.get('faculty')  
    semester = request.args.get('semester')  

    if not faculty or not semester:
        return "Faculty and semester are required", 400

    # ✅ Fetch timetable from MongoDB
    timetable = db['timetables'].find_one({"Faculty": faculty, "Semester": int(semester)})
    if not timetable:
        print(f"⚠️ No timetable found for {faculty}, Semester {semester}")
        return redirect(url_for('manage_routines'))

    # ✅ Fetch all lab details
    lab_details = list(db["Lab Details"].find())

    # ✅ Create mapping (Day, Period) → Lab Data
    lab_map = {}
    for lab in lab_details:
        if "Time_Slot" not in lab or "Day" not in lab:
            continue  

        lab_day = lab["Day"].strip().title()  
        time_slots = lab["Time_Slot"].split(" - ")  
        
        for i in range(0, len(time_slots) - 1, 2):  
            period_1 = f"{time_slots[i]} - {time_slots[i + 1]}"  
            lab_key = (lab_day, period_1)

            if lab_key not in lab_map:
                lab_map[lab_key] = []  
            
            lab_map[lab_key].append({
                "Subject": lab.get('Subject_Name', 'Unknown'),
                "Teacher": lab.get("Teacher", "Unknown"),
                "Lab_Room": lab.get("Lab_Room", "Unknown")
            })

    # ✅ Assign lab details correctly in the timetable
    for day in timetable["Timetable"]:
        day["Day"] = day["Day"].strip().title()  
        for slot in day["Slots"]:
            lab_key = (day["Day"], slot["Period"])  
            if lab_key in lab_map:
                slot["Lab_Classes"] = lab_map[lab_key]  

    # ✅ Sort Days in Correct Order
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    timetable["Timetable"].sort(key=lambda d: day_order.index(d["Day"]) if d["Day"] in day_order else len(day_order))

    # ✅ Extract unique periods for table headers
    periods = list(dict.fromkeys([slot['Period'] for day in timetable['Timetable'] for slot in day['Slots']]))

    # ✅ Generate a mapping of subject codes to their names
    subjects = list(db["subjects"].find({}, {"_id": 0}))  # Fetch all subjects
    subject_names = {s["Code"]: s["Name"] for s in subjects if "Code" in s and "Name" in s}

    return render_template('timetable.html', timetable=timetable, faculty=faculty, semester=semester, periods=periods, subject_names=subject_names)



@app.route('/delete_routine/<faculty>/<int:semester>', methods=['GET'])
def delete_routine(faculty, semester):
    try:
        # Delete the timetable from the database
        result = db['timetables'].delete_one({
            "Faculty": faculty,
            "Semester": semester
        })

        if result.deleted_count > 0:
            return redirect(url_for('manage_routines'))  # Redirect to the page that lists routines
        else:
            return "Error: Routine not found for the given faculty and semester."

    except Exception as e:
        print(f"Error while deleting routine: {e}")
        return "Error occurred while deleting the routine."

if __name__ == '__main__':
    app.run(debug=True)
