import os
import base64
import uuid
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = os.path.dirname(__file__)
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
except Exception:
    pass

from db import connection, execute, init_db, insert, query_all, query_one, using_postgres


UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
HASH_METHOD = "pbkdf2:sha256:180000"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
init_db()


def money_value(value):
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    return amount.quantize(Decimal("0.01"))


def int_value(value, default=0, minimum=0, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


@app.template_filter("money")
def money(value):
    amount = money_value(value)
    if amount == amount.to_integral():
        return f"${int(amount)}"
    return f"${amount:,.2f}"


@app.template_filter("network_slug")
def network_slug(value):
    return str(value or "").strip().lower().replace(" ", "-")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        flash("Only image files are allowed for card uploads.", "error")
        return None
    safe_name = secure_filename(file_storage.filename)
    ext = safe_name.rsplit(".", 1)[1].lower()
    mime = file_storage.mimetype or f"image/{'jpeg' if ext == 'jpg' else ext}"
    data = base64.b64encode(file_storage.read()).decode("ascii")
    return {"image_mime": mime, "image_data": data, "image_filename": None}


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            flash("Admin sign in required.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "app_name": "Russian Market",
        "db_label": "Neon Postgres" if using_postgres() else "SQLite local",
    }


def get_admin_credentials():
    return query_one("SELECT * FROM admin_credentials ORDER BY id LIMIT 1")


def get_setting(key, default=""):
    row = query_one("SELECT value FROM site_settings WHERE key = ?", (key,))
    return row["value"] if row else default


def _sql(statement):
    return statement.replace("?", "%s") if using_postgres() else statement


def set_setting(key, value):
    if query_one("SELECT key FROM site_settings WHERE key = ?", (key,)):
        execute("UPDATE site_settings SET value = ? WHERE key = ?", (value, key))
    else:
        execute("INSERT INTO site_settings (key, value) VALUES (?, ?)", (key, value))


def generate_public_id():
    while True:
        public_id = "RM" + uuid.uuid4().hex[:8].upper()
        if not query_one("SELECT id FROM users WHERE public_id = ?", (public_id,)):
            return public_id


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        credentials = get_admin_credentials()
        if (
            credentials
            and username.lower() == credentials["username"].lower()
            and check_password_hash(credentials["password_hash"], password)
        ):
            session.clear()
            session["admin"] = True
            flash("Admin signed in.", "success")
            return redirect(url_for("admin_dashboard"))

        user = query_one("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,))
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard"))
        flash("Username or password is incorrect.", "error")

    mode = request.args.get("mode", "login")
    return render_template("login.html", mode=mode)


@app.post("/register")
def register():
    username = request.form.get("username", "").strip()
    profile_name = request.form.get("profile_name", "").strip()
    password = request.form.get("password", "").strip()
    if len(username) < 3 or len(password) < 4:
        flash("Use at least 3 characters for username and 4 for password.", "error")
        return redirect(url_for("login", mode="register"))
    if not profile_name:
        profile_name = username
    if query_one("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,)):
        flash("That username already exists.", "error")
        return redirect(url_for("login", mode="register"))

    user_id = insert(
        "users",
        {
            "username": username,
            "public_id": generate_public_id(),
            "profile_name": profile_name,
            "password_hash": generate_password_hash(password, method=HASH_METHOD),
            "balance": 0,
        },
    )
    session.clear()
    session["user_id"] = user_id
    flash("Account created.", "success")
    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    cards = query_all(
        """
        SELECT cards.id, cards.country, cards.country_code, cards.network,
               cards.price, cards.preload, cards.city, cards.masked_number,
               cards.expiry, cards.status, cards.display_stock, cards.image_filename, cards.image_mime,
               CASE WHEN cards.image_data IS NOT NULL THEN 1 ELSE 0 END AS has_image_data,
               COALESCE(stock.available_stock, 0) AS available_stock,
               COALESCE(NULLIF(cards.display_stock, 0), COALESCE(stock.available_stock, 0), 0) AS shown_stock
        FROM cards
        LEFT JOIN (
            SELECT card_id, COUNT(*) AS available_stock
            FROM card_stock
            WHERE status = 'available'
            GROUP BY card_id
        ) AS stock ON stock.card_id = cards.id
        WHERE cards.status != 'hidden'
        ORDER BY cards.id DESC
        """
    )
    enabled_filter = "enabled = TRUE" if using_postgres() else "enabled = 1"
    addresses = query_all(
        f"SELECT * FROM crypto_addresses WHERE {enabled_filter} ORDER BY sort_order, id"
    )
    orders = query_all(
        """
        SELECT orders.*, cards.country, cards.country_code, cards.network,
               cards.masked_number, cards.expiry,
               COALESCE(orders.delivered_details, cards.full_details) AS view_details
        FROM orders
        JOIN cards ON cards.id = orders.card_id
        WHERE orders.user_id = ?
        ORDER BY orders.id DESC
        """,
        (user["id"],),
    )
    deposits = query_all(
        "SELECT * FROM deposits WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (user["id"],),
    )
    custom_orders = query_all(
        "SELECT * FROM custom_orders WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (user["id"],),
    )
    networks = sorted({card["network"] for card in cards if card.get("network")})
    return render_template(
        "dashboard.html",
        user=user,
        cards=cards,
        networks=networks,
        addresses=addresses,
        orders=orders,
        deposits=deposits,
        custom_orders=custom_orders,
        helper_email=get_setting("helper_email", "support@example.com"),
    )


@app.get("/card-image/<int:card_id>")
def card_image(card_id):
    card = query_one(
        "SELECT image_mime, image_data FROM cards WHERE id = ? AND image_data IS NOT NULL",
        (card_id,),
    )
    if not card:
        return ("", 404)
    return Response(
        base64.b64decode(card["image_data"]),
        mimetype=card["image_mime"] or "image/png",
    )


@app.post("/deposit")
@login_required
def create_deposit():
    user = current_user()
    currency = request.form.get("currency", "").strip()
    txid = request.form.get("txid", "").strip()
    amount = money_value(request.form.get("amount", "0"))

    if not currency or not txid:
        flash("Select currency and paste the transaction ID.", "error")
        return redirect(url_for("dashboard"))
    if amount <= 0:
        flash("Enter the deposit amount you sent.", "error")
        return redirect(url_for("dashboard"))

    insert(
        "deposits",
        {
            "user_id": user["id"],
            "currency": currency,
            "txid": txid,
            "amount": str(amount),
            "status": "pending",
        },
    )
    return redirect(url_for("dashboard"))


@app.post("/purchase/<int:card_id>")
@login_required
def purchase(card_id):
    user = current_user()
    card = query_one("SELECT * FROM cards WHERE id = ?", (card_id,))
    if not card or card["status"] != "in_stock":
        flash("This card is not available right now.", "error")
        return redirect(url_for("dashboard"))

    try:
        quantity = max(1, min(20, int(request.form.get("quantity") or 1)))
    except ValueError:
        quantity = 1
    price = money_value(card["price"])
    total = price * quantity
    balance = money_value(user["balance"])
    if balance < total:
        flash("Insufficient balance. Please deposit first.", "error")
        return redirect(url_for("dashboard"))

    stock_items = query_all(
        "SELECT id, details FROM card_stock WHERE card_id = ? AND status = 'available' ORDER BY id LIMIT ?",
        (card_id, quantity),
    )
    auto_approve = len(stock_items) >= quantity
    delivered_details = "\n\n---\n\n".join(item["details"] for item in stock_items) if auto_approve else None
    status = "approved" if auto_approve else "pending"

    with connection() as conn:
        cur = conn.cursor()
        placeholder = "%s" if using_postgres() else "?"
        cur.execute(
            f"UPDATE users SET balance = balance - {placeholder} WHERE id = {placeholder}",
            (str(total), user["id"]),
        )
        if using_postgres():
            cur.execute(
                """
                INSERT INTO orders (user_id, card_id, price, quantity, delivered_details, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user["id"], card["id"], str(total), quantity, delivered_details, status),
            )
            order_id = cur.fetchone()["id"]
        else:
            cur.execute(
                """
                INSERT INTO orders (user_id, card_id, price, quantity, delivered_details, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], card["id"], str(total), quantity, delivered_details, status),
            )
            order_id = cur.lastrowid

        if auto_approve:
            for item in stock_items:
                cur.execute(
                    _sql("UPDATE card_stock SET status = ?, order_id = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ?"),
                    ("sold", order_id, item["id"]),
                )

    return redirect(url_for("dashboard"))


@app.post("/custom-order")
@login_required
def custom_order():
    user = current_user()
    try:
        quantity = max(1, min(100, int(request.form.get("quantity") or 1)))
    except ValueError:
        quantity = 1
    insert(
        "custom_orders",
        {
            "user_id": user["id"],
            "card_type": request.form.get("card_type", "Visa").strip(),
            "country": request.form.get("country", "").strip(),
            "quantity": quantity,
            "budget": str(money_value(request.form.get("budget", "0"))),
            "notes": request.form.get("notes", "").strip(),
            "status": "pending",
        },
    )
    return redirect(url_for("dashboard"))


@app.post("/orders/<int:order_id>/delete")
@login_required
def user_delete_order(order_id):
    user = current_user()
    order = query_one(
        "SELECT id, status FROM orders WHERE id = ? AND user_id = ?",
        (order_id, user["id"]),
    )
    if order and order["status"] == "rejected":
        execute("DELETE FROM orders WHERE id = ?", (order_id,))
    return redirect(url_for("dashboard"))


@app.post("/custom-orders/<int:custom_order_id>/delete")
@login_required
def user_delete_custom_order(custom_order_id):
    user = current_user()
    custom = query_one(
        "SELECT id, status FROM custom_orders WHERE id = ? AND user_id = ?",
        (custom_order_id, user["id"]),
    )
    if custom and custom["status"] == "rejected":
        execute("DELETE FROM custom_orders WHERE id = ?", (custom_order_id,))
    return redirect(url_for("dashboard"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        credentials = get_admin_credentials()
        if (
            credentials
            and username.lower() == credentials["username"].lower()
            and check_password_hash(credentials["password_hash"], password)
        ):
            session.clear()
            session["admin"] = True
            flash("Admin signed in.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "error")
        return redirect(url_for("login"))
    return redirect(url_for("login"))


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    flash("Admin signed out.", "success")
    return redirect(url_for("login"))


@app.get("/admin-panel")
@app.get("/admin_panel")
@app.get("/admin.html")
def admin_alias():
    return redirect(url_for("admin_dashboard"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q.lower()}%"
        users = query_all(
            """
            SELECT id, public_id, username, profile_name, balance, created_at
            FROM users
            WHERE LOWER(username) LIKE ?
               OR LOWER(COALESCE(profile_name, '')) LIKE ?
               OR LOWER(COALESCE(public_id, '')) LIKE ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (like, like, like),
        )
    else:
        users = query_all(
            """
            SELECT id, public_id, username, profile_name, balance, created_at
            FROM users
            ORDER BY id DESC
            LIMIT 100
            """
        )

    user_details = {}
    for item in (users[:20] if q else []):
        user_details[item["id"]] = {
            "deposits": query_all(
                "SELECT * FROM deposits WHERE user_id = ? ORDER BY id DESC LIMIT 8",
                (item["id"],),
            ),
            "orders": query_all(
                """
                SELECT orders.*, cards.country, cards.network
                FROM orders
                JOIN cards ON cards.id = orders.card_id
                WHERE orders.user_id = ?
                ORDER BY orders.id DESC
                LIMIT 8
                """,
                (item["id"],),
            ),
            "custom_orders": query_all(
                "SELECT * FROM custom_orders WHERE user_id = ? ORDER BY id DESC LIMIT 8",
                (item["id"],),
            ),
        }

    stats = {
        "users": query_one("SELECT COUNT(*) AS total FROM users")["total"],
        "pending_deposits": query_one(
            "SELECT COUNT(*) AS total FROM deposits WHERE status = 'pending'"
        )["total"],
        "pending_orders": query_one(
            "SELECT COUNT(*) AS total FROM orders WHERE status = 'pending'"
        )["total"],
        "cards": query_one("SELECT COUNT(*) AS total FROM cards WHERE status != 'hidden'")[
            "total"
        ],
    }
    return render_template(
        "admin.html",
        stats=stats,
        admin_credentials=get_admin_credentials(),
        users=users,
        user_details=user_details,
        search_query=q,
        cards=query_all(
            """
            SELECT cards.id, cards.country, cards.country_code, cards.network,
                   cards.price, cards.preload, cards.city, cards.masked_number,
                   cards.expiry, cards.full_details, cards.display_stock, cards.status, cards.image_filename,
                   cards.image_mime, CASE WHEN cards.image_data IS NOT NULL THEN 1 ELSE 0 END AS has_image_data,
                   COALESCE(stock.available_stock, 0) AS available_stock,
                   COALESCE(NULLIF(cards.display_stock, 0), COALESCE(stock.available_stock, 0), 0) AS shown_stock
            FROM cards
            LEFT JOIN (
                SELECT card_id, COUNT(*) AS available_stock
                FROM card_stock
                WHERE status = 'available'
                GROUP BY card_id
            ) AS stock ON stock.card_id = cards.id
            ORDER BY cards.id DESC
            """
        ),
        network_options=query_all("SELECT DISTINCT network FROM cards ORDER BY network"),
        stock_rows=query_all(
            """
            SELECT card_stock.*, cards.country, cards.network
            FROM card_stock
            JOIN cards ON cards.id = card_stock.card_id
            ORDER BY card_stock.id DESC
            LIMIT 80
            """
        ),
        addresses=query_all("SELECT * FROM crypto_addresses ORDER BY sort_order, id"),
        deposits=query_all(
            """
            SELECT deposits.*, users.username, users.profile_name, users.public_id
            FROM deposits
            JOIN users ON users.id = deposits.user_id
            ORDER BY deposits.id DESC
            LIMIT 50
            """
        ),
        orders=query_all(
            """
            SELECT orders.*, users.username, users.profile_name, users.public_id,
                   cards.country, cards.network, cards.full_details
            FROM orders
            JOIN users ON users.id = orders.user_id
            JOIN cards ON cards.id = orders.card_id
            ORDER BY orders.id DESC
            LIMIT 50
            """
        ),
        custom_orders=query_all(
            """
            SELECT custom_orders.*, users.username, users.profile_name, users.public_id
            FROM custom_orders
            JOIN users ON users.id = custom_orders.user_id
            ORDER BY custom_orders.id DESC
            LIMIT 50
            """
        ),
        helper_email=get_setting("helper_email", "support@example.com"),
    )


@app.post("/admin/credentials")
@admin_required
def admin_update_credentials():
    credentials = get_admin_credentials()
    current_password = request.form.get("current_password", "").strip()
    new_username = request.form.get("new_username", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not credentials or not check_password_hash(
        credentials["password_hash"], current_password
    ):
        flash("Current admin password is incorrect.", "error")
        return redirect(url_for("admin_dashboard"))
    if len(new_username) < 3:
        flash("New admin username must be at least 3 characters.", "error")
        return redirect(url_for("admin_dashboard"))
    if len(new_password) < 6:
        flash("New admin password must be at least 6 characters.", "error")
        return redirect(url_for("admin_dashboard"))
    if new_password != confirm_password:
        flash("New admin passwords do not match.", "error")
        return redirect(url_for("admin_dashboard"))

    execute(
        """
        UPDATE admin_credentials
        SET username = ?, password_hash = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            new_username,
            generate_password_hash(new_password, method=HASH_METHOD),
            credentials["id"],
        ),
    )
    flash("Admin username and password updated. Old credentials will no longer work.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/cards")
@admin_required
def admin_add_card():
    image_payload = read_upload(request.files.get("image")) or {
        "image_mime": None,
        "image_data": None,
        "image_filename": None,
    }
    insert(
        "cards",
        {
            "country": request.form.get("country", "USA").strip(),
            "country_code": request.form.get("country_code", "us").strip().lower(),
            "network": request.form.get("network", "Visa").strip(),
            "price": str(money_value(request.form.get("price", "0"))),
            "preload": str(money_value(request.form.get("preload", "0"))),
            "city": request.form.get("city", "").strip(),
            "masked_number": request.form.get("masked_number", "0000 0000 **** ****").strip(),
            "expiry": request.form.get("expiry", "01/30").strip(),
            "full_details": request.form.get("full_details", "").strip(),
            "display_stock": int_value(request.form.get("display_stock"), 0),
            "status": request.form.get("status", "in_stock"),
            "image_filename": image_payload["image_filename"],
            "image_mime": image_payload["image_mime"],
            "image_data": image_payload["image_data"],
        },
    )
    flash("Card added.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/cards/<int:card_id>")
@admin_required
def admin_update_card(card_id):
    existing = query_one(
        "SELECT image_filename, image_mime, image_data FROM cards WHERE id = ?",
        (card_id,),
    )
    if not existing:
        flash("Card not found.", "error")
        return redirect(url_for("admin_dashboard"))
    image_payload = read_upload(request.files.get("image"))
    image_filename = existing["image_filename"]
    image_mime = existing["image_mime"]
    image_data = existing["image_data"]
    if image_payload:
        image_filename = image_payload["image_filename"]
        image_mime = image_payload["image_mime"]
        image_data = image_payload["image_data"]
    execute(
        """
        UPDATE cards
        SET country = ?, country_code = ?, network = ?, price = ?, preload = ?,
            city = ?, masked_number = ?, expiry = ?, full_details = ?, display_stock = ?,
            status = ?, image_filename = ?, image_mime = ?, image_data = ?
        WHERE id = ?
        """,
        (
            request.form.get("country", "").strip(),
            request.form.get("country_code", "us").strip().lower(),
            request.form.get("network", "").strip(),
            str(money_value(request.form.get("price", "0"))),
            str(money_value(request.form.get("preload", "0"))),
            request.form.get("city", "").strip(),
            request.form.get("masked_number", "").strip(),
            request.form.get("expiry", "").strip(),
            request.form.get("full_details", "").strip(),
            int_value(request.form.get("display_stock"), 0),
            request.form.get("status", "in_stock"),
            image_filename,
            image_mime,
            image_data,
            card_id,
        ),
    )
    flash("Card details updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/stock")
@admin_required
def admin_add_stock():
    card_id = int(request.form.get("card_id") or 0)
    raw_details = request.form.get("details", "").strip()
    if not card_id or not raw_details:
        flash("Select a card and paste stock details.", "error")
        return redirect(url_for("admin_dashboard"))

    items = [item.strip() for item in raw_details.split("\n---\n") if item.strip()]
    if not items:
        items = [raw_details]
    for details in items:
        insert(
            "card_stock",
            {
                "card_id": card_id,
                "details": details,
                "status": "available",
                "order_id": None,
            },
        )
    flash(f"{len(items)} stock item added.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/addresses")
@admin_required
def admin_add_address():
    insert(
        "crypto_addresses",
        {
            "currency": request.form.get("currency", "").strip().upper(),
            "network": request.form.get("network", "").strip(),
            "address": request.form.get("address", "").strip(),
            "sort_order": int(request.form.get("sort_order") or 0),
            "enabled": True if using_postgres() else 1,
        },
    )
    flash("Deposit address added.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/addresses/<int:address_id>")
@admin_required
def admin_update_address(address_id):
    execute(
        """
        UPDATE crypto_addresses
        SET currency = ?, network = ?, address = ?, sort_order = ?, enabled = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            request.form.get("currency", "").strip().upper(),
            request.form.get("network", "").strip(),
            request.form.get("address", "").strip(),
            int(request.form.get("sort_order") or 0),
            (request.form.get("enabled") == "on")
            if using_postgres()
            else (1 if request.form.get("enabled") == "on" else 0),
            address_id,
        ),
    )
    flash("Deposit address updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/settings")
@admin_required
def admin_update_settings():
    set_setting("helper_email", request.form.get("helper_email", "").strip())
    flash("Helper email updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/deposits/<int:deposit_id>/<action>")
@admin_required
def admin_review_deposit(deposit_id, action):
    deposit = query_one("SELECT * FROM deposits WHERE id = ?", (deposit_id,))
    if not deposit or deposit["status"] != "pending":
        flash("Deposit is not pending.", "error")
        return redirect(url_for("admin_dashboard"))

    if action == "approve":
        amount = money_value(request.form.get("amount") or deposit["amount"])
        with connection() as conn:
            cur = conn.cursor()
            if using_postgres():
                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE id = %s",
                    (str(amount), deposit["user_id"]),
                )
                cur.execute(
                    "UPDATE deposits SET amount = %s, status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (str(amount), deposit_id),
                )
            else:
                cur.execute(
                    "UPDATE users SET balance = balance + ? WHERE id = ?",
                    (str(amount), deposit["user_id"]),
                )
                cur.execute(
                    "UPDATE deposits SET amount = ?, status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (str(amount), deposit_id),
                )
        flash("Deposit approved and balance credited.", "success")
    elif action == "reject":
        execute(
            "UPDATE deposits SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (deposit_id,),
        )
        flash("Deposit rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/orders/<int:order_id>/<action>")
@admin_required
def admin_review_order(order_id, action):
    order = query_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if action == "delete":
        if order:
            execute("DELETE FROM orders WHERE id = ?", (order_id,))
        return redirect(url_for("admin_dashboard"))
    if not order or order["status"] != "pending":
        flash("Order is not pending.", "error")
        return redirect(url_for("admin_dashboard"))

    if action == "approve":
        manual_details = request.form.get("delivered_details", "").strip()
        stock_items = query_all(
            "SELECT id, details FROM card_stock WHERE card_id = ? AND status = 'available' ORDER BY id LIMIT ?",
            (order["card_id"], order.get("quantity") or 1),
        )
        if manual_details:
            delivered_details = manual_details
        elif len(stock_items) >= (order.get("quantity") or 1):
            delivered_details = "\n\n---\n\n".join(item["details"] for item in stock_items)
        else:
            card = query_one("SELECT full_details FROM cards WHERE id = ?", (order["card_id"],))
            delivered_details = card["full_details"] if card else ""

        execute(
            """
            UPDATE orders
            SET status = 'approved', delivered_details = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (delivered_details, order_id),
        )
        if stock_items and not manual_details:
            for item in stock_items[: (order.get("quantity") or 1)]:
                execute(
                    "UPDATE card_stock SET status = 'sold', order_id = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id, item["id"]),
                )
        flash("Order approved. User can now see card details.", "success")
    elif action == "reject":
        with connection() as conn:
            cur = conn.cursor()
            if using_postgres():
                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE id = %s",
                    (str(order["price"]), order["user_id"]),
                )
                cur.execute(
                    "UPDATE orders SET status = 'rejected', approved_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (order_id,),
                )
            else:
                cur.execute(
                    "UPDATE users SET balance = balance + ? WHERE id = ?",
                    (str(order["price"]), order["user_id"]),
                )
                cur.execute(
                    "UPDATE orders SET status = 'rejected', approved_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,),
                )
        flash("Order rejected and balance refunded.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/orders/<int:order_id>/delete")
@admin_required
def admin_delete_order(order_id):
    order = query_one("SELECT id FROM orders WHERE id = ?", (order_id,))
    if order:
        execute("DELETE FROM orders WHERE id = ?", (order_id,))
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/custom-orders/<int:custom_order_id>/<action>")
@admin_required
def admin_review_custom_order(custom_order_id, action):
    custom = query_one("SELECT * FROM custom_orders WHERE id = ?", (custom_order_id,))
    if action == "delete":
        if custom:
            execute("DELETE FROM custom_orders WHERE id = ?", (custom_order_id,))
        return redirect(url_for("admin_dashboard"))
    if not custom or custom["status"] != "pending":
        flash("Custom order is not pending.", "error")
        return redirect(url_for("admin_dashboard"))
    if action == "approve":
        execute(
            "UPDATE custom_orders SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (custom_order_id,),
        )
        flash("Custom order approved.", "success")
    elif action == "reject":
        execute(
            "UPDATE custom_orders SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (custom_order_id,),
        )
        flash("Custom order rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/custom-orders/<int:custom_order_id>/delete")
@admin_required
def admin_delete_custom_order(custom_order_id):
    custom = query_one("SELECT id FROM custom_orders WHERE id = ?", (custom_order_id,))
    if custom:
        execute("DELETE FROM custom_orders WHERE id = ?", (custom_order_id,))
    return redirect(url_for("admin_dashboard"))


@app.get("/api/user/status")
@login_required
def api_user_status():
    user = current_user()
    order_state = query_one(
        "SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM orders WHERE user_id = ?",
        (user["id"],),
    )
    deposit_state = query_one(
        "SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM deposits WHERE user_id = ?",
        (user["id"],),
    )
    pending_state = query_one(
        "SELECT COUNT(*) AS count FROM orders WHERE user_id = ? AND status = 'pending'",
        (user["id"],),
    )
    deposit_pending_state = query_one(
        "SELECT COUNT(*) AS count FROM deposits WHERE user_id = ? AND status = 'pending'",
        (user["id"],),
    )
    custom_state = query_one(
        "SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM custom_orders WHERE user_id = ?",
        (user["id"],),
    )
    return jsonify(
        {
            "version": f"{user['balance']}:{order_state['count']}:{order_state['max_id']}:{deposit_state['count']}:{deposit_state['max_id']}:{pending_state['count']}:{deposit_pending_state['count']}:{custom_state['count']}:{custom_state['max_id']}",
            "balance": str(user["balance"]),
        }
    )


@app.get("/api/admin/status")
@admin_required
def api_admin_status():
    state = {
        "deposits": query_one("SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM deposits WHERE status = 'pending'"),
        "orders": query_one("SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM orders WHERE status = 'pending'"),
        "custom": query_one("SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM custom_orders WHERE status = 'pending'"),
        "users": query_one("SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM users"),
        "all_orders": query_one("SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM orders"),
        "all_deposits": query_one("SELECT COUNT(*) AS count, COALESCE(MAX(id), 0) AS max_id FROM deposits"),
    }
    return jsonify(
        {
            "version": ":".join(
                f"{key}-{value['count']}-{value['max_id']}" for key, value in state.items()
            )
        }
    )


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG") == "1",
    )
