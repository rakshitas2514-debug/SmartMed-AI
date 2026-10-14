import os, re, secrets
from datetime import datetime, date, timedelta
from collections import Counter
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
UPLOAD_DIR = os.path.join(INSTANCE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SMARTMED_SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(INSTANCE_DIR, "smartmed.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {"txt", "csv", "pdf"}
STOP_WORDS = set("""a an the and or but to for of in on at with from by is are was were be been being i me my we our you your they them it this that these those what how can could should would do does did have has had want need please tell explain give make help about into than then also eat eating food foods diet meal meals plan healthy health weight lose gain increase reduce lower higher""".split())

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    health_entries = db.relationship("HealthEntry", backref="user", lazy=True, cascade="all, delete-orphan")
    fitness_entries = db.relationship("FitnessEntry", backref="user", lazy=True, cascade="all, delete-orphan")
    daily_logs = db.relationship("DailyLog", backref="user", lazy=True, cascade="all, delete-orphan")
    point_transactions = db.relationship("PointTransaction", backref="user", lazy=True, cascade="all, delete-orphan")

    @property
    def points(self):
        return sum(t.points for t in self.point_transactions)

class HealthEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(40), default="health")
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FitnessEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    goal = db.Column(db.String(80), nullable=False)
    details = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    log_date = db.Column(db.Date, default=date.today, nullable=False)
    water_glasses = db.Column(db.Integer, default=0)
    sleep_hours = db.Column(db.Float, default=0)
    steps = db.Column(db.Integer, default=0)
    mood = db.Column(db.String(40), default="Okay")
    notes = db.Column(db.Text, default="")
    __table_args__ = (db.UniqueConstraint("user_id", "log_date", name="unique_user_log_date"),)

class PointTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def add_points(user, points, reason, once_key=None):
    if once_key:
        today_prefix = date.today().isoformat()
        if any(t.reason == f"{once_key}:{today_prefix}" for t in user.point_transactions):
            return False
        reason = f"{once_key}:{today_prefix}"
    db.session.add(PointTransaction(user_id=user.id, points=points, reason=reason))
    return True

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def tokenize(text):
    # Lightweight offline NLP: normalize punctuation, lowercase and remove common stop words.
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]{1,}", (text or "").lower())
    return [w for w in words if w not in STOP_WORDS]

def has_any(text, terms):
    low = (text or "").lower()
    return any(term in low for term in terms)

def safety_note(text):
    urgent = ["chest pain", "can't breathe", "cannot breathe", "difficulty breathing", "face drooping",
              "weakness on one side", "severe bleeding", "suicidal", "overdose", "unconscious"]
    if has_any(text, urgent):
        return ("URGENT SAFETY NOTE: this may describe an emergency. Contact your local emergency number "
                "or seek emergency medical care now. Do not rely on this website for emergency assessment.")
    return ""

def offline_health_answer(question):
    q = (question or "").strip()
    low = q.lower()
    if not q:
        return "Please enter a health question so I can offer general information."
    urgent = safety_note(q)
    if urgent:
        return urgent + "\n\nI can provide general educational information, but I cannot diagnose or determine the cause online."
    sections = []
    if has_any(low, ["fever", "temperature", "hot body"]):
        sections += ["FEVER — GENERAL GUIDANCE\n• Rest and drink fluids regularly.\n• If you use a thermometer, record the temperature and time.\n• Seek medical advice for persistent or worsening fever, dehydration, rash, severe headache, confusion, or if the person is a very young infant."]
    if has_any(low, ["headache", "migraine"]):
        sections += ["HEADACHE — GENERAL GUIDANCE\n• Rest in a quiet place, drink water, and consider whether skipped meals, sleep changes, or screen strain may contribute.\n• A sudden, extremely severe headache, or headache with weakness, confusion, fainting, fever with stiff neck, or vision loss needs urgent medical assessment."]
    if has_any(low, ["cough", "cold", "sore throat", "flu"]):
        sections += ["COUGH / COLD — GENERAL GUIDANCE\n• Rest, fluids, and warm drinks may help comfort.\n• Avoid smoke and other irritants.\n• Seek care for breathing difficulty, chest pain, dehydration, symptoms that worsen, or symptoms that persist."]
    if has_any(low, ["stomach", "diarrhea", "diarrhoea", "vomit", "nausea", "acidity"]):
        sections += ["DIGESTIVE SYMPTOMS — GENERAL GUIDANCE\n• Take small, frequent sips of fluid; oral rehydration solution may be useful for fluid loss.\n• Eat simple foods as tolerated and avoid foods that clearly worsen symptoms.\n• Seek care for blood in stool/vomit, severe pain, repeated vomiting, dehydration, or persistent symptoms."]
    if has_any(low, ["sleep", "insomnia", "tired", "fatigue"]):
        sections += ["SLEEP / TIREDNESS — GENERAL GUIDANCE\n• Keep a consistent sleep and wake time, reduce late caffeine, and create a calm, dark sleeping environment.\n• Persistent or severe tiredness can have many causes; consider a clinician if it continues or affects daily life."]
    if has_any(low, ["stress", "anxiety", "panic", "sad", "depressed", "mood"]):
        sections += ["STRESS / MOOD — GENERAL GUIDANCE\n• Try a slow breathing exercise, a short walk, regular meals, and talking with someone you trust.\n• If distress is persistent, interferes with daily life, or you feel unsafe, seek professional support. If you may harm yourself, contact emergency services or a crisis service now."]
    if has_any(low, ["blood pressure", "bp", "cholesterol", "diabetes", "blood sugar"]):
        sections += ["LONG-TERM HEALTH — GENERAL GUIDANCE\n• Follow your clinician's monitoring and treatment plan; do not stop or change prescribed medicines based on this website.\n• Balanced meals, regular activity, sleep, and taking prescribed medicines as directed can support health.\n• Bring home readings and questions to a qualified healthcare professional."]
    if not sections:
        sections.append("GENERAL HEALTH INFORMATION\n• Describe when the concern started, how often it happens, what makes it better or worse, and any other symptoms.\n• General steps that support health include regular meals, hydration, sleep, movement appropriate to your ability, and avoiding tobacco.\n• For a new, persistent, worsening, or concerning symptom, contact a qualified healthcare professional.")
    sections.append("Important: this is an offline rule-based educational assistant, not a medical diagnosis. If symptoms are severe or worsening, seek professional care.")
    return "\n\n".join(sections)

def offline_food_answer(question):
    q = (question or "").strip()
    low = q.lower()
    if not q:
        return "Tell me your food question, available ingredients, dietary preferences, and goal (for example, balanced eating or weight gain)."
    foods = []
    food_vocab = ["rice", "sambar", "egg", "eggs", "idli", "dosa", "chapati", "roti", "dal", "lentil", "banana",
                  "curd", "yogurt", "milk", "oats", "chicken", "fish", "tofu", "paneer", "beans", "vegetable",
                  "spinach", "potato", "peanut", "nuts", "bread", "apple", "fruit"]
    for f in food_vocab:
        if re.search(r"\b" + re.escape(f) + r"\b", low):
            foods.append(f)
    goal_gain = has_any(low, ["gain weight", "weight gain", "put on weight", "bulk"])
    goal_loss = has_any(low, ["lose weight", "weight loss", "reduce weight", "fat loss"])
    goal_diabetes = has_any(low, ["diabetes", "blood sugar"])
    lines = ["Here is a practical starting point based on your question."]
    if foods:
        lines.append("Foods I noticed in your message: " + ", ".join(dict.fromkeys(foods)) + ".")
        lines.append("You can combine a grain such as rice, dosa or chapati with protein (dal, beans, eggs, paneer, tofu, fish or chicken if you eat it) and vegetables. Add fruit or curd/yogurt if suitable for you.")
    if goal_gain:
        lines.append("WEIGHT-GAIN APPROACH\n• Eat regular meals and add nourishing snacks rather than relying only on sugary foods.\n• Include protein with meals and energy-rich foods such as nuts, seeds, peanut butter, dairy or suitable alternatives.\n• Example day: breakfast—idli/dosa with sambar and an egg or another protein; lunch—rice, dal/sambar, vegetables and curd; snack—banana with yogurt or nuts; dinner—chapati or rice with beans/paneer/egg and vegetables.")
    elif goal_loss:
        lines.append("WEIGHT-LOSS APPROACH\n• Aim for gradual, sustainable changes; avoid crash diets.\n• Fill about half the plate with vegetables where available, include a protein source, and choose a satisfying portion of rice/chapati or another grain.\n• Example day: breakfast—idli with sambar; lunch—moderate rice portion with dal, vegetables and curd; snack—fruit; dinner—chapati with vegetables and protein.")
    else:
        lines.append("BALANCED-MEAL APPROACH\n• A simple plate guide: about half vegetables/fruit, one quarter protein foods, and one quarter grains or starchy foods, adjusted to your needs and culture.\n• Example Indian-style day: breakfast—idli/dosa with sambar; lunch—rice or chapati with dal/beans, vegetables and curd; snack—fruit or a handful of nuts; dinner—vegetables plus a protein food and a grain.")
    if goal_diabetes:
        lines.append("For diabetes or blood-sugar concerns, carbohydrate portions and medication needs vary. Pair carbohydrate foods with protein/fibre, monitor as your clinician recommends, and ask your clinician or dietitian for a plan specific to your medicines and readings.")
    lines.append("Please tell me your age range, goal, food preferences, allergies, budget, and any clinician-prescribed dietary restrictions for more relevant suggestions. This is general information, not a personalized medical diet prescription.")
    return "\n\n".join(lines)

def offline_fitness_answer(goal, details):
    low = (goal + " " + details).lower()
    if has_any(low, ["injury", "pain", "pregnant", "heart condition", "chest pain", "dizzy"]):
        safety = "Because you mentioned a possible health concern, check with a qualified clinician before starting or changing exercise. Stop and seek urgent care for chest pain, fainting, or severe breathlessness.\n\n"
    else:
        safety = ""
    if has_any(low, ["weight gain", "muscle", "strength", "bulk"]):
        plan = "STARTER STRENGTH PLAN\n• 2–3 non-consecutive days per week: chair squats, wall/incline push-ups, hip hinges, rows with a safe resistance band, and a simple core exercise.\n• Start with 1–2 sets of 8–12 comfortable repetitions, rest between sets, and increase gradually.\n• Eat regular meals with protein-containing foods and sleep consistently."
    elif has_any(low, ["weight loss", "fat loss", "lose weight"]):
        plan = "SUSTAINABLE ACTIVITY PLAN\n• Build toward regular walking or another activity you enjoy, starting with a duration you can comfortably manage.\n• Add 2 days per week of basic strength work if appropriate.\n• Pair activity with sustainable food habits and sleep; avoid extreme exercise or crash diets."
    elif has_any(low, ["yoga", "flexibility", "stretch"]):
        plan = "GENTLE YOGA / MOBILITY PLAN\n• Begin with 5–10 minutes of comfortable breathing, cat-cow, supported child's pose if comfortable, gentle standing stretches, and a relaxed cooldown.\n• Never force a stretch or continue through sharp pain; modify poses to your mobility."
    elif has_any(low, ["walk", "walking", "steps"]):
        plan = "WALKING PLAN\n• Start with a comfortable 10-minute walk if safe for you, then gradually add a few minutes as tolerated.\n• Use supportive footwear, stay hydrated, and choose a safe route.\n• If you have been inactive or have a medical condition, ask a clinician what level is suitable."
    else:
        plan = "GENERAL BEGINNER PLAN\n• 3 days per week: 10–20 minutes of comfortable walking or another accessible activity.\n• 2 non-consecutive days: chair squats, wall push-ups, and gentle mobility, 1–2 easy sets.\n• Include rest days and increase duration or difficulty gradually."
    return safety + plan + "\n\nThis is a general starter template, not medical clearance. Adapt it to your ability and seek professional guidance if unsure."

def extract_report_text(path, extension):
    try:
        if extension == "txt" or extension == "csv":
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(25000)
        if extension == "pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(path)
                return "\n".join((page.extract_text() or "") for page in reader.pages)[:25000]
            except ImportError:
                return "PDF text extraction needs the optional package pypdf. Install it with: pip install pypdf"
    except Exception as exc:
        return "Could not read this file. Please try a text-based PDF, TXT or CSV file. Technical detail: " + str(exc)
    return "Unsupported file type."

def summarize_report(text):
    if not text.strip():
        return ("No readable text was extracted. The PDF may be scanned as an image. This version does not include OCR. "
                "Try a text-based PDF or copy and paste the report text.")
    numeric = re.findall(r"(?im)^\s*([A-Za-z][A-Za-z0-9 /_-]{1,40})\s*[:=]\s*([<>]?\s*-?\d+(?:\.\d+)?)\s*([A-Za-z/%µμ^0-9.]*)", text)
    out = ["REPORT TEXT REVIEW\nI extracted text from the file. This offline tool cannot validate the report's units, reference ranges, or clinical context."]
    if numeric:
        out.append("Possible name/value pairs found:")
        for name, value, unit in numeric[:20]:
            out.append(f"• {name.strip()}: {value.strip()} {unit.strip()}".rstrip())
    else:
        out.append("No simple name/value lines were detected. Review the extracted text below and discuss the original report with a clinician.")
    out.append("Do not use this simple text scan to diagnose yourself or change medication. Reference ranges depend on the laboratory, units, age and clinical context.")
    out.append("\nEXTRACTED TEXT (first part):\n" + text[:5000])
    return "\n".join(out)

def get_or_create_log(user, log_date=None):
    log_date = log_date or date.today()
    log = DailyLog.query.filter_by(user_id=user.id, log_date=log_date).first()
    if not log:
        log = DailyLog(user_id=user.id, log_date=log_date)
        db.session.add(log)
        db.session.commit()
    return log

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(username) < 2 or "@" not in email or len(password) < 8:
            flash("Enter a username, valid email, and password of at least 8 characters.", "error")
        elif User.query.filter((User.username == username) | (User.email == email)).first():
            flash("That username or email is already registered.", "error")
        else:
            user = User(username=username, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            add_points(user, 5, "Welcome to SmartMed AI")
            db.session.commit()
            flash("Account created. Welcome to SmartMed AI!", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    recent_health = HealthEntry.query.filter_by(user_id=current_user.id).order_by(HealthEntry.created_at.desc()).limit(3).all()
    recent_fitness = FitnessEntry.query.filter_by(user_id=current_user.id).order_by(FitnessEntry.created_at.desc()).limit(3).all()
    log = DailyLog.query.filter_by(user_id=current_user.id, log_date=date.today()).first()
    return render_template("dashboard.html", recent_health=recent_health, recent_fitness=recent_fitness, today_log=log)

@app.route("/health", methods=["GET", "POST"])
@login_required
def health():
    answer = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = offline_health_answer(question)
        if question:
            db.session.add(HealthEntry(user_id=current_user.id, category="health question", question=question, answer=answer))
            add_points(current_user, 2, "Asked a health question")
            db.session.commit()
    return render_template("health.html", answer=answer, question=question)

@app.route("/food", methods=["GET", "POST"])
@login_required
def food():
    answer = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = offline_food_answer(question)
        if question:
            db.session.add(HealthEntry(user_id=current_user.id, category="food", question=question, answer=answer))
            add_points(current_user, 2, "Used food guidance")
            db.session.commit()
    return render_template("food.html", answer=answer, question=question)

@app.route("/fitness", methods=["GET", "POST"])
@login_required
def fitness():
    answer = None
    goal = "General fitness"
    details = ""
    if request.method == "POST":
        goal = request.form.get("goal", "General fitness").strip()
        details = request.form.get("details", "").strip()
        answer = offline_fitness_answer(goal, details)
        db.session.add(FitnessEntry(user_id=current_user.id, goal=goal, details=details, answer=answer))
        add_points(current_user, 2, "Created a fitness plan")
        db.session.commit()
    history = FitnessEntry.query.filter_by(user_id=current_user.id).order_by(FitnessEntry.created_at.desc()).limit(5).all()
    return render_template("fitness.html", answer=answer, goal=goal, details=details, history=history)

@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    result = None
    extracted = None
    if request.method == "POST":
        pasted = request.form.get("report_text", "").strip()
        file = request.files.get("report_file")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Upload a TXT, CSV or text-based PDF file (maximum 10 MB).", "error")
            else:
                filename = secure_filename(file.filename)
                unique_name = f"user{current_user.id}_{secrets.token_hex(8)}_{filename}"
                path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
                file.save(path)
                extracted = extract_report_text(path, filename.rsplit(".", 1)[1].lower())
        if pasted:
            extracted = (extracted + "\n\n" if extracted else "") + pasted[:25000]
        if extracted:
            result = summarize_report(extracted)
            db.session.add(HealthEntry(user_id=current_user.id, category="report review", question="Uploaded/pasted health report", answer=result))
            add_points(current_user, 3, "Reviewed report text")
            db.session.commit()
        elif not (file and file.filename):
            flash("Paste report text or choose a supported file.", "error")
    return render_template("report.html", result=result)

@app.route("/trends")
@login_required
def trends():
    health_items = HealthEntry.query.filter_by(user_id=current_user.id).order_by(HealthEntry.created_at.desc()).limit(12).all()
    fitness_items = FitnessEntry.query.filter_by(user_id=current_user.id).order_by(FitnessEntry.created_at.desc()).limit(12).all()
    logs = DailyLog.query.filter_by(user_id=current_user.id).order_by(DailyLog.log_date.desc()).limit(14).all()
    return render_template("trends.html", health_items=health_items, fitness_items=fitness_items, logs=logs)

@app.route("/care", methods=["GET", "POST"])
@login_required
def care():
    query = ""
    search_url = None
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            from urllib.parse import quote_plus
            search_url = "https://www.google.com/maps/search/" + quote_plus(query + " doctor hospital")
    return render_template("care.html", query=query, search_url=search_url)

@app.route("/tracker", methods=["GET", "POST"])
@login_required
def tracker():
    log = get_or_create_log(current_user)
    if request.method == "POST":
        try:
            water = max(0, min(40, int(request.form.get("water_glasses", "0"))))
            sleep = max(0, min(24, float(request.form.get("sleep_hours", "0"))))
            steps = max(0, min(200000, int(request.form.get("steps", "0"))))
        except ValueError:
            flash("Please enter valid numbers for water, sleep and steps.", "error")
            return redirect(url_for("tracker"))
        log.water_glasses = water
        log.sleep_hours = sleep
        log.steps = steps
        log.mood = request.form.get("mood", "Okay")[:40]
        log.notes = request.form.get("notes", "").strip()[:1000]
        add_points(current_user, 5, "Daily tracker completed", once_key="daily-tracker")
        db.session.commit()
        flash("Today's tracker has been saved.", "success")
        return redirect(url_for("tracker"))
    logs = DailyLog.query.filter_by(user_id=current_user.id).order_by(DailyLog.log_date.desc()).limit(7).all()
    return render_template("tracker.html", log=log, logs=logs)

@app.route("/rewards")
@login_required
def rewards():
    transactions = PointTransaction.query.filter_by(user_id=current_user.id).order_by(PointTransaction.created_at.desc()).limit(20).all()
    points = current_user.points
    badges = []
    if points >= 5: badges.append(("🌱", "Healthy Starter", "Earned your first points"))
    if points >= 20: badges.append(("💧", "Consistency Builder", "Earned 20 HealthPoints"))
    if points >= 50: badges.append(("⭐", "Wellness Champion", "Earned 50 HealthPoints"))
    if DailyLog.query.filter_by(user_id=current_user.id).count() >= 7: badges.append(("🔥", "7-Day Tracker", "Logged at least 7 days"))
    return render_template("rewards.html", transactions=transactions, points=points, badges=badges)

@app.errorhandler(413)
def too_large(_error):
    flash("The file is too large. Maximum upload size is 10 MB.", "error")
    return redirect(request.referrer or url_for("report"))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    # Local development only. Do not expose the debug server to the public internet.
    app.run(debug=True)
