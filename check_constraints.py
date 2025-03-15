from pymongo import MongoClient
import pandas as pd

# Connect to MongoDB
client = MongoClient("mongodb+srv://major:project@majorproject.nrvy0xw.mongodb.net/")
db = client["Project1"]

# Fetch collections
lab_details = list(db["Lab Details"].find({}, {"_id": 0}))  # Exclude ObjectId for readability
timetables = list(db["timetables"].find({}, {"_id": 0}))

# Convert to DataFrames for analysis
lab_df = pd.DataFrame(lab_details)
timetable_df = pd.DataFrame(timetables)

# Ensure columns exist
lab_df.fillna("N/A", inplace=True)
timetable_df.fillna("N/A", inplace=True)

# 1️⃣ Check for Field Name Mismatches
expected_lab_fields = {"Subject_Code", "Subject_Name", "Lab_Room", "Teacher", "Time_Slot", "Day"}
actual_lab_fields = set(lab_df.columns)

expected_timetable_fields = {"Faculty", "Semester", "Timetable"}
actual_timetable_fields = set(timetable_df.columns)

lab_field_mismatches = expected_lab_fields - actual_lab_fields
timetable_field_mismatches = expected_timetable_fields - actual_timetable_fields

# 2️⃣ Check for Time Slot Format Issues
def check_time_format(time_str):
    try:
        pd.to_datetime(time_str, format="%I:%M %p")  # 12-hour format
        return True
    except ValueError:
        return False

lab_time_issues = lab_df[~lab_df["Time_Slot"].apply(check_time_format)] if "Time_Slot" in lab_df else pd.DataFrame()
timetable_time_issues = []
for timetable in timetables:
    for day in timetable.get("Timetable", []):
        for slot in day.get("Slots", []):
            if not check_time_format(slot.get("Period", "")):
                timetable_time_issues.append(slot.get("Period", ""))

# 3️⃣ Check for Constraint Violations
# - Check if a teacher is assigned multiple subjects in the same semester
teacher_subjects = {}
teacher_violations = []

for timetable in timetables:
    semester = timetable.get("Semester")
    for day in timetable.get("Timetable", []):
        for slot in day.get("Slots", []):
            teacher_name = slot.get("Teacher")
            subject_code = slot.get("Subject", "").split("(")[-1].replace(")", "").strip()

            if teacher_name and subject_code:
                if (teacher_name, semester) in teacher_subjects:
                    if teacher_subjects[(teacher_name, semester)] != subject_code:
                        teacher_violations.append((teacher_name, semester, subject_code))
                else:
                    teacher_subjects[(teacher_name, semester)] = subject_code

# - Check if a lab room is booked multiple times at the same time
lab_conflicts = lab_df.groupby(["Lab_Room", "Day", "Time_Slot"]).size()
lab_conflicts = lab_conflicts[lab_conflicts > 1].reset_index(name="Conflicts")

# - Check if practical sessions (P=3) are split correctly
practical_subjects = db["subjects"].find({"P": 3}, {"Code": 1, "Name": 1})
practical_issues = []
for subject in practical_subjects:
    subject_code = subject["Code"]
    sessions = lab_df[lab_df["Subject_Code"] == subject_code]
    if len(sessions) < 2:
        practical_issues.append(subject_code)

# Display results
issues_summary = {
    "Lab Field Mismatches": lab_field_mismatches,
    "Timetable Field Mismatches": timetable_field_mismatches,
    "Lab Time Format Issues": lab_time_issues.to_dict(orient="records"),
    "Timetable Time Format Issues": timetable_time_issues,
    "Teacher Constraint Violations": teacher_violations,
    "Lab Room Conflicts": lab_conflicts.to_dict(orient="records"),
    "Practical Sessions Issues (P=3 not split)": practical_issues
}

# Print summary of issues
for key, value in issues_summary.items():
    print(f"🔎 {key}:")
    print(value)
    print("-" * 40)
