from flask import Flask,send_file,render_template, request, jsonify, redirect, url_for, make_response
from flask_bcrypt import Bcrypt
from flask_bcrypt import check_password_hash
from pymongo import MongoClient
import hashlib
import uuid
import html
import os

app = Flask(__name__, template_folder='.')
Method='local'

if Method=='local':
    mongo_client = MongoClient("mongodb+srv://Jaretl123:Jaretl123@cluster0.dpg3dfq.mongodb.net/")
else:
    mongo_client = MongoClient("mongo")

IMAGE_SIGNATURES = {
    b'\xFF\xD8\xFF': 'jpg',   # JPEG/JFIF
    b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A': 'png',   # PNG
    b'\x47\x49\x46\x38\x37\x61': 'gif',   # GIF
}

VIDEO_SIGNATURES = {
    b'\x00\x00\x00\x18ftypmp4': 'mp4'    # MP4
}

def validate_image_signature(signature):
    for magic_number, image_type in IMAGE_SIGNATURES.items():
        if signature.startswith(magic_number):
            return image_type
    return None

def validate_video_signature(signature):
    for magic_number, image_type in VIDEO_SIGNATURES.items():
        if signature.startswith(magic_number):
            return image_type
    return None

db = mongo_client["CSE312"] 
if "Comments" not in db.list_collection_names():
    db.create_collection("Comments")
if "Tokens" not in db.list_collection_names():
    db.create_collection("Tokens")
if "Users" not in db.list_collection_names():
    db.create_collection("Users")
if "XSRF" not in db.list_collection_names():
    db.create_collection("XSRF")
if "id" not in db.list_collection_names():
    db.create_collection("id")
    db["id"].insert_one({"value": 0})
if "media_id" not in db.list_collection_names():
    db.create_collection("media_id")
    db["media_id"].insert_one({"value": 0})

Comments = db["Comments"]
Tokens=db["Tokens"]
Users= db["Users"]
xsrf=db["XSRF"]
ID = db["id"]
media_id = db["media_id"]
bcrypt = Bcrypt()

@app.after_request
def add_header(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.route("/")
def HomePage():
    error_message = request.args.get('error')
    username = request.args.get('username')
    app.logger.info("Accessing home page")
    comments = list(Comments.find())
    auth_token = request.cookies.get('auth_token')
    if auth_token:
        token_hash = hashlib.sha256(auth_token.encode()).hexdigest()
        user_token = Tokens.find_one({"token_hash": token_hash})
        if user_token and user_token['username'] == username:
            pass
        else:
            username = "Guest"
    return render_template('index.html', username=username, error=error_message, comments=comments)

@app.route("/javascript.js")
def ServeJS():
    return send_file('./javascript.js')

@app.route("/style.css")
def ServeCSS():
    return send_file('./style.css')

@app.route('/img/<path:filename>')
def serve_image(filename):
    extension = os.path.splitext(filename)[1]
    mime_type = None
    if extension == '.jpg' or extension == '.jpeg':
        mime_type = 'image/jpeg'
    elif extension == '.png':
        mime_type = 'image/png'
    elif extension == '.gif':
        mime_type = 'image/gif'
    elif extension == '.bmp':
        mime_type = 'image/bmp'
    elif extension == '.webp':
        mime_type = 'image/webp'
    if mime_type:
        image_path = os.path.join(app.root_path, 'img', filename)
        response = make_response(send_file(image_path, mimetype=mime_type))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    else:
        return 'Invalid or unsupported file extension', 400

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password1 = request.form.get('password1')
    password2 = request.form.get('password2')
    username_exists = get_username(username)
    if username_exists:
        error_message = 'Username already exists.'
        return redirect(url_for('HomePage', error=error_message, username="Guest"))
    if password1 != password2:
        error_message = 'Passwords do not match.'
        return redirect(url_for('HomePage', error=error_message, username="Guest"))
    hashed_password = bcrypt.generate_password_hash(password1)
    user_data = {"username": username, "password": hashed_password}
    Users.insert_one(user_data)
    return redirect(url_for('HomePage', username="Guest"))

def get_username(username):
    user_document = Users.find_one({"username": username})
    if user_document:
        return user_document["username"]
    else:
        return None

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    user_data = Users.find_one({"username": username})
    if not user_data:
        error_message = 'Username does not exist'
        return redirect(url_for('HomePage', error=error_message, username="Guest"))
    stored_password = user_data["password"]
    if check_password_hash(stored_password, password):
        token = generate_auth_token(username)
        response = redirect(url_for('HomePage', username=username)) 
        response.set_cookie('auth_token', token, httponly=True, max_age=3600)
        return response, 302
    else:
        error_message = 'Invalid username and password combination'
        return redirect(url_for('HomePage', error=error_message, username="Guest"))

def generate_auth_token(username):
    token = str(uuid.uuid4())
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    Tokens.insert_one({"username": username, "token_hash": token_hash})
    return token

def remove_auth_token(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    Tokens.delete_one({"token_hash": token_hash})

@app.route('/logout')
def logout():
    auth_token = request.cookies.get('auth_token')
    if auth_token:
        token_hash = hashlib.sha256(auth_token.encode()).hexdigest()
        if Tokens.find_one({"token_hash": token_hash}):
            Tokens.delete_one({"token_hash": token_hash})
    response = redirect(url_for('HomePage', username="Guest"))
    response.set_cookie('auth_token', '', expires=0)
    return response

@app.route('/create_comment', methods=['POST'])
def create_comment():
    content = html.escape(request.form.get('comment'))
    author = "Guest"  
    auth_token = request.cookies.get('auth_token')
    if auth_token:
        token_hash = hashlib.sha256(auth_token.encode()).hexdigest()
        token_data = Tokens.find_one({"token_hash": token_hash})
        if token_data:
            author = token_data.get('username', 'Guest')
    file = request.files.get('file')
    if file:
        signature = file.read(8)
        file_type = validate_image_signature(signature)
        if not file_type:
            file_type = validate_video_signature(signature)
        if file_type:
            id = get_next_media_id()
            media_filename = f'uploaded_media{id}.' + file_type
            file_path = os.path.join('/app/media/', f'uploaded_file{id}.' + file_type)
            file.save(file_path)
            content += f' <{ "img" if file_type in ["jpg", "png", "gif"] else "video" } src=\"/video/{media_filename}\" alt="Uploaded file">'
            new_comment = {
                "author": author,
                "content": content,
                "comment_id": get_next_id(),
                "likes": []
            }
            Comments.insert_one(new_comment)
        else:
            return "Invalid file format", 400
    else:
        new_comment = {
            "author": author,
            "content": content,
            "comment_id": get_next_id(),
            "likes": []
        }
        Comments.insert_one(new_comment)
    return redirect(url_for('HomePage', username=author))

@app.route('/like_comment', methods=['POST'])
def like_comment():
    comment_id = request.form.get('comment_id')
    auth_token = request.cookies.get('auth_token')
    if not auth_token:
        error_message = "Only authenticated users can like posts"
        return jsonify({'error': error_message}), 400
    token_hash = hashlib.sha256(auth_token.encode()).hexdigest()
    user_data = Tokens.find_one({"token_hash": token_hash})
    if not user_data:
        error_message = "Only authenticated users can like posts"
        return jsonify({'error': error_message}), 400
    username = user_data.get('username')
    post = Comments.find_one({"comment_id": int(comment_id)})
    if post is None:
        error_message = "Comment not found"
        return jsonify({'error': error_message}), 404 
    if username in post.get('likes', []):
        error_message = "User has already liked post"
        return jsonify({'error': error_message}), 400
    Comments.update_one({"comment_id": int(comment_id)}, {"$push": {"likes": username}})
    updated_post = Comments.find_one({"comment_id": int(comment_id)})
    likes_count = len(updated_post.get('likes', []))
    return jsonify({'likes_count': likes_count})

def get_next_id():
    document = ID.find_one()
    current_value = document.get('value', 0)
    ID.update_one({}, {"$set": {"value": current_value + 1}})
    return current_value

def get_next_media_id():
    document = media_id.find_one()
    current_value = document.get('value', 0)
    media_id.update_one({}, {"$set": {"value": current_value + 1}})
    return current_value

@app.route('/get_comments')
def get_comments():
    comments = Comments.find()
    comments_list = []
    for comment in comments:
        comment['_id'] = str(comment['_id'])
        comments_list.append(comment)
    return jsonify({'comments': comments_list})

#Adds profile data to user's database entry to use as img source
@app.route('/upload-profile', methods=['POST'])
def upload_profile_picture():
    auth_token = request.cookies.get('auth_token')
    if not auth_token:
        error_message = "Only authenticated users can upload profile pictures"
        return jsonify({'error': error_message}), 400
    token_hash = hashlib.sha256(auth_token.encode()).hexdigest()
    user_data = Tokens.find_one({"token_hash": token_hash})
    if not user_data:
        error_message = "Only authenticated users can upload profile pictures"
        return jsonify({'error': error_message}), 400
    if 'image' not in request.files:
        return 'No image uploaded', 400
    image_file = request.files['image']
    signature = image_file.read(8)
    image_file.seek(0)
    image_type = validate_image_signature(signature)
    if not image_type:
        return 'Invalid file format', 400
    id = get_next_media_id()
    image_filename = f'uploaded_media{id}.' + image_type
    image_path = os.path.join('/app/media/', image_filename)
    image_file.save(image_path)
    username = user_data.get('username')
    user_data = Users.update_one({"username": username}, {"$set": {"profile_file": f"/media/{image_filename}"}})
    response = redirect(url_for('HomePage', username=username))
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)