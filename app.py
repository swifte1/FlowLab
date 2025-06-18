from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os
from datetime import datetime, date, timedelta
import plotly.graph_objs as go
from collections import defaultdict
from dateutil.relativedelta import relativedelta  # <-- added for robust date shifting
from uuid import uuid4  # <-- added for unique ID generation

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stock.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key_here'
db = SQLAlchemy(app)

# Panels and Reagents
PANELS = [
    "Chronic Panel",
    "B Cell Follow-on Panel",
    "T Cell Follow-on Panel",
    "Acute Panel",
    "PNH Screen",
    "PID Panel",
    "Myeloma",
    "Lymphocyte Subset Testing",
    "Hereditary Spherocytosis Test",
    "Maintenance BDFACSLyric/Duet",
    "Miscellaneous Reagents"
]

PANEL_REAGENTS = {
    "Chronic Panel": [
        "BD LST Tubes Multicolour"
    ],
    "B Cell Follow-on Panel": [
        "BD CD5 FITC", "BD CD10 PE", "BD CD19 PerCP-Cy5.5",
        "BD FMC7 FITC", "BD CD23 PE", "BD CD103 FITC",
        "BD CD22 PE", "BD CD20 PerCP-Cy5.5"
    ],
    "T Cell Follow-on Panel": [
        "CD4 FITC", "CD25 PE", "CD3 PerCP-Cy5.5"
    ],
    "Acute Panel": [
        "BD CD5 FITC", "BD CD10 PE", "BD CD2 FITC", "BD CD7 FITC",
        "BD CD20 FITC", "BD CD19 PE", "Dako HLA DRDQ FITC",
        "BD CD14 FITC", "BD CD13 PE", "BD CD33 PE", "BD CD34 FITC",
        "BD CD117 PE", "Dako TDT FITC", "BD CD3 FITC", "BD CD79a PerCP Cy5",
        "BD MPO PE", "BD CD34 PE", "BD CD45 PerCP", "BD CD45 APC"
    ],
    "PNH Screen": [
        "BD CD33 PE", "Serotech CD59 PE", "BD CD15 APC", "VH Bio FLAER FITC"
    ],
    "PID Panel": [
        "BC CD19 PC7", "Jackson FLUOR Alexa Fluor 647",
        "Southern Biotech IgD PE", "BD CD21 PE", "BD CD38 FITC", "BD CD27 FITC"
    ],
    "Myeloma": [
        "BD Lambda PE", "BD Kappa FITC", "BD CD138 PerCP-Cy5.5", "BD CD56 APC",
        "BD CD38 PE-Cy7", "BD CD19 BV421"
    ],
    "Lymphocyte Subset Testing": [
        "BD CD3/8/45/4 antibody (A)",
        "BD CD3/16/56/45/19 antibody (B)",
        "BD Trucount tubes",
        "BD FACS Lyse"
    ],
    "Hereditary Spherocytosis Test": [
        "Eosin-5-Maleimide"
    ],
    "Maintenance BDFACSLyric/Duet": [
        "BD FACSFlow", "BD FACSClean", "BD CS&T Beads", "BD 5 Colour FC Beads",
        "BD 7 Colour FC Beads", "BD Cell Wash"
    ],
    "Miscellaneous Reagents": [
        "BD CompBeads", "CD CHEX Plus CD4 Low", "CD CHEX Plus CD4 High",
        "DAKO Intrastain Kit", "Cytognos Quicklyse", "BD 5mL Syringe",
        "BD 21G Eclipse needle", "Falcon Tubes", "10 µL Pipette Tips",
        "200 µL Pipette Tips", "1,000 µL Pipette Tips", "PBS II Concentrate (40x)"
    ]
}

# StockItem model
class StockItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    lot_number = db.Column(db.String(100), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    received_date = db.Column(db.Date, nullable=False)
    acceptance_tested = db.Column(db.Date, nullable=True)
    passed_by = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(100), nullable=True)  # Spare or In Use

# InUseLog model
class InUseLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    panel_name = db.Column(db.String(100), nullable=False)
    reagent_name = db.Column(db.String(200), nullable=False)
    uid = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)

# Home route
@app.route('/')
def index():
    stock_items = StockItem.query.all()
    return render_template(
        'index.html',
        stock_items=stock_items,
        now=datetime.now(),        # ← passing the current time
        timedelta=timedelta        # ← passing the timedelta function
    )

# Monitoring
@app.route('/monitoring')
def monitoring():
    stock_items = StockItem.query.all()
    events = defaultdict(int)

    for item in stock_items:
        events[item.received_date] += 1

    dates = sorted(events.keys())
    counts = []
    total = 0
    for d in dates:
        total += events[d]
        counts.append(total)

    fig = go.Figure(data=[go.Scatter(x=dates, y=counts, mode='lines+markers', name='Stock Levels')])
    fig.update_layout(title='Total Stock Received Over Time', xaxis_title='Date', yaxis_title='Cumulative Stock')
    graph_json = fig.to_json()

    return render_template('monitoring.html', graph_json=graph_json)

# Helper function: Add stock item and update In Use log if applicable
def receive_stock_logic(name, lot_number, expiry_date, received_date, acceptance_tested, passed_by, location, selected_panels):
    new_item = StockItem(
        uid=str(uuid4()),
        name=name,
        lot_number=lot_number,
        expiry_date=expiry_date,
        received_date=received_date,
        acceptance_tested=acceptance_tested,
        passed_by=passed_by,
        location=location
    )

    db.session.add(new_item)

    if location == 'In Use':
        for panel in selected_panels:
            log_entry = InUseLog(
                panel_name=panel,
                reagent_name=name,
                uid=new_item.uid,
                start_date=date.today(),
                end_date=None
            )
            db.session.add(log_entry)

    db.session.commit()

@app.route('/receive', methods=['GET', 'POST'])
def receive_stock():
    if request.method == 'POST':
        name = request.form['name']
        lot_number = request.form['lot_number']
        expiry_date = datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date()
        received_date = datetime.strptime(request.form['received_date'], '%Y-%m-%d').date()

        acceptance_tested_str = request.form['acceptance_tested']
        acceptance_tested = datetime.strptime(acceptance_tested_str, '%Y-%m-%d').date() if acceptance_tested_str else None

        passed_by = request.form['passed_by']
        location = request.form['location']
        selected_panels = request.form.getlist('selected_panels')  # ← this collects the selected checkboxes

        receive_stock_logic(
            name=name,
            lot_number=lot_number,
            expiry_date=expiry_date,
            received_date=received_date,
            acceptance_tested=acceptance_tested,
            passed_by=passed_by,
            location=location,
            selected_panels=selected_panels
        )

        return redirect(url_for('index'))

    return render_template('receive_stock.html', panels=PANELS)

# Date Checking
@app.route('/date_checking', methods=['GET', 'POST'])
def date_checking():
    today = date.today()
    three_months_ahead = today + relativedelta(months=3)

    expiring_soon = StockItem.query.filter(StockItem.expiry_date <= three_months_ahead).all()

    return render_template(
        'date_checking.html',
        items=expiring_soon,
        current_date=today,
        soon_date=three_months_ahead
    )

@app.route('/remove_expired', methods=['POST'])
def remove_expired():
    lot_number = request.form.get('lot_number')
    item = StockItem.query.filter_by(lot_number=lot_number).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        flash(f'Lot {lot_number} removed successfully.', 'success')
    else:
        flash(f'Lot {lot_number} not found.', 'danger')

    return redirect(url_for('date_checking'))

# Remove stock
@app.route('/remove', methods=['GET', 'POST'])
def remove_stock():
    if request.method == 'POST':
        lot_number = request.form['lot_number']
        reason = request.form['reason']
        removal_date = datetime.strptime(request.form['removal_date'], '%Y-%m-%d').date()

        item = StockItem.query.filter_by(lot_number=lot_number).first()
        if item:
            db.session.delete(item)
            db.session.commit()

            flash('Item removed successfully.', 'success')
            return redirect(url_for('remove_stock'))
        else:
            flash('Lot Number not found in stock.', 'danger')

    return render_template('remove_stock.html')

# API: Lookup lot
@app.route('/api/lookup_lot/<lot_number>')
def lookup_lot(lot_number):
    item = StockItem.query.filter_by(lot_number=lot_number).first()
    if item:
        return jsonify({
            'name': item.name,
            'lot_number': item.lot_number,
            'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
            'received_date': item.received_date.strftime('%Y-%m-%d') if item.received_date else '',
            'acceptance_tested': item.acceptance_tested.strftime('%Y-%m-%d') if item.acceptance_tested else '',
            'passed_by': item.passed_by or '',
            'location': item.location or ''
        })
    else:
        return jsonify({})

# In Use page (updated to reflect StockItem location directly)
@app.route('/in_use')
def in_use():
    in_use_data = {}
    for panel in PANELS:
        in_use_data[panel] = []
        for reagent in PANEL_REAGENTS.get(panel, []):
            # Get the most recent InUseLog entry, if it exists
            current_log = InUseLog.query.filter_by(panel_name=panel, reagent_name=reagent, end_date=None).first()

            # Fall back to StockItem where location is 'In Use' if no log exists
            lot_number = ''
            expiry_date = ''

            if current_log:
                uid = current_log.uid
                stock_item = StockItem.query.filter_by(uid=uid).first()
                if stock_item:
                    expiry_date = stock_item.expiry_date.strftime('%Y-%m-%d')
            else:
                # Use any matching 'In Use' item
                fallback_item = StockItem.query.filter_by(name=reagent, location='In Use').first()
                if fallback_item:
                    lot_number = fallback_item.lot_number
                    expiry_date = fallback_item.expiry_date.strftime('%Y-%m-%d')

            in_use_data[panel].append({
                'reagent': reagent,
                'lot_number': lot_number,
                'expiry_date': expiry_date
            })

    return render_template('in_use.html', in_use_data=in_use_data)

# API: Available Lots for In Use page
@app.route('/api/available_lots/<reagent_name>')
def available_lots(reagent_name):
    lots = StockItem.query.filter_by(name=reagent_name, location='Spare').all()
    lots_data = [{
        'uid': lot.uid,
	'lot_number': lot.lot_number,
        'expiry_date': lot.expiry_date.strftime('%Y-%m-%d')
    } for lot in lots]
    return jsonify(lots_data)

# API: Change In Use Lot
@app.route('/api/change_in_use', methods=['POST'])
def change_in_use():
    data = request.json
    panel = data['panel']
    reagent = data['reagent']
    new_uid = data['uid']
    today = date.today()

    old_log = InUseLog.query.filter_by(panel_name=panel, reagent_name=reagent, end_date=None).first()
    if old_log:
        old_log.end_date = today

    new_log = InUseLog(
        panel_name=panel,
        reagent_name=reagent,
        lot_number=new_lot,
        start_date=today,
        end_date=None
    )
    db.session.add(new_log)

    # Update StockItem locations
    if old_log:
        old_item = StockItem.query.filter_by(lot_number=old_log.lot_number, name=reagent).first()
        if old_item:
            old_item.location = 'Spare'

    new_item = StockItem.query.filter_by(uid=new_uid).first()
    if new_item:
        new_item.location = 'In Use'

    db.session.commit()

    return jsonify({'success': True})

# Export stock
@app.route('/export')
def export():
    stock_items = StockItem.query.all()
    data = [
        [
            item.name,
            item.lot_number,
            item.expiry_date,
            item.received_date,
            item.acceptance_tested,
            item.passed_by,
            item.location
        ]
        for item in stock_items
    ]

    df = pd.DataFrame(data, columns=[
        'Name',
        'Lot Number',
        'Expiry Date',
        'Received Date',
        'Acceptance Tested',
        'Passed By',
        'Location'
    ])

    export_path = os.path.join(os.getcwd(), 'stock_export.xlsx')
    df.to_excel(export_path, index=False)

    return send_file(export_path, as_attachment=True)

# Run app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)