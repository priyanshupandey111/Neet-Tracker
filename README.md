# NEET Study Hub V3

Student + Teacher NEET study tracker.

## Features
- Student registration/login
- Add Study, Revision, MCQ and Test tasks
- Date-based study plan
- Tick completed studies
- Student progress percentage
- Teacher login and student list
- Teacher can open each student's study history
- SQLite database

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

Teacher demo:
- Email: teacher@neet.local
- Password: teacher123

For public deployment, use a Python hosting service and set a strong SECRET_KEY.
For production, replace the demo password storage with password hashing and use HTTPS.
