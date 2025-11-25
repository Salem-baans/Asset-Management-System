from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_wtf import FlaskForm # <--- تم إضافة هذا الاستيراد
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Length

# --- إعداد التطبيق وقاعدة البيانات ---
app = Flask(__name__)
# مفتاح سري ضروري لحماية الجلسات و CSRF
app.config['SECRET_KEY'] = 'your_super_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets_management.db'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

# --- نماذج Flask-WTF لزيادة الأمان ---
# نموذج تسجيل الدخول (لأمان CSRF)
class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=2, max=100)])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])

# --- نماذج قاعدة البيانات (Database Models) ---

# نموذج الموظف (المستخدم)
class Employee(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# نموذج الأصول (Assets)
class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(100), unique=True)
    condition = db.Column(db.String(50))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    
    assigned_to = db.relationship('Employee', backref='assets_assigned', lazy='joined') 

# نموذج سجل العُهد (AssetLog)
class AssetLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    handover_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    return_date = db.Column(db.DateTime, nullable=True) 
    
    asset = db.relationship('Asset', backref='history')
    employee = db.relationship('Employee', backref='asset_logs')


# --- وظائف مساعدة لتسجيل الدخول ---
@login_manager.user_loader
def load_user(employee_id):
    return db.session.get(Employee, int(employee_id))

# --- نقاط النهاية (Routes) ---

# إنشاء قاعدة البيانات والجداول عند التشغيل الأول
with app.app_context():
    db.create_all()
    # مثال: إضافة مستخدم مدير (Admin) افتراضي مرة واحدة
    if not Employee.query.filter_by(username='admin').first():
        admin = Employee(username='admin', is_admin=True)
        admin.set_password('adminpass')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: username='admin', password='adminpass'")


# 1. صفحة تسجيل الدخول (مُعدلة لاستخدام Flask-WTF)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm() # <--- إنشاء نسخة من النموذج
    
    if form.validate_on_submit(): # <--- التحقق من CSRF وصحة البيانات
        username = form.username.data
        password = form.password.data
        employee = Employee.query.filter_by(username=username).first()
        
        if employee and employee.check_password(password):
            login_user(employee)
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'danger')
            
    return render_template('login.html', form=form) # <--- تمرير النموذج إلى القالب

# 2. تسجيل الخروج
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 3. لوحة التحكم المشتركة (لوحة الموظف والمدير)
@app.route('/')
@login_required
def dashboard():
    if current_user.is_admin:
        assets = Asset.query.all()
        employees = Employee.query.all()
        return render_template('admin_dashboard.html', assets=assets, employees=employees)
    else:
        employee_assets = Asset.query.filter_by(assigned_to_id=current_user.id).all()
        return render_template('employee_dashboard.html', assets=employee_assets)

# 4. (للمدير فقط) إضافة أصل جديد وتعيينه
@app.route('/add_asset', methods=['GET', 'POST'])
@login_required
def add_asset():
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول لهذه الصفحة.', 'danger')
        return redirect(url_for('dashboard'))
    
    employees = Employee.query.all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        serial = request.form.get('serial_number')
        condition = request.form.get('condition')
        assigned_to_id = request.form.get('assigned_to')
        
        new_asset = Asset(
            name=name, 
            serial_number=serial, 
            condition=condition, 
            assigned_to_id=assigned_to_id if assigned_to_id else None
        )
        
        try:
            db.session.add(new_asset)
            db.session.flush()
            
            if assigned_to_id:
                new_log = AssetLog(
                    asset_id=new_asset.id,
                    employee_id=assigned_to_id,
                    handover_date=datetime.utcnow()
                )
                db.session.add(new_log)
                
            db.session.commit()
            flash('تمت إضافة الأصل بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {e}', 'danger')

    return render_template('add_asset.html', employees=employees)

# 5. (للمدير فقط) إضافة موظف جديد
@app.route('/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول لهذه الصفحة.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'

        if Employee.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل.', 'danger')
            return render_template('add_employee.html')

        new_employee = Employee(username=username, is_admin=is_admin)
        new_employee.set_password(password)

        db.session.add(new_employee)
        db.session.commit()
        flash('تمت إضافة الموظف بنجاح!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_employee.html')

# 6. (للمدير فقط) تعديل تفاصيل الأصل
@app.route('/edit_asset/<int:asset_id>', methods=['GET', 'POST'])
@login_required
def edit_asset(asset_id):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول لهذه الصفحة.', 'danger')
        return redirect(url_for('dashboard'))
    
    asset = Asset.query.get_or_404(asset_id)
    employees = Employee.query.filter_by(is_admin=False).all()
    
    if request.method == 'POST':
        old_assigned_to_id = asset.assigned_to_id
        new_assigned_to_id = request.form.get('assigned_to')
        
        asset.name = request.form.get('name')
        asset.serial_number = request.form.get('serial_number')
        asset.condition = request.form.get('condition')
        
        # --- منطق تسجيل الإرجاع والتسليم الجديد ---
        
        # 1. إذا كان الأصل مُعيناً (سابقاً) وتم إرجاعه (أصبح غير مُعين أو نُقل)
        if old_assigned_to_id is not None and old_assigned_to_id != (int(new_assigned_to_id) if new_assigned_to_id else None):
            current_log = AssetLog.query.filter_by(
                asset_id=asset.id, 
                employee_id=old_assigned_to_id, 
                return_date=None
            ).first()
            
            if current_log:
                current_log.return_date = datetime.utcnow() # تسجيل تاريخ الإرجاع

        # 2. إذا تم تعيين الأصل لشخص جديد 
        if new_assigned_to_id and (old_assigned_to_id is None or old_assigned_to_id != int(new_assigned_to_id)):
            new_log = AssetLog(
                asset_id=asset.id,
                employee_id=new_assigned_to_id,
                handover_date=datetime.utcnow() # تسجيل تاريخ التسليم الجديد
            )
            db.session.add(new_log)
        
        # تحديث الحقل الحالي في جدول Asset
        asset.assigned_to_id = int(new_assigned_to_id) if new_assigned_to_id else None
        
        # ----------------------------------------
        
        try:
            db.session.commit()
            flash(f'تم تحديث الأصل ({asset.name}) بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ أثناء التحديث: {e}', 'danger')

    return render_template('edit_asset.html', asset=asset, employees=employees)

# 7. (للمدير فقط) حذف الأصل
@app.route('/delete_asset/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_id):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول لهذه الصفحة.', 'danger')
        return redirect(url_for('dashboard'))
    
    asset = Asset.query.get_or_404(asset_id)
    asset_name = asset.name 
    
    try:
        AssetLog.query.filter_by(asset_id=asset.id).delete()
        db.session.delete(asset)
        db.session.commit()
        flash(f'تم حذف الأصل ({asset_name}) وجميع سجلات عهدته بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء الحذف: {e}', 'danger')
        
    return redirect(url_for('dashboard'))

# 8. (للمدير فقط) صفحة اختيار الموظف لإنشاء التقرير
@app.route('/reports')
@login_required
def reports():
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول لهذه الصفحة.', 'danger')
        return redirect(url_for('dashboard'))
    
    employees = Employee.query.filter_by(is_admin=False).all()
    return render_template('reports.html', employees=employees)

# 9. (للمدير فقط) عرض تقرير الموظف المحدد
@app.route('/report/employee/<int:employee_id>')
@login_required
def employee_report(employee_id):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول لهذه الصفحة.', 'danger')
        return redirect(url_for('dashboard'))
    
    employee = Employee.query.get_or_404(employee_id)
    
    current_assets = Asset.query.filter_by(assigned_to_id=employee_id).all()
    asset_history = AssetLog.query.filter_by(employee_id=employee_id).order_by(AssetLog.handover_date.desc()).all()
    
    return render_template('employee_report.html', 
                           employee=employee, 
                           current_assets=current_assets, 
                           asset_history=asset_history)

# --- تشغيل التطبيق ---
if __name__ == '__main__':
    app.run(debug=True)