import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError

# --- إعداد التطبيق وقاعدة البيانات ---
app = Flask(__name__)
# استخدم متغير بيئة أو مفتاح سري قوي
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_super_secret_key') 

# المنطق: يستخدم متغير البيئة للداتا بيز في Render، ويستخدم SQLite محلياً
if os.environ.get('DATABASE_URL'):
    # تعديل رابط PostgreSQL ليكون متوافقاً مع SQLAlchemy (ضروري لـ Render)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://", 1)
else:
    # للتشغيل المحلي
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

# --- نماذج WTForms (احتفظ بها كما هي) ---
class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])

class EmployeeForm(FlaskForm):
    full_name = StringField('الاسم الكامل', validators=[DataRequired(), Length(min=2, max=120)])
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=2, max=80)])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=6)])
    is_admin = SelectField('نوع الحساب', choices=[('0', 'موظف'), ('1', 'مدير')], validators=[DataRequired()])

class AssetForm(FlaskForm):
    name = StringField('اسم الأصل', validators=[DataRequired(), Length(min=2, max=100)])
    serial_number = StringField('الرقم التسلسلي', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('الوصف')
    status = SelectField('الحالة', choices=[('Available', 'متاح'), ('Assigned', 'مُسند'), ('Retired', 'مُهمل')], validators=[DataRequired()])

class AssignAssetForm(FlaskForm):
    asset_id = HiddenField() 
    employee_id = SelectField('اختيار الموظف', validators=[DataRequired()])

# --- المسارات (Routes) ---

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
    else:
        current_assets = AssetLog.query.filter_by(user_id=current_user.id, return_date=None).all()
        return render_template('employee_dashboard.html', assets=current_assets)


# --- (ضع هنا بقية مسارات التطبيق: add_asset, edit_employee, etc.) ---


# --- **المنطق الحاسم لإنشاء الجداول وحساب المدير** ---
# هذا الجزء يتم استيراده وتنفيذه مباشرة بواسطة start.sh
with app.app_context():
    db.create_all()
    # إنشاء حساب المدير الافتراضي إذا لم يكن موجوداً
    if User.query.filter_by(username='admin').first() is None:
        admin_user = User(username='admin', password='adminpass', is_admin=True, full_name='مدير النظام')
        db.session.add(admin_user)
        db.session.commit()