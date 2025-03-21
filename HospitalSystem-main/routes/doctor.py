from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from models.patient import db
from models.appointment import Appointment, Schedule
from models.report import Report, Payment
from datetime import datetime, timedelta, time

doctor = Blueprint('doctor', __name__)

@doctor.route('/dashboard')
@login_required
def dashboard():
    # 获取今日预约信息
    today = datetime.now().date()
    today_appointments = Appointment.query.filter_by(
        doctor_id=current_user.id,
        appointment_date=today
    ).order_by(Appointment.appointment_time).all()
    
    return render_template('doctor/dashboard.html',
                         today_appointments=today_appointments)

@doctor.route('/schedule', methods=['GET', 'POST'])
@login_required
def manage_schedule():
    if request.method == 'POST':
        schedule_type = request.form.get('schedule_type')
        
        if schedule_type == 'single':
            work_date = request.form.get('work_date')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            status = request.form.get('status', 'normal')
            morning_slots = int(request.form.get('morning_slots', 12))
            afternoon_slots = int(request.form.get('afternoon_slots', 12))
            
            # 检查是否已有排班
            existing_schedule = Schedule.query.filter_by(
                doctor_id=current_user.id,
                work_date=work_date
            ).first()
            
            if existing_schedule:
                flash('该日期已有排班')
                return redirect(url_for('doctor.manage_schedule'))
            
            schedule_data = {
                'doctor_id': current_user.id,
                'work_date': work_date,
                'start_time': start_time,
                'end_time': end_time,
                'status': status,
                'morning_slots': morning_slots,
                'afternoon_slots': afternoon_slots,
                'available_slots': morning_slots + afternoon_slots
            }
            
            # 如果是加班，添加加班时间
            if status == 'extra':
                extra_start_time = request.form.get('extra_start_time')
                extra_end_time = request.form.get('extra_end_time')
                extra_slots = int(request.form.get('extra_slots', 0))
                
                if not all([extra_start_time, extra_end_time, extra_slots]):
                    flash('请填写加班时间和号源数')
                    return redirect(url_for('doctor.manage_schedule'))
                
                schedule_data.update({
                    'extra_start_time': extra_start_time,
                    'extra_end_time': extra_end_time,
                    'extra_slots': extra_slots,
                    'available_slots': morning_slots + afternoon_slots + extra_slots
                })
            # 如果是停诊，添加停诊时间
            elif status == 'off':
                off_start_time = request.form.get('off_start_time')
                off_end_time = request.form.get('off_end_time')
                
                if not all([off_start_time, off_end_time]):
                    flash('请填写停诊时间段')
                    return redirect(url_for('doctor.manage_schedule'))
                
                # 判断停诊时间是否跨越上下午
                off_start = datetime.strptime(off_start_time, '%H:%M').time()
                off_end = datetime.strptime(off_end_time, '%H:%M').time()
                noon = datetime.strptime('12:00', '%H:%M').time()
                
                # 根据停诊时间段调整号源数
                if off_start < noon:
                    if off_end > noon:
                        # 全天停诊
                        morning_slots = 0
                        afternoon_slots = 0
                    else:
                        # 仅上午停诊
                        morning_slots = 0
                else:
                    # 仅下午停诊
                    afternoon_slots = 0
                
                schedule_data.update({
                    'off_start_time': off_start_time,
                    'off_end_time': off_end_time,
                    'morning_slots': morning_slots,
                    'afternoon_slots': afternoon_slots,
                    'available_slots': morning_slots + afternoon_slots
                })
            
            schedule = Schedule(**schedule_data)
            db.session.add(schedule)
            db.session.commit()
            
            flash('排班设置成功')
            return redirect(url_for('doctor.manage_schedule'))
        
        elif schedule_type == 'batch':
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
            weekdays = request.form.getlist('weekdays')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            morning_slots = int(request.form.get('morning_slots', 12))
            afternoon_slots = int(request.form.get('afternoon_slots', 12))
            
            current_date = start_date
            while current_date <= end_date:
                if str(current_date.weekday()) in weekdays:
                    existing_schedule = Schedule.query.filter_by(
                        doctor_id=current_user.id,
                        work_date=current_date.date()
                    ).first()
                    
                    if not existing_schedule:
                        schedule = Schedule(
                            doctor_id=current_user.id,
                            work_date=current_date.date(),
                            start_time=start_time,
                            end_time=end_time,
                            status='normal',
                            morning_slots=morning_slots,
                            afternoon_slots=afternoon_slots,
                            available_slots=morning_slots + afternoon_slots
                        )
                        db.session.add(schedule)
                
                current_date += timedelta(days=1)
            
            db.session.commit()
            flash('批量排班设置成功')
            return redirect(url_for('doctor.manage_schedule'))
            
    schedules = Schedule.query.filter_by(doctor_id=current_user.id).order_by(Schedule.work_date.desc()).all()
    return render_template('doctor/schedule.html', schedules=schedules)

@doctor.route('/schedule/<int:schedule_id>', methods=['GET'])
@login_required
def get_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.doctor_id != current_user.id:
        abort(403)
    return jsonify({
        'id': schedule.id,
        'status': schedule.status,
        'morning_slots': schedule.morning_slots,
        'afternoon_slots': schedule.afternoon_slots,
        'extra_start_time': schedule.extra_start_time.strftime('%H:%M') if schedule.extra_start_time else None,
        'extra_end_time': schedule.extra_end_time.strftime('%H:%M') if schedule.extra_end_time else None,
        'extra_slots': schedule.extra_slots,
        'off_start_time': schedule.off_start_time.strftime('%H:%M') if schedule.off_start_time else None,
        'off_end_time': schedule.off_end_time.strftime('%H:%M') if schedule.off_end_time else None
    })

@doctor.route('/schedule/<int:schedule_id>', methods=['POST'])
@login_required
def update_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.doctor_id != current_user.id:
        abort(403)
    
    status = request.form.get('status', schedule.status)
    morning_slots = int(request.form.get('morning_slots', schedule.morning_slots))
    afternoon_slots = int(request.form.get('afternoon_slots', schedule.afternoon_slots))
    
    if status == 'extra':
        extra_start_time = request.form.get('extra_start_time')
        extra_end_time = request.form.get('extra_end_time')
        extra_slots = int(request.form.get('extra_slots', 0))
        
        if not all([extra_start_time, extra_end_time, extra_slots]):
            flash('请填写加班时间和号源数')
            return redirect(url_for('doctor.manage_schedule'))
        
        schedule.status = status
        schedule.extra_start_time = extra_start_time
        schedule.extra_end_time = extra_end_time
        schedule.extra_slots = extra_slots
        schedule.off_start_time = None
        schedule.off_end_time = None
        schedule.morning_slots = morning_slots
        schedule.afternoon_slots = afternoon_slots
        schedule.available_slots = morning_slots + afternoon_slots + extra_slots
    elif status == 'off':
        off_start_time = request.form.get('off_start_time')
        off_end_time = request.form.get('off_end_time')
        
        if not all([off_start_time, off_end_time]):
            flash('请填写停诊时间段')
            return redirect(url_for('doctor.manage_schedule'))
        
        # 判断停诊时间是否跨越上下午
        off_start = datetime.strptime(off_start_time, '%H:%M').time()
        off_end = datetime.strptime(off_end_time, '%H:%M').time()
        noon = datetime.strptime('12:00', '%H:%M').time()
        
        # 根据停诊时间段调整号源数
        if off_start < noon:
            if off_end > noon:
                # 全天停诊
                morning_slots = 0
                afternoon_slots = 0
            else:
                # 仅上午停诊
                morning_slots = 0
        else:
            # 仅下午停诊
            afternoon_slots = 0
        
        schedule.status = status
        schedule.off_start_time = off_start_time
        schedule.off_end_time = off_end_time
        schedule.extra_start_time = None
        schedule.extra_end_time = None
        schedule.extra_slots = 0
        schedule.morning_slots = morning_slots
        schedule.afternoon_slots = afternoon_slots
        schedule.available_slots = morning_slots + afternoon_slots
    else:
        schedule.status = status
        schedule.extra_start_time = None
        schedule.extra_end_time = None
        schedule.extra_slots = 0
        schedule.off_start_time = None
        schedule.off_end_time = None
        schedule.morning_slots = morning_slots
        schedule.afternoon_slots = afternoon_slots
        schedule.available_slots = morning_slots + afternoon_slots
    
    db.session.commit()
    flash('排班更新成功')
    return redirect(url_for('doctor.manage_schedule'))

@doctor.route('/schedule/<int:schedule_id>/cancel')
@login_required
def cancel_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.doctor_id != current_user.id:
        abort(403)
        
    db.session.delete(schedule)
    db.session.commit()
    flash('排班已取消')
    return redirect(url_for('doctor.manage_schedule'))

@doctor.route('/patients')
@login_required
def patients():
    # 获取医生的所有预约
    appointments = Appointment.query.filter_by(doctor_id=current_user.id).all()
    return render_template('doctor/patients.html', appointments=appointments)

@doctor.route('/create_report/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
def create_report(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # 检查是否是当前医生的预约
    if appointment.doctor_id != current_user.id:
        flash('无权操作此预约')
        return redirect(url_for('doctor.patients'))
    
    # 检查预约状态是否为待报告
    if appointment.status != 'waiting_report':
        flash('只能为待报告的预约开具检查报告')
        return redirect(url_for('doctor.patients'))
    
    if request.method == 'POST':
        report_type = request.form.get('report_type')
        content = request.form.get('content')
        amount = request.form.get('amount')
        
        if not all([report_type, content, amount]):
            flash('请填写完整的报告信息')
            return redirect(url_for('doctor.create_report', appointment_id=appointment_id))
        
        try:
            amount = float(amount)
            if amount < 0:
                raise ValueError
        except ValueError:
            flash('请输入有效的金额')
            return redirect(url_for('doctor.create_report', appointment_id=appointment_id))
        
        # 创建检查报告
        report = Report(
            appointment_id=appointment_id,
            report_type=report_type,
            content=content,
            publish_date=datetime.now()
        )
        
        # 创建缴费记录
        payment = Payment(
            appointment_id=appointment_id,
            amount=amount,
            status='unpaid'
        )
        
        # 更新预约状态为已完成
        appointment.status = 'completed'
        
        db.session.add(report)
        db.session.add(payment)
        db.session.commit()
        
        flash('检查报告已创建')
        return redirect(url_for('doctor.view_report', appointment_id=appointment_id))
        
    return render_template('doctor/create_report.html', appointment=appointment)

@doctor.route('/view_report/<int:appointment_id>')
@login_required
def view_report(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # 检查是否是当前医生的预约
    if appointment.doctor_id != current_user.id:
        flash('无权查看此预约')
        return redirect(url_for('doctor.patients'))
    
    return render_template('doctor/view_report.html', appointment=appointment)

@doctor.route('/start_consultation/<int:appointment_id>', methods=['POST'])
@login_required
def start_consultation(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # 检查是否是当前医生的预约
    if appointment.doctor_id != current_user.id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '无权操作此预约'})
        flash('无权操作此预约')
        return redirect(url_for('doctor.patients'))
    
    # 检查预约状态
    if appointment.status != 'confirmed':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '只能开始已确认的预约'})
        flash('只能开始已确认的预约')
        return redirect(url_for('doctor.patients'))
    
    print(f"开始就诊 - 预约ID: {appointment.id}")
    print(f"更新前状态: {appointment.status}")
    
    # 更新预约状态为待报告
    appointment.status = 'waiting_report'
    try:
        db.session.commit()
        print(f"更新后状态: {appointment.status}")
    except Exception as e:
        print(f"数据库更新���误: {str(e)}")
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '系统错误，请稍后重试'})
        flash('系统错误，请稍后重试')
        return redirect(url_for('doctor.patients'))
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'status': appointment.status,
            'appointment_id': appointment.id
        })
    
    flash('就诊已开始')
    return redirect(url_for('doctor.patients'))

@doctor.route('/update_payment/<int:payment_id>', methods=['POST'])
@login_required
def update_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    appointment = payment.appointment
    
    # 检查是否是当前医生的预约
    if appointment.doctor_id != current_user.id:
        flash('无权操作此缴费记录')
        return redirect(url_for('doctor.patients'))
    
    payment_method = request.form.get('payment_method')
    if not payment_method:
        flash('请选择支付方式')
        return redirect(url_for('doctor.view_report', appointment_id=appointment.id))
    
    # 更新支付状态
    payment.status = 'paid'
    payment.payment_method = payment_method
    payment.payment_date = datetime.now()
    db.session.commit()
    
    flash('缴费状态已更新')
    return redirect(url_for('doctor.view_report', appointment_id=appointment.id))

@doctor.route('/fix_appointment_status/<int:appointment_id>')
@login_required
def fix_appointment_status(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # 检查是否是当前医生的预约
    if appointment.doctor_id != current_user.id:
        flash('无权操作此预约')
        return redirect(url_for('doctor.patients'))
    
    # 将状态改回已确认
    appointment.status = 'confirmed'
    db.session.commit()
    
    flash('预约状态已重置')
    return redirect(url_for('doctor.patients'))
  