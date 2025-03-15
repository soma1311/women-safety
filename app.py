from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from twilio.rest import Client
from datetime import datetime
import requests  # For making API requests to Mapbox

app = Flask(__name__)

# Twilio configuration (hardcoded credentials)

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Mapbox API configuration
MAPBOX_ACCESS_TOKEN = 'pk.eyJ1Ijoic29tYTEzMDkiLCJhIjoiY204OHRqOTAwMHE1ZjJsc2I0cnl2YnY0YSJ9.f1kxGHxm98mMAprix2ZW8Q'  # Replace with your Mapbox access token
MAPBOX_BASE_URL = 'https://api.mapbox.com/geocoding/v5/mapbox.places'

# Database setup
def init_db():
    conn = sqlite3.connect('/opt/women-safety-app/safety_app.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            emergency_contact TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Home page
@app.route('/')
def home():
    return render_template('index.html')

# Register user
@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name')
    phone = request.form.get('phone')
    emergency_contact = request.form.get('emergency_contact')

    conn = sqlite3.connect('/opt/women-safety-app/safety_app.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (name, phone, emergency_contact) VALUES (?, ?, ?)',
                   (name, phone, emergency_contact))
    conn.commit()
    conn.close()

    return redirect(url_for('home'))

# Panic button
@app.route('/panic', methods=['POST'])
def panic_button():
    # Ensure the request contains JSON data
    if not request.is_json:
        return jsonify({"status": "Request must be JSON"}), 415

    data = request.get_json()  # Parse JSON data
    user_id = data.get('user_id')
    print(f"User ID: {user_id}")  # Debug: Log the User ID

    conn = sqlite3.connect('/opt/women-safety-app/safety_app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()

    if user:
        print(f"User Found: {user}")  # Debug: Log the user data
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        print(f"Latitude: {latitude}, Longitude: {longitude}")  # Debug: Log the location

        # Store the location in the database
        cursor.execute('INSERT INTO locations (user_id, latitude, longitude) VALUES (?, ?, ?)',
                       (user_id, latitude, longitude))
        conn.commit()

        # Generate a link to the /map route
        map_link = f"http://women.leran.xyz/map?user_id={user_id}"  # Replace with your domain
        print(f"Map Link: {map_link}")  # Debug: Log the map link

        # Send SMS to emergency contact
        emergency_contact = user[3]
        if not emergency_contact.startswith('+'):
            emergency_contact = f"+91{emergency_contact}"  # Add Indian country code if missing
        print(f"Emergency Contact: {emergency_contact}")  # Debug: Log the emergency contact

        try:
            message = client.messages.create(
                body=f"Emergency! {user[1]} needs help. Click the link to view their location: {map_link}",
                from_=TWILIO_PHONE_NUMBER,
                to=emergency_contact
            )
            print(f"SMS Sent Successfully! Message SID: {message.sid}")  # Debug: Log success
            return jsonify({"status": "Alert sent!"})
        except Exception as e:
            print(f"Error Sending SMS: {e}")  # Debug: Log the error
            return jsonify({"status": "Failed to send alert!"}), 500
    else:
        print("User Not Found!")  # Debug: Log if user is not found
        return jsonify({"status": "User not found!"}), 404
    conn.close()

# Map route to display user location
@app.route('/map')
def show_map():
    user_id = request.args.get('user_id')
    conn = sqlite3.connect('/opt/women-safety-app/safety_app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT latitude, longitude FROM locations WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,))
    location = cursor.fetchone()
    conn.close()

    if location:
        latitude, longitude = location
        return render_template('map.html', latitude=latitude, longitude=longitude, user_id=user_id)
    else:
        return "Location not found.", 404

# Endpoint to fetch the latest location
@app.route('/get_location', methods=['GET'])
def get_location():
    user_id = request.args.get('user_id')
    conn = sqlite3.connect('/opt/women-safety-app/safety_app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT latitude, longitude FROM locations WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,))
    location = cursor.fetchone()
    conn.close()

    if location:
        latitude, longitude = location
        return jsonify({"latitude": latitude, "longitude": longitude})
    else:
        return jsonify({"error": "Location not found"}), 404

# Route to fetch nearby police stations
@app.route('/nearby_police_stations', methods=['GET'])
def nearby_police_stations():
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

    if not latitude or not longitude:
        return jsonify({"error": "Latitude and longitude are required"}), 400

    # Search for police stations within 10km of the given coordinates
    url = f"{MAPBOX_BASE_URL}/police.json?proximity={longitude},{latitude}&limit=10&access_token={MAPBOX_ACCESS_TOKEN}"
    response = requests.get(url)

    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch police stations"}), 500

    data = response.json()
    police_stations = []

    for feature in data.get('features', []):
        police_stations.append({
            "name": feature.get('text', 'Unknown'),
            "address": feature.get('place_name', 'Unknown'),
            "latitude": feature['center'][1],
            "longitude": feature['center'][0]
        })

    return jsonify(police_stations)

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

