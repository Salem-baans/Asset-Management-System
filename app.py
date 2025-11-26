import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from sqlalchemy.exc import OperationalError

# --- إعداد التطبيق وقاعدة البيانات ---
app = Flask(__name__)
# يستخدم متغير البيئة SECRET_KEY
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_super_secret_key') 

# *** نستخدم SQLite حالياً لتجاوز مشاكل الطبقة المجانية ***
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets_management.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- إعداد تسجيل الدخول ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- النماذج (Models) ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    full_name = db.Column(db.String(120))
    logs = db.relationship('AssetLog', backref='employee', lazy=True)

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='Available')
    logs = db.relationship('AssetLog', backref='asset', lazy=True)

class AssetLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignment_date = db.Column(db.DateTime, default=datetime.utcnow)
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50))

# --- نماذج WTForms (استبدل هذه بالنماذج الكاملة إذا كانت مختلفة) ---
class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
# ... (بقية النماذج) ...

# --- المسارات (Routes) ---

@app.route('/healthz', methods=['GET'])
def health_check():
    """مسار فحص الصحة المطلوب من Render"""
    return "ok", 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.password == form.password.data:
            login_user(user)
            flash('تم تسجيل الدخول بنجاح.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    if current_user.is_admin:
        try:
            # محاولة جلب البيانات، يتم معالجة الخطأ إذا كانت قاعدة البيانات غير مهيأة بالكامل
            employees = User.query.filter_by(is_admin=False).all()
            assets = Asset.query.all()
            total_assets = len(assets)
            available_assets = Asset.query.filter_by(status='Available').count()
            assigned_assets = Asset.query.filter_by(status='Assigned').count()
            recent_logs = AssetLog.query.order_by(AssetLog.assignment_date.desc()).limit(10).all()
            
            context = {
                'employees': employees,
                'assets': assets,
                'total_assets': total_assets,
                'available_assets': available_assets,
                'assigned_assets': assigned_assets,
                'recent_logs': recent_logs
            }
            return render_template('admin_dashboard.html', **context)
        except OperationalError:
            # إذا فشلت العملية بسبب عدم وجود الجداول (لسبب نادر)
            print("Database tables might not be fully initialized. Showing zero data.")
            flash("تم تسجيل الدخول بنجاح، لكن لا يمكن عرض بيانات لوحة القيادة حالياً. يرجى محاولة إضافة بيانات.", 'warning')
            
            # العودة إلى عرض لوحة قيادة فارغة لتجنب Internal Server Error
            return render_template('admin_dashboard.html', employees=[], assets=[], total_assets=0, available_assets=0, assigned_assets=0, recent_logs=[])
        except Exception as e:
            # لأي خطأ آخر غير متوقع
            print(f"Unexpected Error in dashboard route: {e}")
            flash("حدث خطأ غير متوقع أثناء تحميل لوحة القيادة.", 'danger')
            return render_template('admin_dashboard.html', employees=[], assets=[], total_assets=0, available_assets=0, assigned_assets=0, recent_logs=[])

    else:
        # للموظف العادي
        current_assets = AssetLog.query.filter_by(user_id=current_user.id, return_date=None).all()
        return render_template('employee_dashboard.html', assets=current_assets)


# --- (ضع هنا بقية مسارات التطبيق: add_asset, edit_employee, etc.) ---


# ----------------------------------------------------------------------------------
# --- **دالة تهيئة قاعدة البيانات** ---
# ----------------------------------------------------------------------------------

def initialize_database():
    """ينشئ الجداول وحساب المدير لمرة واحدة."""
    with app.app_context():
        # إنشاء الجداول
        db.create_all()
        # إنشاء حساب المدير الافتراضي إذا لم يكن موجوداً
        if User.query.filter_by(username='admin').first() is None:
            admin_user = User(username='admin', password='adminpass', is_admin=True, full_name='مدير النظام')
            db.session.add(admin_user)
            db.session.commit()
        print("Database initialized and admin account created successfully!") 

# ----------------------------------------------------------------------------------
# --- **استدعاء الدالة عند تشغيل Gunicorn** ---
# ----------------------------------------------------------------------------------

# Gunicorn سيعين هذا المتغير البيئي في أمر التشغيل (CALL_INIT=1)
if os.environ.get('CALL_INIT') == '1':
    initialize_database()