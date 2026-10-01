import os
import pusher
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Pusher Initialization ---
pusher_client = pusher.Pusher(
    app_id=os.environ.get('PUSHER_APP_ID'),
    key=os.environ.get('PUSHER_KEY'),
    secret=os.environ.get('PUSHER_SECRET'),
    cluster=os.environ.get('PUSHER_CLUSTER'),
    ssl=True
)

# --- Database Models ---
class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Uuid, primary_key=True)
    branch_name = db.Column(db.String)

class Customer(db.Model):
    __tablename__ = 'customers'
    email = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.Text, nullable=False)
    phone_number = db.Column(db.Text, nullable=False)
    negative_feedback_count = db.Column(db.Integer, server_default=db.text('0'))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Uuid, primary_key=True, server_default=db.text('gen_random_uuid()'))
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(50), nullable=False, default='staff')
    location_id = db.Column(db.Uuid, db.ForeignKey('locations.id'), nullable=True)
    location = db.relationship('Location')

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Uuid, primary_key=True, server_default=db.text('gen_random_uuid()'))
    location_id = db.Column(db.Uuid, db.ForeignKey('locations.id'), nullable=False)
    customer_email = db.Column(db.String(255), db.ForeignKey('customers.email'), nullable=False)
    job_description = db.Column(db.String, nullable=False)
    mechanic_id = db.Column(db.Text, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    location = db.relationship('Location')
    customer = db.relationship('Customer', lazy='joined')

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Uuid, primary_key=True, server_default=db.text('gen_random_uuid()'))
    job_id = db.Column(db.Uuid, db.ForeignKey('jobs.id'))
    raw_text = db.Column(db.Text)
    sentiment_class = db.Column(db.String)
    sentiment_score = db.Column(db.Numeric, nullable=False)
    routing_queue = db.Column(db.String(50), nullable=False)
    ai_draft_response = db.Column(db.Text)
    confidence_score = db.Column(db.Integer)
    is_resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    job = db.relationship('Job', lazy='joined')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    tab = request.args.get('tab', 'home')
    selected_loc = request.args.get('location', 'all')

    query = Feedback.query
    location_name = "All Branches"

    # Scope query based on role and location filter
    if current_user.role == 'staff':
        query = query.join(Job).filter(Job.location_id == current_user.location_id)
        if current_user.location:
            location_name = current_user.location.branch_name
    elif selected_loc != 'all':
        query = query.join(Job).filter(Job.location_id == selected_loc)
        loc_obj = db.session.get(Location, selected_loc)
        if loc_obj:
            location_name = loc_obj.branch_name

    locations = Location.query.all() if current_user.role in ['super_admin', 'manager'] else []

    if tab == 'home':
        recent_reviews = query.order_by(Feedback.created_at.desc()).limit(5).all()
        all_feedback = query.all()

        # Analytics remains tied to sentiment for the pie chart
        chart_data = {
            'Positive': sum(1 for f in all_feedback if f.sentiment_class and f.sentiment_class.lower() == 'positive'),
            'Mildly Negative': sum(1 for f in all_feedback if f.sentiment_class and f.sentiment_class.lower() == 'mildly negative'),
            'Severely Negative': sum(1 for f in all_feedback if f.sentiment_class and f.sentiment_class.lower() in ['severely negative', 'severly negative'])
        }

        # Queues are now strictly tied to the routing_queue field and exclude resolved items
        queue_stats = {
            'Ready to Publish': sum(1 for f in all_feedback if f.routing_queue == 'Ready to Publish' and not f.is_resolved),
            'Private Queue': sum(1 for f in all_feedback if f.routing_queue == 'Private Queue' and not f.is_resolved),
            'Escalate to Manager': sum(1 for f in all_feedback if f.routing_queue == 'Escalate to Manager' and not f.is_resolved),
            'Human Intervention': sum(1 for f in all_feedback if f.routing_queue == 'Human Intervention' and not f.is_resolved)
        }

        return render_template('dashboard.html', tab=tab, recent_reviews=recent_reviews,
                               chart_data=chart_data, queue_stats=queue_stats,
                               locations=locations, selected_loc=selected_loc, location_name=location_name)
    else:
        # Map the URL tab parameter to the exact n8n database strings
        queue_mapping = {
            'ready_to_publish': 'Ready to Publish',
            'private_queue': 'Private Queue',
            'escalated': 'Escalate to Manager',
            'human_intervention': 'Human Intervention'
        }
        target_queue = queue_mapping.get(tab)

        feedbacks = query.filter(Feedback.routing_queue == target_queue, Feedback.is_resolved == False).all()
        return render_template('dashboard.html', tab=tab, feedbacks=feedbacks,
                               locations=locations, selected_loc=selected_loc, location_name=location_name)

@app.route('/action/resolve/<uuid:feedback_id>', methods=['POST'])
@login_required
def resolve_feedback(feedback_id):
    feedback = db.session.get(Feedback, feedback_id)
    if feedback:
        feedback.is_resolved = True
        db.session.commit()
    return redirect(request.referrer)

@app.route('/action/change_queue/<uuid:feedback_id>', methods=['POST'])
@login_required
def change_queue(feedback_id):
    feedback = db.session.get(Feedback, feedback_id)
    new_queue = request.form.get('new_queue')
    if feedback and new_queue:
        # now updates the routing_queue
        feedback.routing_queue = new_queue
        db.session.commit()
    return redirect(request.referrer)

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if current_user.role != 'super_admin':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        loc_id = request.form.get('location_id') or None

        if not User.query.filter_by(email=email).first():
            hashed = generate_password_hash(password, method='scrypt', salt_length=20)
            new_user = User(email=email, password_hash=hashed, role=role, location_id=loc_id)
            db.session.add(new_user)
            db.session.commit()
        else:
            flash("User already exists.")

    users = User.query.all()
    locations = Location.query.all()
    return render_template('admin.html', users=users, locations=locations)

@app.route('/admin/toggle_role/<uuid:user_id>', methods=['POST'])
@login_required
def toggle_role(user_id):
    if current_user.role != 'super_admin':
        return redirect(url_for('dashboard'))
    user = db.session.get(User, user_id)
    if user and user.id != current_user.id:
        user.role = 'staff' if user.role == 'manager' else 'manager'
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/delete/<uuid:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'super_admin':
        return redirect(url_for('dashboard'))
    user = db.session.get(User, user_id)
    if user and user.id != current_user.id:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/api/webhook/notify', methods=['POST'])
@app.route('/api/webhook/notify', methods=['POST'])
def notify_dashboard():
    client_key = request.headers.get('x-key')
    server_secret = os.environ.get('N8N_WEBHOOK_SECRET')

    # 1. Authorise (and prevent the None == None trap)
    if not server_secret or client_key != server_secret:
        # Force flush ensures the print statement always hits the Vercel logs immediately
        print(f"Auth Failed! Client sent: {client_key} | Server expected: {server_secret}", flush=True)
        return jsonify({"error": "Unauthorised access"}), 401

    # 2. Trigger the Pusher event
    pusher_client.trigger('dashboard-channel', 'data-updated', {'action': 'refresh'})
    return jsonify({"status": "notification sent"}), 200